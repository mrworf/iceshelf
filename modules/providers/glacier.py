import io
import os
import sys
import logging
import time
import threading
from queue import Queue, Empty

from . import BackupProvider
from modules import aws
from modules import helper


class _UploadCoordinator:
    """Thread-pool that uploads multipart chunks to Glacier via boto3."""

    def __init__(self, threads=4):
        self.threads = threads
        self.sent = 0
        self.began = round(time.time())
        self.exit = False
        self.queue = Queue()

    def process(self):
        self.began = round(time.time())
        for _ in range(self.threads):
            t = threading.Thread(target=self._worker)
            t.daemon = True
            t.start()

    def _worker(self):
        run = True
        while run and not self.exit:
            try:
                entry = self.queue.get(False)
            except Empty:
                break
            except Exception:
                logging.exception('Failed to read from queue')
                break
            sent = entry.work()
            if sent == -1:
                logging.error("Upload chunk failed")
                run = False
                self.exit = True
            else:
                self.sent += sent
            self.queue.task_done()
        self.threads -= 1

    def add(self, job):
        if self.exit:
            return False
        self.queue.put(job)
        return True

    def get_time(self):
        t = round(time.time()) - self.began
        return max(t, 1)

    def get_sent(self):
        return self.sent

    def is_done(self):
        return self.threads == 0 or self.exit

    def finish(self):
        self.queue.join()
        return not self.exit


class _UploadJob:
    """Uploads a single multipart chunk using boto3."""

    def __init__(self, client, vault, filepath, offset, size, checksum, upload_id):
        self.client = client
        self.vault = vault
        self.filepath = filepath
        self.offset = offset
        self.size = size
        self.checksum = checksum
        self.upload_id = upload_id
        self.retries = 10

    def work(self):
        data_range = 'bytes %d-%d/*' % (self.offset, self.offset + self.size - 1)
        retry = self.retries
        while retry > 0:
            try:
                with io.open(self.filepath, 'rb') as f:
                    f.seek(self.offset)
                    body = f.read(self.size)
                resp = self.client.upload_multipart_part(
                    vaultName=self.vault,
                    uploadId=self.upload_id,
                    body=body,
                    range=data_range,
                    checksum=self.checksum,
                )
                got = resp.get('checksum', '')
                if got and got != self.checksum:
                    logging.error('Hash mismatch, expected %s got %s', self.checksum, got)
                else:
                    return self.size
            except Exception as e:
                logging.debug('Upload part error: %s', e)

            retry -= 1
            wait = (self.retries - retry) * 30
            logging.warning('%s @ %d failed, retrying in %ds. %d tries left',
                            helper.formatSize(self.size), self.offset, wait, retry)
            time.sleep(wait)

        logging.error('Unable to upload %s at offset %d',
                      helper.formatSize(self.size), self.offset)
        return -1


class GlacierProvider(BackupProvider):
    """Upload archives to AWS Glacier using boto3."""
    name = 'glacier'
    allowed_options = {'type', 'vault', 'threads'} | set(aws.PROVIDER_CONFIG_KEYS)

    def verify(self):
        self.vault = self.options.get('vault')
        self.threads = int(self.options.get('threads', 4))
        if not self.vault:
            logging.error('glacier provider requires "vault"')
            return False
        aws_config = aws.extract_aws_config(self.options)
        client, err = aws.create_glacier_client(aws_config)
        if err:
            logging.error('glacier provider: %s', err)
            return False
        self.client = client
        return True

    def storage_id(self):
        return f'glacier:{self.vault}'

    def get_vault(self):
        return self.vault

    def upload_files(self, files):
        try:
            self.client.create_vault(vaultName=self.vault)
        except Exception:
            logging.exception('Failed to create vault %s', self.vault)
            return False

        total = sum(os.path.getsize(f) for f in files)
        logging.info("Uploading %d files (%s) to glacier",
                     len(files), helper.formatSize(total))

        done = 0
        for idx, filepath in enumerate(files, 1):
            prefix = "(%d of %d) " % (idx, len(files))
            if not self._upload_one(filepath, prefix, done, total):
                return False
            done += os.path.getsize(filepath)
        return True

    def _upload_one(self, filepath, prefix, bytes_done, bytes_total):
        name = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        chunk_size = aws.compute_chunk_size(size)

        hashes = aws.hashFile(filepath, chunk_size)
        if hashes is None:
            logging.error('Unable to hash file %s', filepath)
            return False

        try:
            resp = self.client.initiate_multipart_upload(
                vaultName=self.vault,
                archiveDescription=name,
                partSize=str(chunk_size),
            )
        except Exception:
            logging.exception('Unable to initiate upload for %s', name)
            return False
        upload_id = resp['uploadId']

        coord = _UploadCoordinator(self.threads)
        offset = 0
        block = 0
        remain = size
        while remain > 0:
            chunk = min(remain, chunk_size)
            job = _UploadJob(self.client, self.vault, filepath,
                             offset, chunk,
                             hashes['blocks'][block].hexdigest(),
                             upload_id)
            coord.add(job)
            block += 1
            remain -= chunk
            offset += chunk

        coord.process()
        while not coord.is_done():
            time.sleep(1)
            if sys.stdout.isatty() and coord.get_sent() > 0:
                sent = coord.get_sent()
                elapsed = coord.get_time()
                speed = sent / elapsed
                total_sent = bytes_done + sent
                timerem = ""
                if speed > 0 and bytes_total > total_sent:
                    timerem = ", %s remaining" % helper.formatTime(
                        (bytes_total - total_sent) / speed)
                sys.stdout.write(
                    '%s%s @ %s, %.2f%% done (%.2f%% total%s)          \r' % (
                        prefix, name,
                        helper.formatSpeed(speed),
                        sent / size * 100.0,
                        total_sent / bytes_total * 100.0,
                        timerem))
                sys.stdout.flush()
        if sys.stdout.isatty():
            sys.stdout.write('\n')
            sys.stdout.flush()

        if not coord.finish():
            logging.error('Failed to upload %s, aborting', name)
            try:
                self.client.abort_multipart_upload(
                    vaultName=self.vault, uploadId=upload_id)
            except Exception:
                pass
            return False

        try:
            self.client.complete_multipart_upload(
                vaultName=self.vault,
                uploadId=upload_id,
                archiveSize=str(size),
                checksum=hashes['final'].hexdigest(),
            )
        except Exception:
            logging.exception('Unable to complete upload of %s', name)
            return False
        return True

import os
import getpass
import hashlib
import logging
import posixpath

import paramiko

from . import BackupProvider

UPLOAD_CHUNK = 64 * 1024
_BOOL_TRUE = {'yes', 'true', '1'}


def _parse_bool(value, default=True):
    if value is None or value == '':
        return default
    return value.strip().lower() in _BOOL_TRUE


def _local_sha256(path, nbytes=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        remaining = nbytes
        while True:
            chunk_size = UPLOAD_CHUNK if remaining is None else min(UPLOAD_CHUNK, remaining)
            data = f.read(chunk_size)
            if not data:
                break
            h.update(data)
            if remaining is not None:
                remaining -= len(data)
                if remaining <= 0:
                    break
    return h.hexdigest()


class SFTPProvider(BackupProvider):
    name = 'sftp'
    allowed_options = {'type', 'host', 'port', 'user', 'key', 'password', 'path', 'retries', 'resume', 'verify'}

    def verify(self):
        self.host = self.options.get('host')
        if not self.host:
            logging.error('sftp provider requires "host"')
            return False

        self.port = int(self.options.get('port', 22))
        self.user = self.options.get('user') or getpass.getuser()
        self.key = self.options.get('key') or None
        self.password = self.options.get('password') or None
        self.path = self.options.get('path', '.')
        self.retries = int(self.options.get('retries', 3))
        self.resume = _parse_bool(self.options.get('resume'), default=True)
        self.do_verify = _parse_bool(self.options.get('verify'), default=True)

        if self.key and not os.path.exists(self.key):
            logging.error('SSH key file %s not found', self.key)
            return False

        try:
            client = self._connect()
            client.close()
        except paramiko.PasswordRequiredException:
            logging.error(
                'sftp: key %s requires a passphrase and no agent key is loaded. '
                'Interactive auth is not supported — load the key into an ssh-agent '
                'or set "password" in the provider config.', self.key)
            return False
        except paramiko.AuthenticationException as e:
            logging.error('sftp: authentication failed for %s@%s:%s — %s',
                          self.user, self.host, self.port, e)
            return False
        except Exception as e:
            logging.error('sftp: failed to connect to %s@%s:%s — %s',
                          self.user, self.host, self.port, e)
            return False

        return True

    def storage_id(self):
        return f'sftp://{self.user}@{self.host}:{self.port}{self.path}'

    def upload_files(self, files):
        try:
            client = self._connect()
        except Exception:
            logging.exception('sftp: connection failed')
            return False

        try:
            sftp = client.open_sftp()
            for local_path in files:
                remote_name = posixpath.join(self.path, os.path.basename(local_path))
                if not self._upload_with_retries(client, sftp, local_path, remote_name):
                    return False
            return True
        except Exception:
            logging.exception('sftp: upload session failed')
            return False
        finally:
            client.close()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs = {
            'hostname': self.host,
            'port': self.port,
            'username': self.user,
            'allow_agent': True,
            'look_for_keys': not self.key and not self.password,
        }
        if self.key:
            kwargs['key_filename'] = self.key
        if self.password:
            kwargs['password'] = self.password

        client.connect(**kwargs)
        return client

    # ------------------------------------------------------------------
    # Upload with retry / resume
    # ------------------------------------------------------------------

    def _upload_with_retries(self, client, sftp, local_path, remote_path):
        local_size = os.path.getsize(local_path)
        last_err = None

        for attempt in range(1 + self.retries):
            if attempt > 0:
                logging.warning('sftp: retry %d/%d for %s',
                                attempt, self.retries, local_path)
                try:
                    client.close()
                except Exception:
                    pass
                try:
                    client = self._connect()
                    sftp = client.open_sftp()
                except Exception:
                    logging.exception('sftp: reconnect failed on retry %d', attempt)
                    continue

            try:
                self._upload_one(client, sftp, local_path, remote_path, local_size)
                return True
            except _HashMismatch:
                logging.warning('sftp: hash mismatch for %s, deleting remote copy', remote_path)
                try:
                    sftp.remove(remote_path)
                except Exception:
                    pass
                last_err = 'hash mismatch'
            except (IOError, OSError, paramiko.SSHException) as e:
                logging.warning('sftp: upload error for %s — %s', local_path, e)
                last_err = e

        logging.error('sftp: giving up on %s after %d attempts (last error: %s)',
                      local_path, 1 + self.retries, last_err)
        return False

    def _upload_one(self, client, sftp, local_path, remote_path, local_size):
        offset = 0

        if self.resume:
            offset = self._resume_offset(client, sftp, local_path, remote_path, local_size)

        if offset >= local_size:
            logging.info('sftp: %s already complete on remote, verifying', remote_path)
        elif offset > 0:
            logging.info('sftp: resuming %s from offset %d / %d',
                         remote_path, offset, local_size)
            self._append_from(sftp, local_path, remote_path, offset)
        else:
            if offset == 0:
                try:
                    sftp.remove(remote_path)
                except IOError:
                    pass
            logging.info('sftp: uploading %s (%d bytes)', remote_path, local_size)
            sftp.put(local_path, remote_path)

        if self.do_verify:
            if not self._verify_remote(client, local_path, remote_path, local_size):
                raise _HashMismatch()
        else:
            remote_size = sftp.stat(remote_path).st_size
            if remote_size != local_size:
                raise _HashMismatch()

    # ------------------------------------------------------------------
    # Resume helpers
    # ------------------------------------------------------------------

    def _resume_offset(self, client, sftp, local_path, remote_path, local_size):
        """Return the byte offset to resume from, or 0 to start fresh."""
        try:
            remote_size = sftp.stat(remote_path).st_size
        except IOError:
            return 0

        if remote_size <= 0:
            return 0
        if remote_size >= local_size:
            return remote_size

        if not self.do_verify:
            return remote_size

        local_hash = _local_sha256(local_path, nbytes=remote_size)
        remote_hash = self._remote_partial_sha256(client, remote_path, remote_size)

        if remote_hash is None:
            logging.warning('sftp: cannot hash partial remote file, restarting upload')
            return 0

        if local_hash == remote_hash:
            return remote_size

        logging.warning('sftp: partial file %s is corrupt (local %s != remote %s), restarting',
                        remote_path, local_hash[:12], remote_hash[:12])
        try:
            sftp.remove(remote_path)
        except IOError:
            pass
        return 0

    def _append_from(self, sftp, local_path, remote_path, offset):
        with sftp.open(remote_path, 'ab') as remote_f:
            with open(local_path, 'rb') as local_f:
                local_f.seek(offset)
                while True:
                    data = local_f.read(UPLOAD_CHUNK)
                    if not data:
                        break
                    remote_f.write(data)

    # ------------------------------------------------------------------
    # Verification helpers
    # ------------------------------------------------------------------

    def _verify_remote(self, client, local_path, remote_path, local_size):
        local_hash = _local_sha256(local_path)
        remote_hash = self._remote_sha256(client, remote_path)

        if remote_hash is None:
            logging.warning('sftp: sha256sum not available on remote, falling back to size check')
            try:
                ssh_client = client
                sftp = ssh_client.open_sftp()
                remote_size = sftp.stat(remote_path).st_size
                sftp.close()
                return remote_size == local_size
            except Exception:
                return False

        if local_hash == remote_hash:
            return True

        logging.error('sftp: hash mismatch for %s (local %s, remote %s)',
                      remote_path, local_hash[:12], remote_hash[:12])
        return False

    def _remote_sha256(self, client, remote_path):
        return self._exec_hash_cmd(client, f'sha256sum {_shell_quote(remote_path)}')

    def _remote_partial_sha256(self, client, remote_path, nbytes):
        cmd = f'head -c {nbytes} {_shell_quote(remote_path)} | sha256sum'
        return self._exec_hash_cmd(client, cmd)

    def _exec_hash_cmd(self, client, cmd):
        try:
            _, stdout, stderr = client.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                return None
            output = stdout.read().decode().strip()
            return output.split()[0] if output else None
        except Exception:
            return None


class _HashMismatch(Exception):
    pass


def _shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"

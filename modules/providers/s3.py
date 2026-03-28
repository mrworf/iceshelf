import os
import logging
from . import BackupProvider
from modules import aws


class S3Provider(BackupProvider):
    name = 's3'

    def verify(self):
        self.bucket = self.options.get('bucket')
        self.prefix = self.options.get('prefix', '')
        if not self.bucket:
            logging.error('s3 provider requires "bucket"')
            return False
        aws_config = aws.extract_aws_config(self.options)
        client, err = aws.create_s3_client(aws_config)
        if err:
            logging.error('s3 provider: %s', err)
            return False
        self.client = client
        return True

    def storage_id(self):
        prefix = f'/{self.prefix}' if self.prefix else ''
        return f's3:{self.bucket}{prefix}'

    def upload_files(self, files):
        for f in files:
            key = os.path.join(self.prefix, os.path.basename(f))
            try:
                self.client.upload_file(f, self.bucket, key)
            except Exception:
                logging.exception('s3 upload failed for %s', f)
                return False
        return True

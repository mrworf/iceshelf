import os
import logging
import boto3
from botocore.exceptions import ClientError
from . import BackupProvider

class S3Provider(BackupProvider):
    name = 's3'
    def verify(self):
        self.bucket = self.options.get('bucket')
        self.prefix = self.options.get('prefix', '')
        if not self.bucket:
            logging.error('s3 provider requires "bucket"')
            return False
        session = boto3.Session()
        if session.get_credentials() is None:
            logging.error('AWS credentials not configured')
            return False
        return True

    def storage_id(self):
        prefix = f'/{self.prefix}' if self.prefix else ''
        return f's3:{self.bucket}{prefix}'

    def upload_files(self, files):
        client = boto3.client('s3')
        for f in files:
            key = os.path.join(self.prefix, os.path.basename(f))
            try:
                client.upload_file(f, self.bucket, key)
            except ClientError:
                logging.exception('S3 upload failed for %s', f)
                return False
        return True

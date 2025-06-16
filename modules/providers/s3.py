import os
import subprocess
import logging
from . import BackupProvider, _which

class S3Provider(BackupProvider):
    def verify(self):
        self.bucket = self.options.get('bucket')
        self.prefix = self.options.get('prefix', '')
        if not self.bucket:
            logging.error('s3 provider requires "bucket"')
            return False
        if _which('aws') is None:
            logging.error('aws command not found')
            return False
        return True

    def upload_files(self, files):
        for f in files:
            key = os.path.join(self.prefix, os.path.basename(f))
            cmd = ['aws', 's3', 'cp', f, f's3://{self.bucket}/{key}']
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = p.communicate()
                if p.returncode != 0:
                    logging.error('aws s3 cp failed: %s', err)
                    return False
            except Exception:
                logging.exception('aws s3 cp failed for %s', f)
                return False
        return True

import os
import subprocess
import logging
from . import BackupProvider, _which

class SFTPProvider(BackupProvider):
    def verify(self):
        self.user = self.options.get('user')
        self.host = self.options.get('host')
        self.dest = self.options.get('dest', '.')
        if not self.user or not self.host:
            logging.error('sftp provider requires "user" and "host"')
            return False
        if _which('sftp') is None:
            logging.error('sftp command not found')
            return False
        return True

    def upload_files(self, files):
        for f in files:
            cmd = ['sftp', f'{self.user}@{self.host}']
            batch = f'put {f} {self.dest}/{os.path.basename(f)}\n'
            try:
                p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = p.communicate(batch.encode())
                if p.returncode != 0:
                    logging.error('sftp failed: %s', err)
                    return False
            except Exception:
                logging.exception('sftp failed for %s', f)
                return False
        return True

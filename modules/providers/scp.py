import os
import subprocess
import logging
from . import BackupProvider, _which

class SCPProvider(BackupProvider):
    def verify(self):
        self.user = self.options.get('user')
        self.host = self.options.get('host')
        self.dest = self.options.get('dest', '.')
        if not self.user or not self.host:
            logging.error('scp provider requires "user" and "host"')
            return False
        if _which('scp') is None:
            logging.error('scp command not found')
            return False
        return True

    def upload_files(self, files):
        for f in files:
            dest = f'{self.user}@{self.host}:{self.dest}/{os.path.basename(f)}'
            cmd = ['scp', f, dest]
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = p.communicate()
                if p.returncode != 0:
                    logging.error('scp failed: %s', err)
                    return False
            except Exception:
                logging.exception('scp failed for %s', f)
                return False
        return True

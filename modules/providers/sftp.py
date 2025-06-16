import os
import subprocess
import logging
from . import BackupProvider, _which

class SFTPProvider(BackupProvider):
    name = 'sftp'
    def verify(self):
        self.user = self.options.get('user')
        self.host = self.options.get('host')
        self.dest = self.options.get('dest', '.')
        self.key = self.options.get('key')
        self.password = self.options.get('password')
        if not self.user or not self.host:
            logging.error('sftp provider requires "user" and "host"')
            return False
        if self.key and not os.path.exists(self.key):
            logging.error('SSH key %s not found', self.key)
            return False
        if self.password and _which('sshpass') is None:
            logging.error('sshpass command not found')
            return False
        if _which('sftp') is None:
            logging.error('sftp command not found')
            return False
        return True

    def storage_id(self):
        return f'sftp:{self.user}@{self.host}:{self.dest}'

    def upload_files(self, files):
        base = []
        if self.password:
            base += ['sshpass', '-p', self.password]
        sftp_cmd = ['sftp']
        if self.key:
            sftp_cmd += ['-i', self.key]
        for f in files:
            cmd = base + sftp_cmd + [f'{self.user}@{self.host}']
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

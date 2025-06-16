import os
import subprocess
import logging
from . import BackupProvider, _which

class SCPProvider(BackupProvider):
    name = 'scp'
    def verify(self):
        self.user = self.options.get('user')
        self.host = self.options.get('host')
        self.dest = self.options.get('dest', '.')
        self.key = self.options.get('key')
        self.password = self.options.get('password')
        if not self.user or not self.host:
            logging.error('scp provider requires "user" and "host"')
            return False
        if self.key and not os.path.exists(self.key):
            logging.error('SSH key %s not found', self.key)
            return False
        if self.password and _which('sshpass') is None:
            logging.error('sshpass command not found')
            return False
        if _which('scp') is None:
            logging.error('scp command not found')
            return False
        return True

    def storage_id(self):
        return f'scp:{self.user}@{self.host}:{self.dest}'

    def upload_files(self, files):
        base = []
        if self.password:
            base += ['sshpass', '-p', self.password]
        scp_cmd = ['scp']
        if self.key:
            scp_cmd += ['-i', self.key]
        for f in files:
            dest = f'{self.user}@{self.host}:{self.dest}/{os.path.basename(f)}'
            cmd = base + scp_cmd + [f, dest]
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

import os
import logging
from . import BackupProvider, _which
from modules import aws

class GlacierProvider(BackupProvider):
    """Upload archives to AWS Glacier using the aws CLI."""

    def verify(self):
        self.vault = self.options.get('vault')
        self.threads = int(self.options.get('threads', 4))
        if not self.vault:
            logging.error('glacier provider requires "vault"')
            return False
        if _which('aws') is None:
            logging.error('aws command not found')
            return False
        if not aws.isConfigured():
            return False
        return True

    def upload_files(self, files):
        cfg = {
            'glacier-vault': self.vault,
            'glacier-threads': self.threads,
            'prepdir': os.path.dirname(files[0]) if files else ''
        }
        total = sum(os.path.getsize(f) for f in files)
        names = [os.path.basename(f) for f in files]
        # Ensure vault exists (createVault will no-op if it already exists)
        if not aws.createVault(cfg):
            return False
        return aws.uploadFiles(cfg, names, total)

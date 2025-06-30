import os
import logging
import boto3
from botocore.exceptions import ClientError
from . import BackupProvider
from modules import aws

class GlacierProvider(BackupProvider):
    """Upload archives to AWS Glacier using boto3."""
    name = 'glacier'

    def verify(self):
        self.vault = self.options.get('vault')
        self.threads = int(self.options.get('threads', 4))
        if not self.vault:
            logging.error('glacier provider requires "vault"')
            return False
        if not aws.isConfigured():
            return False
        # Verify we can access Glacier
        try:
            boto3.client('glacier').describe_vault(vaultName=self.vault)
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') != 'ResourceNotFoundException':
                logging.error('Unable to access Glacier: %s', e)
                return False
        return True

    def storage_id(self):
        return f'glacier:{self.vault}'

    def get_vault(self):
        return self.vault

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

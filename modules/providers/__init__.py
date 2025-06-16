import shutil
import logging

class BackupProvider:
    """Base class for backup providers."""

    def __init__(self, **options):
        self.options = options

    def verify(self):
        """Return True if the provider configuration is valid."""
        raise NotImplementedError

    def upload_files(self, files):
        """Upload a list of files."""
        raise NotImplementedError


def _which(program):
    return shutil.which(program)

from . import sftp, s3, scp, copy

PROVIDERS = {
    'sftp': sftp.SFTPProvider,
    's3': s3.S3Provider,
    'scp': scp.SCPProvider,
    'cp': copy.CopyProvider,
}

def get_provider(cfg):
    if not cfg or 'type' not in cfg:
        raise ValueError('Provider configuration missing type')
    t = cfg['type'].lower()
    cls = PROVIDERS.get(t)
    if not cls:
        raise ValueError('Unknown provider: %s' % t)
    opts = dict(cfg)
    opts.pop('type', None)
    provider = cls(**opts)
    if not provider.verify():
        logging.error('Provider verification failed for %s', t)
        return None
    return provider

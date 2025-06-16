import os
import shutil
import logging
from . import BackupProvider, _which

class CopyProvider(BackupProvider):
    """Simple provider that copies files locally using cp."""
    def verify(self):
        dest = self.options.get('dest')
        if not dest:
            logging.error('copy provider requires "dest"')
            return False
        if not os.path.isdir(dest):
            logging.error('Destination %s does not exist', dest)
            return False
        if _which('cp') is None:
            logging.error('cp command not found')
            return False
        self.dest = dest
        return True

    def upload_files(self, files):
        for f in files:
            try:
                shutil.copy(f, os.path.join(self.dest, os.path.basename(f)))
            except Exception:
                logging.exception('Failed to copy %s', f)
                return False
        return True

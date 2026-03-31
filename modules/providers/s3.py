import os
import logging
from . import BackupProvider
from modules import aws


class S3Provider(BackupProvider):
    name = 's3'
    allowed_options = {'type', 'bucket', 'storage class'} | set(aws.PROVIDER_CONFIG_KEYS)
    _SUPPORTED_STORAGE_CLASSES = {
        'STANDARD',
        'REDUCED_REDUNDANCY',
        'STANDARD_IA',
        'ONEZONE_IA',
        'INTELLIGENT_TIERING',
        'GLACIER_IR',
        'GLACIER',
        'DEEP_ARCHIVE',
        'EXPRESS_ONEZONE',
    }

    _STORAGE_CLASS_ALIASES = {
        'standard': 'STANDARD',
        'STANDARD': 'STANDARD',
        'reduced_redundancy': 'REDUCED_REDUNDANCY',
        'reduced redundancy': 'REDUCED_REDUNDANCY',
        'REDUCED_REDUNDANCY': 'REDUCED_REDUNDANCY',
        'standard_ia': 'STANDARD_IA',
        'standard-ia': 'STANDARD_IA',
        'STANDARD_IA': 'STANDARD_IA',
        'onezone_ia': 'ONEZONE_IA',
        'onezone-ia': 'ONEZONE_IA',
        'one zone-ia': 'ONEZONE_IA',
        'ONEZONE_IA': 'ONEZONE_IA',
        'intelligent_tiering': 'INTELLIGENT_TIERING',
        'intelligent-tiering': 'INTELLIGENT_TIERING',
        'intelligent tiering': 'INTELLIGENT_TIERING',
        'INTELLIGENT_TIERING': 'INTELLIGENT_TIERING',
        'glacier_ir': 'GLACIER_IR',
        'glacier-ir': 'GLACIER_IR',
        'glacier instant retrieval': 'GLACIER_IR',
        'GLACIER_IR': 'GLACIER_IR',
        'glacier': 'GLACIER',
        'glacier flexible retrieval': 'GLACIER',
        'GLACIER': 'GLACIER',
        'deep_archive': 'DEEP_ARCHIVE',
        'deep-archive': 'DEEP_ARCHIVE',
        'deep archive': 'DEEP_ARCHIVE',
        'DEEP_ARCHIVE': 'DEEP_ARCHIVE',
        'express_onezone': 'EXPRESS_ONEZONE',
        'express-onezone': 'EXPRESS_ONEZONE',
        'express one zone': 'EXPRESS_ONEZONE',
        'EXPRESS_ONEZONE': 'EXPRESS_ONEZONE',
    }

    @classmethod
    def normalize_storage_class(cls, value):
        if not value:
            return None
        cleaned = value.strip()
        normalized = cls._STORAGE_CLASS_ALIASES.get(cleaned)
        if normalized:
            return normalized

        lowered = cleaned.lower()
        normalized = cls._STORAGE_CLASS_ALIASES.get(lowered)
        if normalized:
            return normalized

        candidate = cleaned.upper().replace('-', '_').replace(' ', '_')
        if candidate in cls._SUPPORTED_STORAGE_CLASSES:
            return candidate
        return None

    def verify(self):
        self.bucket = self.options.get('bucket')
        configured_storage_class = self.options.get('storage class')
        self.storage_class = self.normalize_storage_class(configured_storage_class)
        if not self.bucket:
            logging.error('s3 provider requires "bucket"')
            return False
        if configured_storage_class and not self.storage_class:
            logging.error('s3 provider: storage class "%s" is not supported',
                          configured_storage_class)
            return False
        aws_config = aws.extract_aws_config(self.options)
        client, err = aws.create_s3_client(aws_config)
        if err:
            logging.error('s3 provider: %s', err)
            return False
        self.client = client
        return True

    def storage_id(self):
        return f's3:{self.bucket}'

    def upload_files(self, files):
        for f in files:
            key = os.path.basename(f)
            try:
                kwargs = {}
                if self.storage_class:
                    kwargs['ExtraArgs'] = {'StorageClass': self.storage_class}
                self.client.upload_file(f, self.bucket, key, **kwargs)
            except Exception:
                logging.exception('s3 upload failed for %s', f)
                return False
        logging.info('Stored %d file(s) successfully via %s', len(files), self.storage_id())
        return True

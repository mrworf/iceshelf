import os
import logging
from botocore.exceptions import ClientError
from . import BackupProvider
from modules import aws


class S3Provider(BackupProvider):
    name = 's3'
    allowed_options = {'type', 'bucket', 'storage class', 'create'} | set(aws.PROVIDER_CONFIG_KEYS)
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
        create = self.options.get('create', 'no').strip().lower()
        if not self.bucket:
            logging.error('s3 provider requires "bucket"')
            return False
        if configured_storage_class and not self.storage_class:
            logging.error('s3 provider: storage class "%s" is not supported',
                          configured_storage_class)
            return False
        if create not in ('yes', 'no'):
            logging.error('s3 provider: create must be "yes" or "no"')
            return False
        aws_config = aws.extract_aws_config(self.options)
        client, err = aws.create_s3_client(aws_config)
        if err:
            logging.error('s3 provider: %s', err)
            return False
        self.client = client
        self.create_bucket = create == 'yes'
        self.region = aws_config.get('region')
        return True

    def storage_id(self):
        return f's3:{self.bucket}'

    def upload_files(self, files):
        if not self._ensure_bucket():
            return False
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

    @staticmethod
    def _error_code(exc):
        response = getattr(exc, 'response', None) or {}
        error = response.get('Error', {})
        code = error.get('Code')
        if code is None:
            return ''
        return str(code)

    def _bucket_exists(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except ClientError as exc:
            code = self._error_code(exc)
            if code in {'404', 'NoSuchBucket', 'NotFound'}:
                return False
            logging.error('s3 provider: unable to check bucket %s', self.bucket)
            logging.exception(exc)
            raise
        except Exception:
            logging.exception('s3 provider: unable to check bucket %s', self.bucket)
            raise

    def _create_missing_bucket(self):
        kwargs = {'Bucket': self.bucket}
        if self.region and self.region != 'us-east-1':
            kwargs['CreateBucketConfiguration'] = {
                'LocationConstraint': self.region,
            }
        try:
            self.client.create_bucket(**kwargs)
            return True
        except Exception:
            logging.exception('s3 provider: failed to create bucket %s', self.bucket)
            return False

    def _ensure_bucket(self):
        try:
            if self._bucket_exists():
                return True
        except Exception:
            return False

        if not self.create_bucket:
            logging.error('s3 provider: bucket %s does not exist and create is disabled',
                          self.bucket)
            return False

        if not self._create_missing_bucket():
            return False
        return True

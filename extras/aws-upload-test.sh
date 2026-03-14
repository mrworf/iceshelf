#!/bin/bash
# Manual test script for verifying S3 and Glacier providers.
# Requires boto3 and valid AWS credentials.

set -e

ICESHELF_DIR="$(dirname "$0")/.."
ICESHELF="$ICESHELF_DIR/iceshelf"

if ! command -v "$ICESHELF" >/dev/null 2>&1; then
  echo "Unable to locate iceshelf" >&2
  exit 1
fi

TARGET=${1:-both}

if [ -z "$S3_BUCKET" ] && [ -z "$GLACIER_VAULT" ]; then
  echo "Usage: S3_BUCKET=<bucket> GLACIER_VAULT=<vault> $0 [s3|glacier|both]" >&2
  exit 1
fi

# Display the credentials in use so the user knows what account is charged
echo "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
echo "AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}"
[ -n "$S3_BUCKET" ] && echo "S3 bucket: $S3_BUCKET"
[ -n "$GLACIER_VAULT" ] && echo "Glacier vault: $GLACIER_VAULT"

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
cd "$WORKDIR"

mkdir content tmp data done

echo "This is a test" > content/testfile

cat > config.ini <<CONF
[sources]
test=content/

[paths]
prep dir: tmp/
data dir: data/
done dir: done/

[options]
compress: no
delta manifest: yes
ignore overlimit: yes
max keep: 0
CONF

if [ "$TARGET" != "s3" ] && [ -n "$GLACIER_VAULT" ]; then
cat >> config.ini <<CONF
[provider-glacier]
type: glacier
vault: ${GLACIER_VAULT}
threads: 1
CONF
fi

if [ "$TARGET" != "glacier" ] && [ -n "$S3_BUCKET" ]; then
cat >> config.ini <<CONF
[provider-s3]
type: s3
bucket: ${S3_BUCKET}
prefix: iceshelf-test
CONF
fi

cat config.ini

"$ICESHELF" config.ini --debug



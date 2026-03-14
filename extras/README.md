# Other

This folder holds some goodies which might be useful for you.

## iceshelf.service

A systemd service file for running iceshelf

## analog-key.sh

A shell script which can transfer a GPG key into a printable form (as multiple QR codes) suitable for longterm backup. It can also take a scanned copy and restore the digital key. Finally it also has a validate mode where it simple exports, imports and confirms that the reconstituted key is identical to the one in GPGs keychain.

It's HIGHLY recommended that you make copies of the key used for iceshelf backups, since without it, any and all backed up content is lost.

## aws-upload-test.sh

A manual helper for testing the Glacier and S3 providers. It uploads a small
file using your configured AWS credentials. Provide the destination names via
`S3_BUCKET` and `GLACIER_VAULT` environment variables and optionally pass
`s3` or `glacier` as an argument to limit which provider is used.
The script prints the credentials in use so you can verify the account,
then creates a temporary backup and runs `iceshelf` with the generated
configuration. Because this may incur cloud storage costs, it is not
executed as part of CI.

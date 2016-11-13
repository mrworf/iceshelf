# Other

This folder holds some goodies which might be useful for you.

## iceshelf.service

A systemd service file for running iceshelf

## analog-key.sh

A shell script which can transfer a GPG key into a printable form (as multiple QR codes) suitable for longterm backup. It can also take a scanned copy and restore the digital key. Finally it also has a validate mode where it simple exports, imports and confirms that the reconstituted key is identical to the one in GPGs keychain.

It's HIGHLY recommended that you make copies of the key used for iceshelf backups, since without it, any and all backed up content is lost.

# iceshelf

A simple tool to allow storage of private, incremental backups using Amazon's Glacier storage. It relies entirely on open source technology, such as TAR, BZip2, GPG, SHA512, PAR2.

# Features

- Encrypts all backups using GPG private/public key
- Signs all files it uploads (tamper detection)
- Can upload separate PAR2 file for parity correction
- Supports segmentation of upload (but not of files, yet)
- Primarily designed for AWS Glacier

Due to the need to work well with Glacier, any change to a file will cause it
to reupload the same file (with the new content). This backup solution is not
meant to be used on files which change often.

It's an archiving solution for long-term storage which is what Glacier excels
at. Also the reason it's called iceshelf. To quote from wikipedia:

> An ice shelf is a thick floating platform of ice that forms where a glacier or ice sheet flows down to a coastline and onto the ocean surface

*(and yes, this would probably mean that time runs in reverse, but bear with
me, finding cool names (phun intended) for projects is not always easy)*

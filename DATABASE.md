Structure of the JSON database:

{
  "dataset" : {...},
  "backups" : {...},
"vault"   : "<name of the vault used>",
"storage" : ["<provider-id>", ...],  // destinations used for this backup
  "version" : [major, minor, revision],
  "timestamp" : <seconds since epoch>,
  "moved" : {...} (optional),
  "lastbackup" : "<name of the previous successful backup>"
}

"backups" contains:

"<YYYMMDD-HHMMSS-xxxxx>" : [
  "file1",
  "file2",
  ...
]

"dataset" contains:

"<filename with path>" : {
  "deleted" : ["<backup>", ...],  // Lists in which backups this file was deleted
  "checksum" : "<hash>",          // Currently known version (blank if currently deleted)
  "memberof" : ["<backup>", ...]  // Which backups this file exists in
}

"moved" contains:

"<new filename with path>" : {
  "reference" : "<backup>",
  "original" : "<original filename with path in <backup>>"
}

---------

Manifest:

{
  "deleted" : [...],
  "moved" : {...},
  "modified" : {...},
  "previousbackup", "<name of last successful backup>"
}

"deleted" contains:

All files which were deleted since last run

"moved" contains:

"<new filename with path>" : {
  "reference" : "<backup>",
  "original" : "<original filename with path in <backup>>"
}

"modified" contains:

"<filename with path>" : {
  "deleted" : ["<backup>", ...],  // Lists in which backups this file was deleted
  "checksum" : "<hash>",          // Currently known version (blank if currently deleted)
  "memberof" : ["<backup>", ...]  // Which backups this file exists in
}

## Version history

| Version | Changes |
|---------|---------|
| 1.0.0   | Added `version` and `timestamp` fields along with `dataset`, `backups` and `vault`. |
| 1.0.1   | Internal move detection, manifest gained `moved` entries. Database format unchanged. |
| 1.1.0   | Database now records `moved` entries and `lastbackup` of the previous run. Version key changed to an integer array. |

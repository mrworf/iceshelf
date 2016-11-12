Structure of the JSON database:

{
  "dataset" : {...},
  "backups" : {...},
  "vault"   : "<name of the vault used>",
  "version" : [major, minor, revision]
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

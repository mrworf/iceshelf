from . import helper
from subprocess import Popen, PIPE
import logging
import os
import time

def createVault(config):
  logging.info("Creating vault \"%s\"", config["glacier-vault"])
  result = glacierCommand(config, ["mkvault", config["glacier-vault"]])
  if result is None or result["code"] != 0:
    logging.error("Failed to create vault: %s", repr(result))
    return False

  logging.info("Vault created")
  return True

def uploadFiles(config, files, bytes):
  logging.info("Uploading %d files (%s) to glacier, this may take a while", len(files), helper.formatSize(bytes))
  cmd = ["upload", config["glacier-vault"]]
  for f in files:
    cmd.append(f)

  upload_start = round(time.time())
  result = glacierCommand(config, cmd)
  upload_time = max(round(time.time()) - upload_start, 1)

  if result is None or "output" not in result or "Uploaded file" not in result["output"]:
    logging.error("Failed to upload files: %s", repr(result))
    return False

  logging.info("Files uploaded @ %s", helper.formatSpeed(bytes / upload_time))
  return True

# TODO: This one should actually show output as it goes...
def glacierCommand(config, args):
  if config["glacier-config"] is None:
    logging.error("glacierCommand() called without proper settings")
    return None

  cmd = ["glacier-cmd", "-c", config["glacier-config"], "--output", "json"]
  cmd += args

  logging.debug("Glacier command: " + repr(cmd))

  p = Popen(cmd, stdout=PIPE, stderr=PIPE, cwd=config["prepdir"])
  out, err = p.communicate()
  logging.debug("Output: " + repr(out))
  logging.debug("Error : " + repr(err))
  return {"code" : p.returncode, "output" : out, "error" : err }
#  return {"code": 0}
"""
upload:
{'output': '{"Created archive with ID": "", "Archive SHA256 tree hash": "", "Uploaded file": ""}\n', 'code': 0, 'error': ''}

mkvault:
{"RequestId": "", "Location": "/5555555555/vaults/test"}

lsvault:
[{"SizeInBytes": 0, "LastInventoryDate": null, "VaultARN": "arn:aws:glacier:", "VaultName": "test", "NumberOfArchives": 0, "CreationDate": "2015-10-01T06:13:47.811Z"}]
"""

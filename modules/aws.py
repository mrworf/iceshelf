import helper
from subprocess import Popen, PIPE
import logging
import os
import time
import json
import io
import hashlib
import tempfile
import sys

def isConfigured():
  if not os.path.exists(os.path.expanduser('~/.aws/config')) or not os.path.exists(os.path.expanduser('~/.aws/credentials')):
    logging.error('AWS is not configured, please run aws tool with configure for current user')
    return False

  # Now that we know these files exists, check the contents
  hasRegion = False
  hasJSON = False
  hasCred1 = False
  hasCred2 = False
  with io.open(os.path.expanduser('~/.aws/config')) as f:
    while True:
      line = f.readline().lower()
      if 'region' in line:
        hasRegion = True
      elif 'output' in line and 'json' in line:
        hasJSON = True
      elif line == '':
        break

  with io.open(os.path.expanduser('~/.aws/credentials')) as f:
    while True:
      line = f.readline().lower()
      if 'aws_access_key_id' in line:
        hasCred1 = True
      elif 'aws_secret_access_key' in line:
        hasCred2 = True
      elif line == '':
        break

  if not hasRegion:
    logging.error('AWS configuration is missing region setting')
  if not hasJSON:
    logging.error('AWS configuration is missing output setting or it\'s not set to JSON')
  if not hasCred1:
    logging.error('AWS configuration is missing aws_access_key_id')
  if not hasCred2:
    logging.error('AWS configuration is missing aws_secret_access_key')
  if not (hasRegion and hasJSON and hasCred1 and hasCred2):
    logging.error('Please resolve issues by running aws tool with configure for current user')
    return False
  return True

def createVault(config):
  result = awsCommand(config, ['create-vault', '--vault-name', config["glacier-vault"]])
  if result is None or result["code"] != 0:
    logging.error("Failed to create vault: %s", repr(result))
    return False

  logging.info("Vault created")
  return True

def extractChunk(file, tmp, offset, size):
  with io.open(file, 'rb') as i:
    i.seek(offset)
    with io.open(tmp, 'wb') as o:
      buf = i.read(size)
      o.write(buf)
  return True

def hashFile(file):
  if not os.path.exists(file):
    return None

  h = hashlib.sha256
  blocks = []
  with io.open(file, 'rb') as f:
    while True:
      data = f.read(1024**2)
      if len(data) == 0:
        break
      v = h(data)
      blocks.append(v)

  # Produce final hash
  def recurse(hashlist):
    output = [h(h1.digest() + h2.digest())
              for h1, h2 in zip(hashlist[::2], hashlist[1::2])]
    if len(hashlist) % 2:
        output.append(hashlist[-1])
    if len(output) > 1:
        return recurse(output)
    else:
      return output[0]
  return {'blocks' : blocks, 'final' : recurse(blocks or [h(b"")])}

def uploadFile(config, prefix, file, tmpfile, withPath=False):
  hashes = hashFile(file)
  if hashes is None:
    logging.error('File %s does not exist', file)
    return False

  name = file
  if not withPath:
    name = os.path.basename(name)

  # Initiate the upload (1MB increments)
  result = awsCommand(config, ['initiate-multipart-upload', '--vault-name', config['glacier-vault'], '--archive-description', name, '--part-size', '1048576'])
  if result is None or result['code'] != 0 or 'uploadId' not in result['json']:
    logging.error('Unable to initiate upload: %s', repr(result))
    return False
  uploadId = result['json']['uploadId']

  # Start sending the file, one megabyte at a time until we have none left
  size = remain = os.path.getsize(file)
  offset = 0
  block = 0

  upload_start = round(time.time())

  # Chunk upload, 1MB chunks
  if sys.stdout.isatty():
    sys.stdout.write('%s%s, %.2f%% done\r' % (prefix, name, 0))
    sys.stdout.flush()
  while remain > 0:
    chunk = remain
    if chunk > 1024**2:
      chunk = 1024**2

    # Exract chunk into temp file for upload purpose
    if not extractChunk(file, tmpfile, offset, 1024**2):
      logging.error('Unable to extract chunk for upload')
      return False

    dataRange = 'bytes %d-%d/*' % (offset, offset + chunk - 1)
    retry = 10
    while retry > 0:
      result = awsCommand(config, ['upload-multipart-part', '--vault-name', config['glacier-vault'], '--upload-id', uploadId, '--body', tmpfile, '--range', dataRange])
      if result is not None and result['json'] is not None and 'checksum' in result['json']:
        if hashes['blocks'][block].hexdigest() != result['json']['checksum']:
          logging.error('Hash does not match, expected %s got %s.', hashes['blocks'][block].hexdigest(), result['json']['checksum'])
        else:
          break
      else:
        logging.debug('Result was: ' + repr(result))

      retry = retry - 1
      logging.warning('1MB @ %d failed to upload, retrying in %d seconds. %d tries left', offset, (10-retry)*30, retry)
      time.sleep((10-retry) * 30)

    if retry == 0:
      logging.error('Unable to upload 1MB at offset %d', offset)
      return False
    block += 1
    remain -= chunk
    offset += chunk
    if sys.stdout.isatty():
      sys.stdout.write('%s%s, %.2f%% done\r' % (prefix, name, float(offset)/float(size) * 100.0))
      sys.stdout.flush()

  if sys.stdout.isatty():
    print("")
  # Time to finalize this deal
  result = awsCommand(config, ['complete-multipart-upload', '--vault-name', config['glacier-vault'], '--upload-id', uploadId, '--checksum', hashes['final'].hexdigest(), '--archive-size', str(size)])
  if result is None or result['code'] != 0:
    logging.error('Failed to upload %s: %s', file, repr(result))
    return False

  upload_time = max(round(time.time()) - upload_start, 1)
  logging.debug('%s @ %s', file, helper.formatSpeed(size / upload_time))
  return True

def uploadFiles(config, files, bytes):
  logging.info("Uploading %d files (%s) to glacier, this may take a while", len(files), helper.formatSize(bytes))

  tf = tempfile.NamedTemporaryFile(dir='/tmp', delete=False)
  if tf is None:
    logging.error('Unable to generate temporary file')
    return False
  tmp = tf.name
  tf.close()

  i = 0
  d = 0
  for file in files:
    i += 1
    file = os.path.join(config["prepdir"], file)
    if not uploadFile(config, "(%d of %d, %.2f%%) " % (i, len(files), float(d)/float(bytes) * 100), file, tmp):
      return False
    d += os.path.getsize(file)
  os.unlink(tmp)
  return True

def awsCommand(config, args):
  if config["glacier-vault"] is None:
    logging.error("awsCommand() called without proper settings")
    return None

  cmd = ['aws', '--output', 'json', 'glacier']
  cmd += args
  cmd += ['--account-id', '-']

  #logging.debug("AWS command: " + repr(cmd))

  p = Popen(cmd, stdout=PIPE, stderr=PIPE, cwd=config["prepdir"])
  out, err = p.communicate()
  if out is None or out == "":
    logging.debug("Error : " + repr(err))

  jout = None
  try:
    jout = json.loads(out)
  except:
    logging.debug("Raw: " + repr(out))
    logging.debug("Error: " + repr(err))

  return {"code" : p.returncode, "raw" : out, 'json' : jout, "error" : err }

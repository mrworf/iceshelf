from . import helper
from subprocess import Popen, PIPE
import logging
import os
import time
import json
import io
import hashlib
import tempfile
import sys
import math

import random

import threading
from queue import Queue

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

class uploadCoordinator:
  def __init__(self, threads=4):
    self.threads = threads
    self.sent = 0
    self.began = round(time.time())
    self.exit = False
    self.queue = Queue()

  def process(self):
    self.began = round(time.time())
    for w in range(self.threads):
      t = threading.Thread(target=self.worker)
      t.daemon = True
      t.start()

  def worker(self):
    run = True
    while run and not self.exit:
      try:
        entry = self.queue.get(False)
      except:
        break
      sent = entry.work()
      if sent == -1:
        logging.error("WE FAILED!")
        run = False
        self.exit = True
      else:
        self.sent += sent
      entry.cleanup()
      self.queue.task_done()
    self.threads -= 1

  def add(self, process):
    if self.exit:
      return False
    self.queue.put(process)
    return True

  def getTime(self):
    t = round(time.time()) - self.began
    if t < 1:
      return 1
    return t

  def getSent(self):
    return self.sent

  def isDone(self):
    return self.threads == 0 | self.exit

  def finish(self):
    self.queue.join()
    return not self.exit

class uploadJob:
  def __init__(self, config, file, name, offset, size, checksum, uploadId):
    self.config = config
    self.file = file
    self.name = name
    self.offset = offset
    self.size = size
    self.checksum = checksum
    self.uploadId = uploadId

    self.retries = 10
    tf = tempfile.NamedTemporaryFile(dir='/tmp', delete=False)
    if tf is None:
      logging.error('Unable to generate temporary file')
      return -1
    self.tmpfile = tf.name
    tf.close()

  def extractChunk(self, offset, size):
    with io.open(self.file, 'rb') as i:
      i.seek(offset)
      with io.open(self.tmpfile, 'wb') as o:
        buf = i.read(size)
        o.write(buf)
    return True

  def cleanup(self):
    if os.path.exists(self.tmpfile):
      os.unlink(self.tmpfile)

  def work(self):
    # Exract chunk into temp file for upload purpose
    if not self.extractChunk(self.offset, self.size):
      logging.error('Unable to extract chunk for upload')
      return False

    dataRange = 'bytes %d-%d/*' % (self.offset, self.offset + self.size - 1)
    self.retry = self.retries
    while self.retry > 0:
      result = awsCommand(self.config, ['upload-multipart-part', '--vault-name', self.config['glacier-vault'], '--cli-input-json', '{"uploadId": "' + self.uploadId + '"}', '--body', self.tmpfile, '--range', dataRange])
      if result is not None and result['json'] is not None and 'checksum' in result['json']:
        if self.checksum != result['json']['checksum']:
          logging.error('Hash does not match, expected %s got %s.', self.checksum, result['json']['checksum'])
        else:
          break
      else:
        if 'RequestTimeoutException' in result['error']:
          logging.warn('Timeout')
        else:
          logging.debug('Result was: ' + repr(result))

      self.retry = self.retry - 1
      logging.warning('%s @ %d failed to upload, retrying in %d seconds. %d tries left', helper.formatSize(self.size), self.offset, (10-self.retry)*30, self.retry)
      time.sleep((10-self.retry) * 30)

    if self.retry == 0:
      logging.error('Unable to upload %s at offset %d', helper.formatSize(self.size), self.offset)
      return -1
    return self.size

def hashFile(file, chunkSize):
  if not os.path.exists(file):
    return None

  h = hashlib.sha256
  blocks = []
  final = []
  # Do it in 1MB chunks, regardless of chunkSize
  with io.open(file, 'rb') as f:
    while True:
      data = f.read(1024**2)
      if len(data) == 0:
        break
      v = h(data)
      blocks.append(v)

  # Produce final hash
  def recurse(hashlist, size):
    # We've reached the chunksize we need, so store a copy before we continue
    if size == chunkSize:
      for o in hashlist:
        final.append(o)

    output = [h(h1.digest() + h2.digest())
              for h1, h2 in zip(hashlist[::2], hashlist[1::2])]
    if len(hashlist) % 2:
        output.append(hashlist[-1])

    if len(output) > 1:
        return recurse(output, size*2)
    else:
      return output[0]

  result = {'blocks' : final, 'final' : recurse(blocks or [h(b"")], 1024**2)}
  return result

def uploadFile(config, prefix, file, bytesDone=0, bytesTotal=0, withPath=False):
  if not os.path.exists(file):
    logging.error('File %s does not exist', file)
    return False

  name = file
  if not withPath:
    name = os.path.basename(name)
  size = remain = os.path.getsize(file)

  # Due to limit of 10000 parts in an upload, we need to make it all fit
  chunkSize = size / 10000
  if chunkSize <= 1024**2:
    chunkSize = 1024**2
  else:
    # Make sure it's a power of two
    factor = math.ceil(float(chunkSize) / float(1024**2))
    chunkSize = int((1024**2) * factor)
    chunkSize -= 1
    chunkSize |= chunkSize >> 1
    chunkSize |= chunkSize >> 2
    chunkSize |= chunkSize >> 4
    chunkSize |= chunkSize >> 8
    chunkSize |= chunkSize >> 16
    chunkSize += 1
  logging.debug('Using chunksize of %s based on size (%s) of the file we\'re uploading', helper.formatSize(chunkSize), helper.formatSize(size))

  hashes = hashFile(file, chunkSize)
  if hashes is None:
    logging.error('Unable to hash file %s', file)
    return False

  # Initiate the upload
  result = awsCommand(config, ['initiate-multipart-upload', '--vault-name', config['glacier-vault'], '--archive-description', name, '--part-size', str(chunkSize)])
  if result is None or result['code'] != 0 or 'uploadId' not in result['json']:
    logging.error('Unable to initiate upload: %s', repr(result))
    return False
  uploadId = result['json']['uploadId']

  # Start sending the file, one megabyte at a time until we have none left
  offset = 0
  block = 0
  work = uploadCoordinator(config['glacier-threads'])

  # Queue up all the work
  while remain > 0:
    chunk = remain
    if chunk > chunkSize:
      chunk = chunkSize

    job = uploadJob(config, file, name, offset, chunk, hashes['blocks'][block].hexdigest(), uploadId)
    work.add(job)

    block += 1
    remain -= chunk
    offset += chunk

  # Wait for it...
  work.process()
  while not work.isDone():
    time.sleep(1)
    if sys.stdout.isatty():
      # Extra spaces at the end to clear remnants when numbers change
      if work.getSent() > 0 and work.getTime() > 0:
        timerem = ", " + helper.formatTime((float(bytesTotal) - float(bytesDone + work.getSent())) / (work.getSent() / work.getTime())) + " remaining"
      else:
        timerem = ""
      sys.stdout.write('%s%s @ %s, %.2f%% done (%.2f%% total%s)          \r' % (
        prefix,
        name,
        helper.formatSpeed(work.getSent() / work.getTime()),
        float(work.getSent())/float(size) * 100.0,
        float(bytesDone + work.getSent())/float(bytesTotal) * 100.0,
        timerem
        )
      )
      sys.stdout.flush()
  if sys.stdout.isatty():
    sys.stdout.write('\n')
    sys.stdout.flush()

  if not work.finish():
    logging.error('Failed to upload the file, aborting')
    # Note! Should use JSON since plain arguments seems to not work
    awsCommand(config, ['abort-multipart-upload', '--vault-name', config['glacier-vault'], '--cli-input-json', '{"uploadId": "' + uploadId + '"}'])
    return False

  # Time to finalize this deal
  result = awsCommand(config, ['complete-multipart-upload', '--vault-name', config['glacier-vault'], '--cli-input-json', '{"uploadId": "' + uploadId + '"}', '--checksum', hashes['final'].hexdigest(), '--archive-size', str(size)])
  if result is None or result['code'] != 0:
    logging.error('Unable to complete upload of %s: %s', file, repr(result))
    return False
  return True

def uploadFiles(config, files, bytes):
  logging.info("Uploading %d files (%s) to glacier, this may take a while", len(files), helper.formatSize(bytes))

  i = 0
  d = 0
  for file in files:
    i += 1
    file = os.path.join(config["prepdir"], file)
    if not uploadFile(config, "(%d of %d) " % (i, len(files)), file, d, bytes):
      return False
    d += os.path.getsize(file)
  return True

def awsCommand(config, args, dry=False):
  if config["glacier-vault"] is None:
    logging.error("awsCommand() called without proper settings")
    return None

  # Fake it until you make it
  if dry:
    time.sleep(random.randint(1, 50) / 10)
    return  {"code" : 0, "raw" : '', 'json' : {'checksum' : 'something', 'uploadId' : 'someid' }, "error" : '' }

  cmd = ['aws', '--output', 'json', 'glacier']
  cmd += args
  cmd += ['--account-id', '-']

  #logging.debug("AWS command: " + repr(cmd))

  p = Popen(cmd, stdout=PIPE, stderr=PIPE, cwd=config["prepdir"])
  out, err = p.communicate()

  jout = None
  try:
    jout = json.loads(out)
  except:
    pass

  if out is None or out == "":
    logging.debug("Error : " + repr(err))
    logging.debug('Cmd: ' + repr(cmd))

  return {"code" : p.returncode, "raw" : out, 'json' : jout, "error" : err }

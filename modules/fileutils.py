import os.path
import os
import hashlib
import shutil
import logging
from subprocess import Popen, PIPE

def copy(src, dst):
  try:
    shutil.copy(src, dst)
  except OSError as e:
    if e.errno == 1:
      logging.debug("Unable to change permissons on copied file: %s" % dst)
    else:
      logging.exception("Error copying file: %s" % src)
      raise

def deleteTree(tree, include_self=False):
  for root, dirs, files in os.walk(tree, topdown=False):
    for name in files:
      os.remove(os.path.join(root, name))
    for name in dirs:
      os.rmdir(os.path.join(root, name))
  if include_self:
    os.rmdir(tree)

def generateParity(filename, level):
  if level is 0:
    return False
  cmd = ["par2", "create", "-r"+str(level), filename]
  p = Popen(cmd, stdout=PIPE, stderr=PIPE)
  out, err = p.communicate()
  if p.returncode != 0:
    print "Command: " + repr(cmd)
    print "Output: " + out
    print "Error : " + err
    print "Code  : " + str(p.returncode)
  return p.returncode == 0

def repairParity(filename):
  cmd = ["par2", "r", filename]
  p = Popen(cmd, stdout=PIPE, stderr=PIPE)
  out, err = p.communicate()
  if p.returncode != 0:
    print "Command: " + repr(cmd)
    print "Output: " + out
    print "Error : " + err
    print "Code  : " + str(p.returncode)
  else:
    # Remove the corrupt file
    if filename[-5:] == '.par2':
      os.unlink(filename[0:-5] + '.1')
    else:
      os.unlink(filename + '.1')
  return p.returncode == 0

def hashFile(file, shatype):
  sha = hashlib.new(shatype)
  with open(file, 'rb') as fp:
    for chunk in iter(lambda: fp.read(32768), b''):
      sha.update(chunk)
  return sha.hexdigest()

def sumSize(path, files):
  result = 0
  for f in files:
    result += os.path.getsize(os.path.join(path, f))
  return result

def generateFilelist(path, output):
  files = os.listdir(path)
  with open(output, 'wb') as lst:
    for f in files:
      lst.write('{}  {}\n'.format(hashFile(os.path.join(path, f), 'sha1'), f))

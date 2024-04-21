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
  if level == 0:
    return False
  cmd = ["par2", "create", "-r"+str(level), filename]
  p = Popen(cmd, stdout=PIPE, stderr=PIPE)
  out, err = p.communicate()
  if p.returncode != 0:
    print("Command: " + repr(cmd))
    print("Output: " + out)
    print("Error : " + err)
    print("Code  : " + str(p.returncode))
  return p.returncode == 0

def repairParity(filename):
  cmd = ["par2", "r", filename]
  p = Popen(cmd, stdout=PIPE, stderr=PIPE)
  out, err = p.communicate()
  if p.returncode != 0:
    print("Command: " + repr(cmd))
    print("Output: " + out)
    print("Error : " + err)
    print("Code  : " + str(p.returncode))
  else:
    # Remove the corrupt file
    if filename[-5:] == '.par2':
      os.unlink(filename[0:-5] + '.1')
    else:
      os.unlink(filename + '.1')
  return p.returncode == 0

def hashFile(file, shatype, includeType=False):
  sha = hashlib.new(shatype)
  with open(file, 'rb') as fp:
    for chunk in iter(lambda: fp.read(32768), b''):
      sha.update(chunk)
  if includeType:
    return sha.hexdigest() + ":" + shatype
  return sha.hexdigest()

def hashChanged(filename, oldChecksum, newChecksum):
  (hashNew, typeNew) = newChecksum.split(':', 2)

  # See if it's using the new method of hashes
  if ':' in oldChecksum:
    (hashOld, typeOld) = oldChecksum.split(':', 2)
    if typeOld != typeNew:
      hashNew = hashFile(filename, typeOld)
    return hashOld != hashNew

  # It's the old kind, see if this matches
  if len(oldChecksum) != len(hashNew):
    l = len(oldChecksum)
    hashNew = None # Forces a differences if we can't resolve
    if l == 32:
      hashNew = hashFile(filename, "md5")
    elif l == 40:
      hashNew = hashFile(filename, "sha1")
    elif l == 56:
      hashNew = hashFile(filename, "sha224")
    elif l == 64:
      hashNew = hashFile(filename, "sha256")
    elif l == 96:
      hashNew = hashFile(filename, "sha384")
    elif l == 128:
      hashNew = hashFile(filename, "sha512")
    else:
      logging.warn("Unable to determine hashing method used, returning changed (old hash: " + oldChecksum + ")")

  return oldChecksum != hashNew

def sumSize(path, files):
  result = 0
  for f in files:
    result += os.path.getsize(os.path.join(path, f))
  return result

def generateFilelist(path, output):
  files = os.listdir(path)
  with open(output, 'w', encoding="utf-8") as lst:
    for f in files:
      lst.write('{}  {}\n'.format(hashFile(os.path.join(path, f), 'sha1'), f))

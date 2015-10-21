import os.path

def shouldCompress():
  chance = int((currentOp["compressable"] * 100) / currentOp["filesize"])
  return chance >= 20

def willCompress(filename):
  (ignore, ext) = os.path.splitext(filename)
  return ext[1:].lower() not in incompressable

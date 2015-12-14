import ConfigParser
import sys
import os.path
import logging
import os

setting = {
  "encrypt": None,
  "encrypt-pw": None,
  "sign": None,
  "sign-pw": None,
  "parity": 0,
  "manifest": True,
  "use-sha": True,
  "sha-type": "sha1",
  "maxsize": 0,
  "prepdir": "/tmp/",
  "datadir": "data/",
  "sources": {},
  "exclude": [],
  "persuasive": True,
  "compress": True,
  "compress-force": False,
  "ignore-overlimit": False,
  "extra-ext" : None,
  "donedir": None,
  "maxkeep": 0,
  "glacier-config" : None,
  "glacier-vault" : None,
  "prefix" : "",
  "detect-move": False,
}

def parse(filename):
  config = ConfigParser.ConfigParser()
  # Some sane defaults

  config.add_section("sources")

  config.add_section("paths")
  config.set("paths", "prep dir", "/tmp/")
  config.set("paths", "data dir", "data/")
  config.set("paths", "prefix", "")

  config.add_section("options")
  config.set("options", "max size", "0")
  config.set("options", "change method", "meta")
  config.set("options", "delta manifest", "yes")
  config.set("options", "compress", "yes")
  config.set("options", "incompressible", "")
  config.set("options", "persuasive", "no")
  config.set("options", "detect move", "no")

  config.add_section("glacier")
  config.set("glacier", "config", "")
  config.set("glacier", "vault", "")

  config.add_section("security")
  config.set("security", "encrypt", "")
  config.set("security", "sign", "")
  config.set("security", "encrypt phrase", "")
  config.set("security", "sign phrase", "")
  config.set("security", "add parity", "0")


  # Read user settings
  config.read(filename)

  # Validate the config
  if len(config.options("sources")) == 0:
    logging.error("You don't have any sources defined")
    return None

  if config.get("security", "encrypt") != "":
    setting["encrypt"] = config.get("security", "encrypt")
  if config.get("security", "encrypt phrase") != "":
    setting["encrypt-pw"] = config.get("security", "encrypt phrase")
  if config.get("security", "sign") != "":
    setting["sign"] = config.get("security", "sign")
  if config.get("security", "sign phrase") != "":
    setting["sign-pw"] = config.get("security", "sign phrase")

  if config.get("options", "delta manifest").lower() not in ["yes", "no"]:
    logging.error("Delta Manifest has to be yes/no")
    return None
  elif config.get("options", "delta manifest").lower() == "no":
    setting["manifest"] = False

  if config.get("options", "persuasive").lower() not in ["yes", "no"]:
    logging.error("persuasive has to be yes/no")
    return None
  elif config.get("options", "persuasive").lower() == "no":
    setting["persuasive"] = False

  if config.get("options", "ignore overlimit").lower() not in ["yes", "no"]:
    logging.error("ignore overlimit has to be yes/no")
    return None
  elif config.get("options", "ignore overlimit").lower() == "yes":
    setting["ignore-overlimit"] = True

  if config.get("options", "compress").lower() not in ["force", "yes", "no"]:
    logging.error("compress has to be yes/no")
    return None
  elif config.get("options", "compress").lower() == "no":
    setting["compress"] = False
  elif config.get("options", "compress").lower() == "force":
    setting["compress-force"] = True

  if config.get("options", "change method").lower() not in [ "data", "sha1", "sha256", "sha512"]:
    logging.error("Change method has to be data, sha1, sha256 or sha512 (meta is deprecated)")
    return None
  else:
    setting["use-sha"] = True
    setting["sha-type"] = config.get("options", "change method").lower()
    if setting["sha-type"] == "data":
      setting["sha-type"] = "sha1"

  if config.get("options", "incompressible"):
    setting["extra-ext"] = config.get("options", "incompressible").split()

  if config.get("options", "max keep").isdigit():
    setting["maxkeep"] = config.getint("options", "max keep")
  elif config.get("options", "max keep") is not "":
    logging.error("Max keep should be a number or empty")
    return None

  if config.has_option("options", "prefix") and config.get("options", "prefix") != "":
    setting["prefix"] = config.get("options", "prefix")

  if config.get("options", "detect move").lower() not in ["yes", "no"]:
    logging.error("detect move has to be yes or no")
  elif config.get("options", "detect move").lower() == "yes":
    if not setting["use-sha"]:
      logging.error("You cannot use \"detect move\" with \"change method\" set to \"meta\"")
      return None
    setting["detect-move"] = True

  if config.get("options", "max size").isdigit() and config.getint("options", "max size") > 0:
    setting["maxsize"] = config.getint("options", "max size")
  elif not config.get("options", "max size").isdigit() and config.get("options", "max size") != "":
    unit = config.get("options", "max size").lower()[-1:]
    value = config.get("options", "max size")[:-1]
    if not value.isdigit():
      logging.error("Max size has to be a number and may contain a unit suffix")
      return None
    value = int(value, 10)

    if unit == 'k':
      value *= 1024
    elif unit == 'm':
      value *= 1048576
    elif unit == 'g':
      value *= 1073741824
    elif unit == 't':
      value *= 1099511627776
    else:
      logging.error("Max size has to be a number and may contain a unit suffix")
      sys.exit(1)
    setting["maxsize"] = value

  if not config.get("security", "add parity").isdigit() or config.getint("security", "add parity") > 100 or config.getint("security", "add parity") < 0:
    logging.error("Parity ranges from 0 to 100, " + config.get("security", "add parity") + " is invalid")
    return None
  elif config.getint("security", "add parity") > 0:
    setting["parity"] = config.getint("security", "add parity")
    if setting["maxsize"] > 34359738367 or setting["maxsize"] == 0:
      logging.warn("max size is limited to 32GB when using parity, changing setting accordingly")
      setting["maxsize"] = 34359738367 # (actually 32GB - 1 byte)

  if config.get("paths", "prep dir") == "" or not os.path.isdir(config.get("paths", "prep dir")):
    logging.error("Preparation dir doesn't exist")
    return None
  else:
    setting["prepdir"] = os.path.join(config.get("paths", "prep dir"), "iceshelf")

  if config.get("paths", "data dir") == "" or not os.path.isdir(config.get("paths", "data dir")):
    logging.error("Data dir doesn't exist")
    return None
  else:
    setting["datadir"] = config.get("paths", "data dir")

  if config.get("paths", "done dir") != "" and not os.path.isdir(config.get("paths", "done dir")):
    logging.error("Done dir doesn't exist")
    return None
  elif config.get("paths", "done dir") != "":
    setting["donedir"] = config.get("paths", "done dir")

  # Check that all sources are either directories or files
  for x in config.options("sources"):
    if config.get("sources", x) == "":
      logging.error("Source " + x + " is empty")
      return None
    if not os.path.exists(config.get("sources", x)):
      logging.error("Source \"%s\" points to a non-existing entry \"%s\"", x, config.get("sources", x))
      return None
    setting["sources"][x] = config.get("sources", x)

  # Glacier options
  if config.has_section("glacier"):
    if config.has_option("glacier", "config"):
      if config.get("glacier", "config") != "" and not os.path.exists(config.get("glacier", "config")):
        logging.error("Glacier config not found")
        return None
      elif config.get("glacier", "config") != "":
        setting["glacier-config"] = config.get("glacier", "config")
        if not config.has_option("glacier", "vault") or config.get("glacier", "vault") == "":
          logging.error("Glacier vault not defined")
          return None
        setting["glacier-vault"] = config.get("glacier", "vault")

  # Load exlude rules (if any)
  if config.has_section("exclude"):
    for x in config.options("exclude"):
      v = config.get("exclude", x).strip()
      if v == "" :
        logging.error("Exclude filter %s is empty", x)
        return None
      if v[0] == '|':
        logging.debug("Loading external exclusion rules from %s", v[1:])
        try:
          with open(v[1:], "r") as f:
            for line in f:
              line = line.strip()
              if len(line) == 0:
                continue
              if line[0] == '|':
                logging.error("Cannot reference external exclusion files from an external exclusion file (%s): %s", v[1:], line)
                return None
              elif line[0] == '#':
                continue
              setting["exclude"].append(line)
        except:
          logging.exception("Error loading external exclusion file \"%s\"", v[1:])
          raise
      else:
        setting["exclude"].append(v)
  if len(setting["exclude"]) == 0:
    setting["exclude"] = None

  # Lastly, check that required software is installed and available on the path
  if setting["parity"] > 0 and which("par2") is None:
    logging.error("To use parity, you must have par2 installed")
    return None
  if (setting["sign"] is not None or setting["encrypt"] is not None) and which("gpg") is None:
    logging.error("To use encryption/signature, you must have gpg installed")
    return None
  if setting["glacier-config"] is not None and which("glacier-cmd") is None:
    logging.error("To use glacier backup, you must have glacier-cmd installed")
    return None

  return setting

# From http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
#
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

def isExcluded(f):
  if setting["exclude"] is None:
    return False

  fl = f.lower()
  for v in setting["exclude"]:
    ov=v
    invert = False
    fromend = False
    contain = False
    match = False
    lessthan = None
    morethan = None
    if v[0] != "\\":
      if v[0] == "!":
        invert = True
        v = v[1:]
      if v[0] != "\\":
        if v[0] == "*":
          fromend = True
          v = v[1:]
        elif v[0] == "?":
          contain = True
          v = v[1:]
        elif v[0] == "<":
          v = v[1:]
          if v.isdigit():
            lessthan = int(v)
          else:
            logging.error("\"Less than\" exclude rule can only have digits")
            sys.exit(2)
        elif v[0] == ">":
          v = v[1:]
          if v.isdigit():
            morethan = int(v)
          else:
            logging.error("\"More than\" exclude rule can only have digits")
            sys.exit(2)
      else: # No special filter at the start (after invert)
        v = v[1:]
    else: # No special filter at the start
      v = v[1:]

    if morethan or lessthan:
      # Expensive, we need to stat
      i = os.stat(f)
      if morethan is not None and i.st_size > morethan:
        match = True
      elif lessthan is not None and i.st_size < lessthan:
        match = True
    else:
      match = (fromend and fl.endswith(v)) or (contain and v in fl) or (fl.startswith(v))

    if match:
      if invert: # Special case, it matches, so stop processing, but DON'T EXCLUDE IT
        logging.debug("Rule \"%s\" matched \"%s\", not excluded", ov, f)
        return False
      else: # Normal case, matched, so should be excluded
        logging.debug("Rule \"%s\" matched \"%s\", excluded", ov, f)
        return True
  return False


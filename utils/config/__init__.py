import ConfigParser
import sys
import os.path
import logging

def parse(filename):
  result = {
    "encrypt": None,
    "encrypt-pw": None,
    "sign": None,
    "sign-pw": None,
    "parity": 0,
    "manifest": True,
    "use-sha": False,
    "maxsize": 0,
    "prepdir": "/tmp/",
    "datadir": "data/",
    "sources": {},
    "persuasive": True,
    "compress": True,
    "compress-force": False,
    "ignore-overlimit": False,
    "extra-ext" : None
  }
  config = ConfigParser.ConfigParser()
  # Some sane defaults

  config.add_section("sources")

  config.add_section("paths")
  config.set("paths", "prep dir", "/tmp/")
  config.set("paths", "data dir", "data/")

  config.add_section("options")
  config.set("options", "max size", "0")
  config.set("options", "change method", "meta")
  config.set("options", "delta manifest", "yes")
  config.set("options", "compress", "yes")
  config.set("options", "incompressible", "")
  config.set("options", "persuasive", "no")

  config.add_section("glacier")
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
    result["encrypt"] = config.get("security", "encrypt")
  if config.get("security", "encrypt phrase") != "":
    result["encrypt-pw"] = config.get("security", "encrypt phrase")
  if config.get("security", "sign") != "":
    result["sign"] = config.get("security", "sign")
  if config.get("security", "sign phrase") != "":
    result["sign-pw"] = config.get("security", "sign phrase")

  if config.get("options", "delta manifest").lower() not in ["yes", "no"]:
    logging.error("Delta Manifest has to be yes/no")
    return None
  elif config.get("options", "delta manifest").lower() == "no":
    result["manifest"] = False

  if config.get("options", "persuasive").lower() not in ["yes", "no"]:
    logging.error("persuasive has to be yes/no")
    return None
  elif config.get("options", "persuasive").lower() == "no":
    result["persuasive"] = False

  if config.get("options", "ignore overlimit").lower() not in ["yes", "no"]:
    logging.error("ignore overlimit has to be yes/no")
    return None
  elif config.get("options", "ignore overlimit").lower() == "yes":
    result["ignore-overlimit"] = True

  if config.get("options", "compress").lower() not in ["force", "yes", "no"]:
    logging.error("compress has to be yes/no")
    return None
  elif config.get("options", "compress").lower() == "no":
    result["compress"] = False
  elif config.get("options", "compress").lower() == "force":
    result["compress-force"] = True

  if config.get("options", "change method").lower() not in ["meta", "data"]:
    logging.error("Change method has to be data or meta")
    return None
  elif config.get("options", "change method").lower() == "data":
    result["use-sha"] = True

  if config.get("options", "incompressible"):
    result["extra-ext"] = config.get("options", "incompressible").split()

  if config.get("options", "max size").isdigit() and config.getint("options", "max size") > 0:
    result["maxsize"] = config.getint("options", "max size")
  elif not config.get("options", "max size").isdigit():
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
    result["maxsize"] = value

  if not config.get("security", "add parity").isdigit() or config.getint("security", "add parity") > 100 or config.getint("security", "add parity") < 0:
    logging.error("Parity ranges from 0 to 100, " + config.get("security", "add parity") + " is invalid")
    return None
  else:
    result["parity"] = config.getint("security", "add parity")
    if result["maxsize"] > 34359738367:
      logging.warn("max size is limited to 32GB when using parity, changing setting accordingly")
    result["maxsize"] = 34359738367 # (actually 32GB - 1 byte)

  if config.get("paths", "prep dir") == "" or not os.path.isdir(config.get("paths", "prep dir")):
    logging.error("Preparation dir doesn't exist")
    return None
  else:
    result["prepdir"] = os.path.join(config.get("paths", "prep dir"), "iceshelf")

  if config.get("paths", "data dir") == "" or not os.path.isdir(config.get("paths", "data dir")):
    logging.error("Data dir doesn't exist")
    return None
  else:
    result["datadir"] = config.get("paths", "data dir")

  # Finally, check that all sources are either directories or files
  for x in config.options("sources"):
    if config.get("sources", x) == "":
      logging.error("Source " + x + " is empty")
      return None
    if not os.path.exists(config.get("sources", x)):
      logging.error("Source \"%s\" points to a non-existing entry \"%s\"", x, config.get("sources", x))
      return None
    result["sources"][x] = config.get("sources", x)

  return result

import ConfigParse
import sy
import os.pat
import loggin
import o
import aw

setting = 
  "encrypt": None
  "encrypt-pw": None
  "sign": None
  "sign-pw": None
  "parity": 0
  "manifest": True
  "use-sha": True
  "sha-type": "sha1"
  "maxsize": 0
  "prepdir": "backup/inprogress/"
  "datadir": "backup/metadata/"
  "sources": {}
  "exclude": []
  "persuasive": True
  "compress": True
  "compress-force": False
  "ignore-overlimit": False
  "extra-ext" : None
  "donedir": "backup/done/"
  "maxkeep": 0
  "glacier-vault" : None
  "prefix" : ""
  "detect-move": False
  "create-paths": False
  "skip-empty": False
  "encrypt-manifest" : True
  "create-filelist" : True
  "checkupdate" : False
  "custom-pre" : None
  "custom-post" : None


def getVersion()
  return [1,1,0

def isCompatible(version)
  ""
  Checks if the version (x.y.z) is compatible with our
  The general rule is that as long as only Z changes
  it remains compatible
  ""
  try
    if len(version) is not 3
      return Fals
    c = getVersion(
    return c[0] == version[0] and c[1] == version[1] and c[2] >= version[2
  except
    return Fals

def parse(filename, onlysecurity=False)
  config = ConfigParser.ConfigParser(
  # Some sane default

  config.add_section("sources"

  config.add_section("paths"
  config.set("paths", "prep dir", "backup/inprogress/"
  config.set("paths", "data dir", "backup/metadata/"
  config.set("paths", "done dir", "backup/done/"
  config.set("paths", "prefix", ""
  config.set("paths", "create paths", "no"

  config.add_section("options"
  config.set("options", "max size", "0"
  config.set("options", "delta manifest", "yes"
  config.set("options", "compress", "yes"
  config.set("options", "incompressible", ""
  config.set("options", "persuasive", "no"
  config.set("options", "detect move", "no"
  config.set("options", "skip empty", "no"
  config.set("options", "ignore overlimit", "no"
  config.set("options", "change method", "sha1"
  config.set("options", "max keep", "0"
  config.set("options", "create filelist", "yes"
  config.set("options", "check update", "no"

  config.add_section("glacier"
  config.set("glacier", "vault", ""

  config.add_section("custom"
  config.set("custom", "pre command", ""
  config.set("custom", "post command", ""

  config.add_section("security"
  config.set("security", "encrypt", ""
  config.set("security", "sign", ""
  config.set("security", "encrypt phrase", ""
  config.set("security", "sign phrase", ""
  config.set("security", "add parity", "0"
  config.set("security", "encrypt manifest", "yes"


  # Read user setting
  config.read(filename

  # Validate the confi
  if len(config.options("sources")) == 0 and not onlysecurity
    logging.error("You don't have any sources defined"
    return Non

  if config.get("security", "encrypt") != ""
    setting["encrypt"] = config.get("security", "encrypt"
  if config.get("security", "encrypt phrase") != ""
    setting["encrypt-pw"] = config.get("security", "encrypt phrase"
  if config.get("security", "sign") != ""
    setting["sign"] = config.get("security", "sign"
  if config.get("security", "sign phrase") != ""
    setting["sign-pw"] = config.get("security", "sign phrase"
  if config.get("security", "encrypt manifest").lower() not in ["yes", "no"]
    logging.error("encrypt manifest has to be yes/no"
    return Non
  elif config.get("security", "encrypt manifest").lower() == "no"
    setting["encrypt-manifest"] = Fals

  # Exit early if we don't need more than securit
  if onlysecurity
    return settin

  if config.get("options", "delta manifest").lower() not in ["yes", "no"]
    logging.error("Delta Manifest has to be yes/no"
    return Non
  elif config.get("options", "delta manifest").lower() == "no"
    setting["manifest"] = Fals

  if config.get("options", "create filelist").lower() not in ["yes", "no"]
    logging.error("create filelist has to be yes/no"
    return Non
  elif config.get("options", "create filelist").lower() == "no"
    setting["create-filelist"] = Fals

  if config.get("options", "persuasive").lower() not in ["yes", "no"]
    logging.error("persuasive has to be yes/no"
    return Non
  elif config.get("options", "persuasive").lower() == "no"
    setting["persuasive"] = Fals

  if config.get("options", "check update").lower() not in ["yes", "no"]
    logging.error("check update has to be yes/no"
    return Non
  elif config.get("options", "check update").lower() == "yes"
    setting["checkupdate"] = Tru

  if config.get("options", "ignore overlimit").lower() not in ["yes", "no"]
    logging.error("ignore overlimit has to be yes/no"
    return Non
  elif config.get("options", "ignore overlimit").lower() == "yes"
    setting["ignore-overlimit"] = Tru

  if config.get("options", "compress").lower() not in ["force", "yes", "no"]
    logging.error("compress has to be yes/no"
    return Non
  elif config.get("options", "compress").lower() == "no"
    setting["compress"] = Fals
  elif config.get("options", "compress").lower() == "force"
    setting["compress-force"] = Tru

  if config.get("options", "skip empty").lower() not in ["yes", "no"]
    logging.error("skip empty has to be yes/no"
    return Non
  elif config.get("options", "skip empty").lower() == "yes"
    setting["skip-empty"] = Tru

  if config.get("options", "change method").lower() not in [ "data", "sha1", "sha256", "sha512"]
    logging.error("Change method has to be data, sha1, sha256 or sha512 (meta is deprecated)"
    return Non
  else
    setting["use-sha"] = Tru
    setting["sha-type"] = config.get("options", "change method").lower(
    if setting["sha-type"] == "data"
      logging.debug("Sha type was data, default to sha1"
      setting["sha-type"] = "sha1
    logging.debug("Using sha-type: " + setting["sha-type"]

  if config.get("options", "incompressible")
    setting["extra-ext"] = config.get("options", "incompressible").split(

  if config.get("options", "max keep").isdigit()
    setting["maxkeep"] = config.getint("options", "max keep"
  elif config.get("options", "max keep") is not ""
    logging.error("Max keep should be a number or empty"
    return Non

  if config.has_option("options", "prefix") and config.get("options", "prefix") != ""
    setting["prefix"] = config.get("options", "prefix"

  if config.get("options", "detect move").lower() not in ["yes", "no"]
    logging.error("detect move has to be yes or no"
  elif config.get("options", "detect move").lower() == "yes"
    if not setting["use-sha"]
      logging.error("You cannot use \"detect move\" with \"change method\" set to \"meta\""
      return Non
    setting["detect-move"] = Tru

  if config.get("options", "max size").isdigit() and config.getint("options", "max size") > 0
    setting["maxsize"] = config.getint("options", "max size"
  elif not config.get("options", "max size").isdigit() and config.get("options", "max size") != ""
    unit = config.get("options", "max size").lower()[-1:
    value = config.get("options", "max size")[:-1
    if not value.isdigit()
      logging.error("Max size has to be a number and may contain a unit suffix"
      return Non
    value = int(value, 10

    if unit == 'k'
      value *= 102
    elif unit == 'm'
      value *= 104857
    elif unit == 'g'
      value *= 107374182
    elif unit == 't'
      value *= 109951162777
    else
      logging.error("Max size has to be a number and may contain a unit suffix"
      sys.exit(1
    setting["maxsize"] = valu

  if not config.get("security", "add parity").isdigit() or config.getint("security", "add parity") > 100 or config.getint("security", "add parity") < 0
    logging.error("Parity ranges from 0 to 100, " + config.get("security", "add parity") + " is invalid"
    return Non
  elif config.getint("security", "add parity") > 0
    setting["parity"] = config.getint("security", "add parity"
    if setting["maxsize"] > 34359738367 or setting["maxsize"] == 0
      logging.debug("max size is limited to 32GB when using parity, changing \"max size\" setting"
      setting["maxsize"] = 34359738367 # (actually 32GB - 1 byte

  if config.get("paths", "create paths").lower() not in ["yes", "no"]
    logging.error("create paths has to be yes or no"
  elif config.get("paths", "create paths").lower() == "yes"
    setting["create-paths"] = Tru

  if config.get("paths", "prep dir") == ""
    logging.error("Preparation dir cannot be empty"
  elif not os.path.isdir(config.get("paths", "prep dir")) and setting["create-paths"] == False
    logging.error("Preparation dir doesn't exist"
    return Non
  else
    setting["prepdir"] = os.path.join(config.get("paths", "prep dir"), "iceshelf"
    if setting["create-paths"]
      try
        os.makedirs(setting["prepdir"]
      except OSError as e
        if e.errno is not 17
          logging.exception("Cannot create preparation dir"
          return Non

  if config.get("paths", "data dir") == ""
    logging.error("Data dir cannot be empty"
  elif not os.path.isdir(config.get("paths", "data dir")) and setting["create-paths"] == False
    logging.error("Data dir doesn't exist"
    return Non
  else
    setting["datadir"] = config.get("paths", "data dir"
    if setting["create-paths"]
      try
        os.makedirs(setting["datadir"]
      except OSError as e
        if e.errno is not 17
          logging.exception("Cannot create data dir"
          return Non

  if config.get("paths", "done dir") == ""
    setting["donedir"] = Non
  elif not os.path.isdir(config.get("paths", "done dir")) and setting["create-paths"] == False
    logging.error("Done dir doesn't exist"
    return Non
  elif config.get("paths", "done dir") != ""
    setting["donedir"] = config.get("paths", "done dir"
    if setting["create-paths"]
      try
        os.makedirs(setting["donedir"]
      except OSError as e
        if e.errno is not 17
          logging.exception("Cannot create done dir"
          return Non

  # Check that all sources are either directories or file
  for x in config.options("sources")
    if config.get("sources", x) == ""
      logging.error("Source " + x + " is empty"
      return Non
    if not os.path.exists(config.get("sources", x))
      logging.error("Source \"%s\" points to a non-existing entry \"%s\"", x, config.get("sources", x)
      return Non
    setting["sources"][x] = config.get("sources", x

  # Glacier option
  if config.has_section("glacier")
    if config.has_option("glacier", "config")
      logging.error('Glacier config is deprecated. Please use official AWS tool from Amazon instead'
      return Non
  if config.has_option("glacier", "vault") and config.get("glacier", "vault") != ""
    setting["glacier-vault"] = config.get("glacier", "vault"
    # Make sure AWS is configured
    if not aws.isConfigured()
      return Non
    if which('aws') is None
      logging.error('AWS command line tool not in path. Is it installed?'
      return Non

  # Custom options (not in-use yet
  if config.has_section("custom")
    if config.get("custom", "pre command") != "" and not os.path.exists(config.get("custom", "pre command"))
      logging.error("Can't find pre-command \"%s\"" % config.get("custom", "pre command")
      return Non
    elif config.get("custom", "pre command") != ""
      setting["custom-pre"] = config.get("custom", "pre command"
    if config.get("custom", "post command") != "" and not os.path.exists(config.get("custom", "post command"))
      logging.error("Can't find post-command \"%s\"" % config.get("custom", "post command")
      return Non
    elif config.get("custom", "post command") != ""
      setting["custom-pre"] = config.get("custom", "post command"

  # Load exlude rules (if any
  if config.has_section("exclude")
    for x in config.options("exclude")
      v = config.get("exclude", x).strip(
      if v == "" 
        logging.error("Exclude filter %s is empty", x
        return Non
      if v[0] == '|'
        logging.debug("Loading external exclusion rules from %s", v[1:]
        try
          with open(v[1:], "r") as f
            for line in f
              line = line.strip(
              if len(line) == 0
                continu
              if line[0] == '|'
                logging.error("Cannot reference external exclusion files from an external exclusion file (%s): %s", v[1:], line
                return Non
              elif line[0] == '#'
                continu
              setting["exclude"].append(line
        except
          logging.exception("Error loading external exclusion file \"%s\"", v[1:]
          rais
      else
        setting["exclude"].append(v
  if len(setting["exclude"]) == 0
    setting["exclude"] = Non

  # Lastly, check that required software is installed and available on the pat
  if setting["parity"] > 0 and which("par2") is None
    logging.error("To use parity, you must have par2 installed"
    return Non
  if (setting["sign"] is not None or setting["encrypt"] is not None) and which("gpg") is None
    logging.error("To use encryption/signature, you must have gpg installed"
    return Non

  return settin

# From http://stackoverflow.com/questions/377017/test-if-executable-exists-in-pytho

def which(program)
    def is_exe(fpath)
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK

    fpath, fname = os.path.split(program
    if fpath
        if is_exe(program)
            return progra
    else
        for path in os.environ["PATH"].split(os.pathsep)
            path = path.strip('"'
            exe_file = os.path.join(path, program
            if is_exe(exe_file)
                return exe_fil

    return Non

def isExcluded(f)
  if setting["exclude"] is None
    return Fals

  fl = f.lower(
  for v in setting["exclude"]
    ov=
    invert = Fals
    fromend = Fals
    contain = Fals
    match = Fals
    lessthan = Non
    morethan = Non
    if v[0] != "\\"
      if v[0] == "!"
        invert = Tru
        v = v[1:
      if v[0] != "\\"
        if v[0] == "*"
          fromend = Tru
          v = v[1:
        elif v[0] == "?"
          contain = Tru
          v = v[1:
        elif v[0] == "<"
          v = v[1:
          if v.isdigit()
            lessthan = int(v
          else
            logging.error("\"Less than\" exclude rule can only have digits"
            sys.exit(2
        elif v[0] == ">"
          v = v[1:
          if v.isdigit()
            morethan = int(v
          else
            logging.error("\"More than\" exclude rule can only have digits"
            sys.exit(2
      else: # No special filter at the start (after invert
        v = v[1:
    else: # No special filter at the star
      v = v[1:

    if morethan or lessthan
      # Expensive, we need to sta
      i = os.stat(f
      if morethan is not None and i.st_size > morethan
        match = Tru
      elif lessthan is not None and i.st_size < lessthan
        match = Tru
    else
      match = (fromend and fl.endswith(v)) or (contain and v in fl) or (fl.startswith(v)

    if match
      if invert: # Special case, it matches, so stop processing, but DON'T EXCLUDE I
        logging.debug("Rule \"%s\" matched \"%s\", not excluded", ov, f
        return Fals
      else: # Normal case, matched, so should be exclude
        logging.debug("Rule \"%s\" matched \"%s\", excluded", ov, f
        return Tru
  return Fals


#!/bin/bash
#
# Ice Shelf for Glacier is a incremental backup tool which will upload any
# changes to glacier. It can both encrypt and/or provide extra parity data
# to make sure that the data is secure and has some measure of protection
# against data corruption.
#
# Each backup can therefore be restored individually at the expense of
# extra storage in Glacier.
#
###############################################################################

# Quick-check before we allow bad things to happen
if [ -z "${BASH_VERSINFO}" ]; then
  echo "ERROR: You must execute this script with BASH"
  exit 255
fi
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "Sorry, this script requires version 4 or newer of BASH"
  exit 255
fi

# Override the following using your custom .iceshelf file in $HOME
#
# Which folders to backup (exact structure is recreated in archive)
SOURCE=()
# Temporary storage for creating archive, must have enough space for all
# content, you may want to use MAX_SIZE to avoid running out of space.
PREP_DIR=/tmp
# Folder to store metadata needed to track changes
DATA_DIR=backup/
# Method of detecting a change: data or meta
# data uses sha512 of the content to detect changes
# meta uses filesize + datestamp to detect changes
CHANGE_METHOD=meta
# Which GPG key to encode content with, empty means NO encryption or signatures
# (Requires GPG installed)
GPG_KEY=
# Sign only? Normally if GPG is available, all data is encrypted and signed and
# any companionfiles are signed. This option will disable encryption and only
# sign the files.
SIGN_ONLY=no
# Include delta manifest in upload, useful if you lost all data locally
DELTA_MANIFEST=yes
# Amazon Glacier vault to use for backups
GLACIER_VAULT=
# Parity option, 0 = No parity, if a bit flipped, no backup, 5 = 5% can be
# corrupt, 50 = 50%, 100 = 100% (Requires par2 and will force an automatic
# split at 32GB due to Par2 limitations)
ADD_PARITY=0
# Max size of incremental archive. This is defined in MB (1048576 bytes) and
# will cause the operation to stop if the archive reaches this size BEFORE
# compression (so resulting file may be smaller). If there is more to backup,
# the script will return with exit code 20 so it can be run again until it
# returns 0. Empty or zero means no limit.
#
# Note!
# Use of parity will enforce a max limit of 32GB, unless you've set it lower.
#
# WARNING! You must have sufficient temporary space to hold the complete
#          archive before it has been uploaded.
MAX_SIZE=
#
###############################################################################

function dryout() {
  if [ ${DRYRUN} ] ; then
    echo DRYRUN: $1
  fi
}

function loginfo() {
  echo "INFO: $1"
}

function logerr() {
  echo "ERROR: $1"
}

function logwarn() {
  echo "WARN: $1"
}

function checkGPG() {
  return 1
}

function checkPAR2() {
  which par2 >/dev/null 2>/dev/null
  return $?
}

function usage() {
  echo "Ice Shelf Backup for Glacier"
  echo "¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨¨"
  echo " -h          This help"
  echo " -n          Dry-run, do most of the work, but don't upload the result"
  echo " -c <config> Use a different config file instead of the default ~/.iceshelf"
}

function cleanfilename() {
  RESULT=
  EXTRA=
  if [ -f "${1}" ]; then
    EXTRA="$(basename "${1}")"
    eval pushd "$(dirname "${1}")" >/dev/null 2>/dev/null
  else
    eval pushd "${1}" >/dev/null 2>/dev/null
  fi
  if [ $? -gt 0 ]; then
    return 1
  fi
  RESULT="$(pwd)/${EXTRA}"
  popd >/dev/null 2>/dev/null

  echo ${RESULT}
  return 0
}

function checksum() {
  if [ "${CHANGE_METHOD}" == "data" ]; then
    SUM=($(sha512sum "$1"))
    SUM="${SUM[0]}"
  elif [ "${CHANGE_METHOD}" == "meta" ]; then
    SUM="$(stat -c%Y%s "$1")"
  else
    logerr "CHANGEMETHOD ${CHANGE_METHOD} is not supported"
    exit 4
  fi
  echo ${SUM}
}

function hasChanged() {
  RESULT=0
  SUM="$(checksum "$1")"

  if [ -z "${OLDCHECKSUMS["$1"]}" ] || [ "${OLDCHECKSUMS["$1"]}" != "${SUM}" ]; then
    NEWCHECKSUMS["$1"]="${SUM}"
    return 0
  fi
  return 1
}

function traverse() {
  find "${1}" -type f -print0 | while IFS= read -r -d '' FILE
  do
    SIZE="$(stat -c%s "${FILE}")"
    if [ ${MAX_SIZE} -gt 0 -a ${SIZE} -gt ${MAX_SIZE} ]; then
      logerr "Unable to continue, source file is larger than max size"
      return 20
    fi
    if [ ${MAX_SIZE} -gt 0 -a $(( ${SIZE} + ${FS} )) -gt ${MAX_SIZE} ]; then
      logwarn "Reached max size for archive, going to next step"
      return 20
    fi

    if hasChanged "${FILE}" ; then
      echo "${FILE} has changed"
      FC=$((${FC} + 1))
      FS=$((${FS} + ${SIZE}))
    fi
  done
}

# Defaults, do not change
DRYRUN=0
CONFIG=~/.iceshelf

# Parse options
#
while getopts c:hn opt
do
  case "$opt" in
    c) CONFIG=$OPTARG;;
    h) usage;;
    n) DRYRUN=1;;
  esac
done

# Load local config
CONFIG="$(cleanfilename "${CONFIG}")"
if [ -f "${CONFIG}" ]; then
  source "${CONFIG}"
else
  echo "ERROR: Could not load config from ${CONFIG}"
  exit 255
fi

# Validate config settings
#
if [ ${#SOURCE[@]} -eq 0 ]; then
  echo "ERROR: No source directories was provided"
  exit 1
fi

if [ ! -z ${GPG_KEY} -a checkGPG ]; then
  echo "ERROR: You don't have GPG installed"
  exit 2
elif [ ! -f ${GPG_KEY} ]; then
  echo "ERROR: GPG Key does not exist"
  exit 2
else
  GPG_KEY="$(cleanfilename "${GPG_KEY}")"
fi

if [ ! -z "${ADD_PARITY}" ] && [ ${ADD_PARITY} -lt 0 -o ${ADD_PARITY} -gt 100 ]; then
  echo "ERROR: Invalid ADD_PARITY setting, either leave it empty or provide a value from 0 to 100"
  exit 3
fi
if [ "${ADD_PARITY}" == "" ]; then # Convenience
  ADD_PARITY=0
fi

if [ ${ADD_PARITY} -gt 0 ] && ! checkPAR2; then
  echo "ERROR: You don't have PAR2 installed, cannot add parity"
  exit 3
fi

if [ ! -z "${DATA_DIR}" ]; then
  DATA_DIR="$(cleanfilename "${DATA_DIR}/")"
  if [ $? -ne 0 ] || [ ! -d "${DATA_DIR}" ]; then
    logerr "Data directory doesn't exist"
    exit 5
  fi
fi

if [ ! -z "${MAX_SIZE}" ]; then
  if [ "${MAX_SIZE}" -eq "${MAX_SIZE}" ] 2>/dev/null; then
    true
  else
    case "${MAX_SIZE: -1}" in
      k) MAX_SIZE=$((${MAX_SIZE:0: -1} * 1024));;
      K) MAX_SIZE=$((${MAX_SIZE:0: -1} * 1024));;
      m) MAX_SIZE=$((${MAX_SIZE:0: -1} * 1024 * 1024));;
      M) MAX_SIZE=$((${MAX_SIZE:0: -1} * 1024 * 1024));;
      g) MAX_SIZE=$((${MAX_SIZE:0: -1} * 1024 * 1024 * 1024));;
      G) MAX_SIZE=$((${MAX_SIZE:0: -1} * 1024 * 1024 * 1024));;
    esac
  fi
  if [ "${MAX_SIZE}" -eq "${MAX_SIZE}" ] 2>/dev/null; then
    true
  else
    logerr "MAX_SIZE has to be a number"
    exit 6
  fi
else
  MAX_SIZE=0
fi
if [ $ADD_PARITY -gt 0 -a $MAX_SIZE -gt 34359738368 ]; then
  logwarn "When creating parity, max size is limited to 32GB"
  MAX_SIZE=34359738368
fi

for D in "${SOURCE[@]}"; do
  OD="${D}"
  D="$(cleanfilename "${D}")"
  if [ $? -ne 0 ] || [ ! -d "${D}" -a ! -f "${D}" ]; then
    echo "ERROR: ${OD} is not a directory or file"
    exit 1
  fi
done

# Generate a unique filename for this session, we use YYYYMMDD-HHMMSS-nnnnnnnn in UTC
BASENAME="$(date -u +%Y%m%d-%H%M%S-%N)"

# Prep our array with checksum data
declare -A OLDCHECKSUMS
if [ -f "${DATA_DIR}checksum.lst" ]; then
  loginfo "Loading existing checksums"
  source "${DATA_DIR}checksum.lst"
fi
declare -A NEWCHECKSUMS

# Try our hand at iterating...
loginfo "Traversing the source directories, "

FC=0
FS=0
for D in "${SOURCE[@]}"; do
  D="$(cleanfilename "${D}")"

  find "${D}" -type f -print0 | while IFS= read -r -d '' FILE
  do
    echo FILE: $FILE
    SIZE="$(stat -c%s "${FILE}")"
    if [ ${MAX_SIZE} -gt 0 -a ${SIZE} -gt ${MAX_SIZE} ]; then
      logerr "Unable to continue, source file is larger than max size"
      RESULT=20
      break
    fi
    if [ ${MAX_SIZE} -gt 0 -a $(( ${SIZE} + ${FS} )) -gt ${MAX_SIZE} ]; then
      logwarn "Reached max size for archive, going to next step"
      RESULT=20
      break
    fi

    SUM="$(checksum "$FILE")"

    if [ -z "${OLDCHECKSUMS["$FILE"]}" ] || [ "${OLDCHECKSUMS["$FILE"]}" != "${SUM}" ]; then
      NEWCHECKSUMS["$FILE"]="${SUM}"
      FC=$((${FC} + 1))
      FS=$((${FS} + ${SIZE}))
    fi
  done

  echo RESULT: ${RESULT}

  if [ ${RESULT} -eq 20 ]; then
    loginfo "More data to backup but quota filled"
    break
  fi
done

if [ ${RESULT} -eq 20 ]; then
  echo "File Count: $FC"
  echo "File Size : $FS"
  echo ""
  echo "List of entries: "
  for X in "${!OLDCHECKSUMS[@]}"; do
    # Ignore items which are in our new list...
    if [ -z "${NEWCHECKSUMS["${X}"]}" ]; then
      echo "OLD: ${X} = ${OLDCHECKSUMS["${X}"]}"
    fi
  done
  for X in "${!NEWCHECKSUMS[@]}"; do
    echo "NEW: ${X} = ${NEWCHECKSUMS["${X}"]}"
    OLDCHECKSUMS["${X}"]="${NEWCHECKSUMS["${X}"]}"
  done

  # Do it in steps, we don't want to fail in the middle
  declare -p OLDCHECKSUMS > "${DATA_DIR}checksum.lst_new"
  mv "${DATA_DIR}checksum.lst_new" "${DATA_DIR}checksum.lst"
fi
exit ${RESULT}
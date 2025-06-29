#!/bin/bash

# First, make sure we're standing inside the testsuite area
cd "$(dirname "$0")"

ICESHELF=../../iceshelf
COUNT=0

# Removes old data and creates fresh
function cleanup() {
  rm -rf compare data tmp content done  >/dev/null 2>/dev/null
  rm config_* >/dev/null 2>/dev/null
}

function initialize() {
  # Clean and prep
  cleanup
  mkdir data tmp content done compare

  # Generate content
  # First, bunch of files
  for FILE in a b c d e f g h i j k l m n o p q r s t u v w x y z åäö éùü ø Hörbücher " "; do
  	dd if=/dev/zero of=content/${FILE} bs=1024 count=1 2>/dev/null
    FOLDER="folder-${FILE}"
    mkdir "content/${FOLDER}"
    for FILE2 in a b c åäö éùü " " ø; do
      dd if=/dev/zero of="content/${FOLDER}/${FILE2}" bs=1024 count=1 2>/dev/null
    done
  done
  # Next folders with files
}

# Takes an INI file and ensures sections are only defined once
#
# Param 1: Filename of the INI file
#
merge_sections() {
  local filename=$1
  awk -F'=' '
    /^\[.*\]$/ {
      if (section != $0 && section) {
        print section
        for (key in keys) {
          if (keys[key] != "") {
            print key "=" keys[key]
          } else {
            print key
          }
        }
        delete keys
      }
      section=$0
      next
    }
    /^$/ { next }  # Skip blank lines
    /^#/ { next }  # Skip comments
    {
      if ($1 in keys) {
        next
      } else {
        keys[$1]=$2
      }
    }
    END {
      print section
      for (key in keys) {
        if (keys[key] != "") {
          print key "=" keys[key]
        } else {
          print key
        }
      }
    }
  ' "$filename" > "${filename}.tmp" && mv "${filename}.tmp" "$filename"
}
# Creates a configuration file
#
# Param 1: Name of the config file, always prefixed with "config_"
# Param 2: sources, additional config parameters (supports escaping)
# Param 3: paths, additional config parameters (supports escaping)
# Param 4: options, additional config parameters (supports escaping)
# Param 5: sections, additional config parameters (supports escaping)
#
# NOTE! Don't forget section when using parameter 5!
#
function generateConfig() {
  cat >> "config_$1" << EOF
[sources]
test=content/
$(echo -e "$2")
[paths]
prep dir: tmp/
data dir: data/
done dir: done/
$(echo -e "$3")
[options]
delta manifest: yes
compress: no
persuasive: yes
ignore overlimit: no
incompressible:
max keep: 0
detect move: yes
$(echo -e "$4")
$(echo -e "$5")
EOF

  # Ensure sections are unique
  merge_sections "config_$1"

}

function lastFolder() {
  F=$(ls -1t done/ | head -n1)
  echo "done/$F/"
}

function lastArchive() {
  T=$(ls -1rt done/ | tail -1)
  TT=$(ls -1rt done/$T | grep tar | grep -v par)
  echo "done/$T/$TT"
}

# Runs an iceshelf session, first checking if there is any changes.
# If no changes are found, it fails
#
# Param 1: Name of the test
# Param 2: Run --changes ? skip = no, nochange = expect no changes, change = expect changes
# Param 3: Optional script (pretest() and posttest())
# Param 4: Configfile to use
# Param 5: List of file remaining in compare
# Param 6+ sent verbaitum to iceshelf
#
# Special variables that test can override:
#  OPT_SUCCESSRET Default zero, this is the return code expected from iceshelf.
#  OPT_IGNORECOMP Default false, if true skips directory comparison.
#
# All changes to these variables are reset at end of runTest() call
#
function runTest() {
  ERROR=true # Catch all
  let "COUNT+=1"
  printf "Test #%03d: %s\n" ${COUNT} "$1"

  # Create functions
  eval "$3"

  if [ "$(type -t pretest)" == "function" ]; then
    RESULT="$(pretest)"
    if [ $? -ne 0 ]; then
      echo "=== Pretest failed: $RESULT"
      return 255
    fi
    unset -f pretest
  fi

  if [ ! -f config_$4 ]; then
    echo "=== Config \"config_$4\" does not exist"
    return 255
  fi

  if [ "$2" != "skip" ]; then
    RESULT1="$(${ICESHELF} 2>&1 config_$4 --debug --changes)"
    RET=$?
    if [ $RET -ne 1 -a "$2" == "change" ]; then
      echo "=== Iceshelf didn't detect changes (was expected to detect changed)"
      echo "$RESULT1"
      return 255
    fi
    if [ $RET -ne 0 -a "$2" == "nochange" ]; then
      echo "=== Iceshelf detected changes (was expected to not have changes)"
      echo "$RESULT1"
      return 255
    fi
  fi

  RESULT2="$(${ICESHELF} 2>&1 config_$4 --debug ${@:6})"
  if [ $? -ne $OPT_SUCCESSRET ]; then
    echo "=== Iceshelf failed:"
    echo "$RESULT2"
    return 255
  fi

  # The magic part, we unpack into compare so we can diff things...
  ARCHIVE="$(lastArchive)"
  ORIGINAL="${ARCHIVE}"
  if [ -f "${ARCHIVE}" ]; then

    # See if there is parity and then check that it's ok
    if [ -f "${ARCHIVE}.par2" ]; then
      dd if=/dev/urandom of="${ARCHIVE}" seek=5 bs=1 count=5 conv=notrunc >/dev/null 2>/dev/null
      par2repair "${ARCHIVE}" >/dev/null
      if [ $? -ne 0 ]; then
        echo "ERROR: Parity is corrupt or insufficient, unable to repair file ${ORIGINAL}"
        return 255
      fi
    fi

    GPGERR=0
    rm tmp/file.tar >/dev/null 2>/dev/null
    rm tmp/file.tar.gpg >/dev/null 2>/dev/null
    if echo "$ARCHIVE" | grep -q "gpg.sig" ; then
      GPGOUTPUT="$(gpg -q --no-tty --batch --pinentry-mode loopback --passphrase test --output tmp/file.tar.gpg --decrypt "${ARCHIVE}" 2>&1)"
      GPGERR=$?
      ARCHIVE=tmp/file.tar.gpg
    fi
    if [ $GPGERR -ne 0 ]; then
      echo "ERROR: GPG was unable to process ${ORIGINAL}"
      echo "$GPGOUTPUT"
      return 255
    fi

    if echo "$ARCHIVE" | grep -q gpg ; then
      GPGOUTPUT="$(gpg -q --no-tty --batch --pinentry-mode loopback --passphrase test --output tmp/file.tar --decrypt "${ARCHIVE}" 2>&1)"
      GPGERR=$?
      ARCHIVE=tmp/file.tar
    elif echo "$ARCHIVE" | grep -q sig ; then
      GPGOUTPUT="$(gpg -q --no-tty --batch --pinentry-mode loopback  --passphrase test --output tmp/file.tar --decrypt "${ARCHIVE}" 2>&1)"
      GPGERR=$?
      ARCHIVE=tmp/file.tar
    fi

    if [ $GPGERR -ne 0 ]; then
      echo "ERROR: GPG was unable to process ${ORIGINAL}"
      echo "$GPGOUTPUT"
      return 255
    fi

    if echo "$ARCHIVE" | grep -q bz2 ; then
      tar xfj "${ARCHIVE}" -C compare/ --overwrite
    else
      tar xf "${ARCHIVE}" -C compare/ --overwrite
    fi
  fi
  if [ $? -ne 0 ]; then
    echo "Failed decompressing ${ARCHIVE} (${ORIGINAL})"
    return 255
  fi

  FAILED=false
  if ! $OPT_IGNORECOMP; then
    DIFF=$(diff -r content compare/content)
    if [ $? -eq 0 ]; then
      DIFF=""
    fi
    if [ "$5" != "" ]; then
      if [ "${5:0:1}" == "^" ]; then
        if ! [[ "${DIFF}" =~ $5 ]]; then
          FAILED=true
        fi
      elif [ "${DIFF}" != "$5" ]; then
        FAILED=true
      fi
    elif [ "${DIFF}" != "" ]; then
      FAILED=true
    fi
  fi

  if $FAILED ; then
    echo "=== FAILED! Diff is not matching expectations for ${ORIGINAL}:"
    echo "'$DIFF'"
    echo "=== Expected:"
    echo "'$5'"
    echo "=== Iceshelf output:"
    echo "$RESULT2"
    echo "=== Contents of folder: content/"
    ls -laR content/
    echo "=== Contents of folder: compare/content/"
    ls -laR compare/content/
    return 255
  fi

  if [ "$(type -t posttest)" == "function" ]; then
    RESULT="$(posttest)"
    if [ $? -ne 0 ]; then
      echo "=== FAILED! Posttest failed:"
      echo "$RESULT"
      echo "=== Iceshelf output:"
      echo "$RESULT2"
      echo "=== Contents of folder: content/"
      ls -laR content/
      echo "=== Contents of folder: compare/content/"
      ls -laR compare/content/
      return 255
    fi
    unset -f posttest
  fi

  # Final step, sync content with compare
  rsync -avr --delete content/ compare/content/ 2>/dev/null >/dev/null
  ERROR=false
  OPT_SUCCESSRET=0
  OPT_IGNORECOMP=false
  return 0
}

function hasGPGconfig() {
  gpg --list-secret-keys 2>/dev/null | grep test@test.test >/dev/null 2>/dev/null
  return $?
}

if hash par2 ; then
  VARIATIONS=("normal" "parity")
else
  echo 'Note! PAR2 configuration not detected'
  echo 'To enable PAR2 testing (parity support), please install par2 tools.'
  VARIATIONS=("normal")
fi

# See if user has installed the testkey
if hash gpg ; then
  HASKEY=false
  if ! hasGPGconfig; then
    echo "Importing test-key for test usage"
    RESULT="$(gpg 2>&1 --no-tty --batch --pinentry-mode loopback --passphrase test --fast-import test_key.*)"
    RESULT2="$(echo "010034E91082BF022DBAF1FEA00E5EDACC9D1828:6:" | gpg 2>&1 --import-ownertrust)"
    if hasGPGconfig ; then
      HASKEY=true
    else
      echo "=== ERROR: Unable to import GPG key for testing, encryption will not be tested"
      echo -e "Result 1:\n$RESULT"
      echo -e "Result 2:\n$RESULT2"
      exit 255
    fi
  else
    HASKEY=true
  fi

  if $HASKEY ; then
    ADD=()
    for I in "${VARIATIONS[@]}"; do
      ADD+=("$I,encrypted" "$I,signed" "$I,encrypted,signed")
    done
    for I in "${ADD[@]}"; do
      VARIATIONS+=($I)
    done
  fi
fi

if [ "$1" == "short" ]; then
  echo "Running normal use-case only! NOT A COMPLETE TEST RUN!"
  VARIATIONS=("normal")
fi

# Runs through ALL the versions...
ERROR=false
OPT_SUCCESSRET=0
OPT_IGNORECOMP=false
for VARIANT in "${VARIATIONS[@]}"; do
  EXTRAS="[security]"
  if [[ "$VARIANT" == *"encrypted"* ]]; then
    EXTRAS="$EXTRAS\nencrypt: test@test.test\nencrypt phrase: test\n"
  fi
  if [[ "$VARIANT" == *"signed"* ]]; then
    EXTRAS="$EXTRAS\nsign: test@test.test\nsign phrase: test\n"
  fi
  if [[ "$VARIANT" == *"parity"* ]]; then
    EXTRAS="$EXTRAS\nadd parity: 5\n"
  fi

  echo "...Running suite using variation ${VARIANT}..."

  initialize

  # Param 1: Name of the config file, always prefixed with "config_"
  # Param 2: sources, additional config parameters (supports escaping)
  # Param 3: paths, additional config parameters (supports escaping)
  # Param 4: options, additional config parameters (supports escaping)
  # Param 5: sections, additional config parameters (supports escaping)
  #
  # NOTE! Don't forget section when using parameter 5!


  generateConfig regular     '' '' '' "$EXTRAS"
  generateConfig prefix      '' '' "prefix: prefixed-\n" "$EXTRAS"
  generateConfig filelist    '' '' "create filelist: yes\n" "$EXTRAS"
  generateConfig encryptmani '' '' '' "[security]\nencrypt manifest: yes\n$EXTRAS"
  generateConfig changehash  '' '' "change method: sha256\n" "$EXTRAS"
  generateConfig maxsize     '' '' "max size: 1\n" "$EXTRAS"

  # First, make sure NO test uses the same case-number, that's an AUTO FAIL!
  ALL_CASES="$(ls -1 tests/ | wc --lines)"
  UNI_CASES="$(ls -1 tests/ | cut -c 1-3 | wc --lines)"
  if [ "${ALL_CASES}" != "${UNI_CASES}" ]; then
    echo "=== ERROR: Cannot have two cases with the same sequential number!"
    ls -la tests/
    exit 255
  fi

  while read TESTCASE; do
    source "tests/$TESTCASE"
    if $ERROR ; then
      break
    fi
  done  < <(ls -1 tests/)
  if $ERROR ; then
    break
  fi
done

if $ERROR ; then
  echo -e "\nTest failed, output directories preserved for analysis"
  exit 255
else
  echo -e "\nAll tests ended successfully"
  cleanup
  exit 0
fi

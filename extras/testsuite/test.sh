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

# Creates a configuration file
#
# Param 1: Name of the config file, always prefixed with "config_"
# Param 2: additional config parameters (supports escaping)
#
# NOTE! Don't forget section when adding items!
#
function generateConfig() {
  echo >"config_$1" -e "$2"
  cat >> "config_$1" << EOF
[sources]
test=content/
[paths]
prep dir: tmp/
data dir: data/
done dir: done/
[options]
max size:
change method: data
delta manifest: yes
compress: no
persuasive: yes
ignore overlimit: no
incompressible:
max keep: 0
detect move: yes
EOF
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
# Param 2: Run --changes ? If non-empty, it's skipped
# Param 3: Optional script (pretest() and posttest())
# Param 4: Configfile to use
# Param 5: List of file remaining in compare
# Param 6+ sent verbaitum to iceshelf
#
function runTest() {
  let "COUNT+=1"
  printf "Test #%03d: %s\n" ${COUNT} "$1"

  # Create functions
  eval "$3"

  if [ "$(type -t pretest)" == "function" ]; then
    RESULT="$(pretest)"
    if [ $? -ne 0 ]; then
      echo "Pretest failed: $RESULT"
      exit 255
    fi
    unset -f pretest
  fi

  if [ "$2" == "" ]; then
    RESULT="$(${ICESHELF} 2>&1 config_$4 --changes)"
    if [ $? -ne 1 ]; then
      echo "Test failed: Didn't detect changes"
      echo "$RESULT"
      exit 255
    fi
  fi

  RESULT="$(${ICESHELF} 2>&1 config_$4 ${@:6})"
  if [ $? -ne 0 ]; then
    echo "Test failed:"
    echo "$RESULT"
    exit 255
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
        exit 255
      fi
    fi

    GPGERR=0
    rm tmp/file.tar >/dev/null 2>/dev/null
    rm tmp/file.tar.gpg >/dev/null 2>/dev/null
    if echo "$ARCHIVE" | grep -q "gpg.sig" ; then
      gpg -q --no-tty --no-use-agent --batch --output tmp/file.tar.gpg --decrypt "${ARCHIVE}" 2>/dev/null >/dev/null
      GPGERR=$?
      ARCHIVE=tmp/file.tar.gpg
    fi
    if [ $GPGERR -ne 0 ]; then
      echo "ERROR: GPG was unable to process ${ORIGINAL}"
      exit 255
    fi

    if echo "$ARCHIVE" | grep -q gpg ; then
      gpg -q --no-tty --no-use-agent --batch --passphrase test --output tmp/file.tar --decrypt "${ARCHIVE}" 2>/dev/null >/dev/null
      GPGERR=$?
      ARCHIVE=tmp/file.tar
    elif echo "$ARCHIVE" | grep -q sig ; then
      gpg -q --no-tty --no-use-agent --batch --output tmp/file.tar --decrypt "${ARCHIVE}" 2>/dev/null >/dev/null
      GPGERR=$?
      ARCHIVE=tmp/file.tar
    fi

    if [ $GPGERR -ne 0 ]; then
      echo "ERROR: GPG was unable to process ${ORIGINAL}"
      exit 255
    fi

    if echo "$ARCHIVE" | grep -q bz2 ; then
      tar xfj "${ARCHIVE}" -C compare/ --overwrite
    else
      tar xf "${ARCHIVE}" -C compare/ --overwrite
    fi
  fi
  if [ $? -ne 0 ]; then
    echo "Failed decompressing ${ARCHIVE} (${ORIGINAL})"
    exit 255
  fi

  DIFF=$(diff -r content compare/content)
  if [ $? -eq 0 ]; then
    DIFF=""
  fi
  FAILED=false
  if [ "$5" != "" ]; then
    if [ "${DIFF}" != "$5" ]; then
      FAILED=true
    fi
  elif [ "${DIFF}" != "" ]; then
    FAILED=true
  fi

  if $FAILED ; then
    echo "=== FAILED! Diff is not matching expectations for ${ORIGINAL}:"
    echo "$DIFF"
    echo "=== Contents of folder: content/ (now)"
    ls -laR content/
    echo "=== Contents of folder: content/ (before)"
    cat /tmp/before_content.txt
    echo "=== Contents of folder: compare/content/ (now)"
    ls -laR compare/content/
    echo "=== Contents of folder: compare/content/ (before)"
    cat /tmp/before_compare.txt
    exit 255
  fi

  if [ "$(type -t posttest)" == "function" ]; then
    RESULT="$(posttest)"
    if [ $? -ne 0 ]; then
      echo "Posttest failed: $RESULT"
      exit 255
    fi
    unset -f posttest
  fi

  if [ "Move file and copy the same as well" == "$1" ]; then
    return 0
  fi

  # Before we sync, log folder structure
  ls -laR content/ >/tmp/before_content.txt
  ls -laR compare/content/ >/tmp/before_compare.txt

  # Final step, sync content with compare
  #rsync -avr --delete content/ compare/content/ 2>/dev/null >/dev/null
  rm -rf compare/content || exit 255
  cp -dpr content compare/ || exit 255
}

function hasGPGconfig() {
  gpg --list-keys 2>/dev/null | grep test@test.test >/dev/null 2>/dev/null
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
if ! hasGPGconfig; then
  echo 'Note! GPG configuration not detected.'
  echo 'To enable GPG support testing, install GPG and create a key with "test@test.test", passphrase "test"'
else
  ADD=()
  for I in "${VARIATIONS[@]}"; do
    ADD+=("$I,encrypted" "$I,signed" "$I,encrypted,signed")
  done
  for I in "${ADD[@]}"; do
    VARIATIONS+=($I)
  done
fi

if [ "$1" == "short" ]; then
  echo "Running normal use-case only! NOT A COMPLETE TEST RUN!"
  VARIATIONS=("encrypted")
fi

# Runs through ALL the versions...
for V in "${VARIATIONS[@]}"; do
  EXTRAS="[security]"
  if [[ "$V" == *"encrypted"* ]]; then
    EXTRAS="$EXTRAS\nencrypt: test@test.test\nencrypt phrase: test\n"
  fi
  if [[ "$V" == *"signed"* ]]; then
    EXTRAS="$EXTRAS\nsign: test@test.test\nsign phrase: test\n"
  fi
  if [[ "$V" == *"parity"* ]]; then
    EXTRAS="$EXTRAS\nadd parity: 5\n"
  fi

  echo "...Running suite using variation $V..."

  initialize
  generateConfig regular "$EXTRAS"
  generateConfig prefix "[options]\nprefix: prefixed-\n$EXTRAS"
  generateConfig filelist "[options]\ncreate filelist: yes\n$EXTRAS"
  generateConfig encryptmani "[security]\nencrypt manifest: yes\n$EXTRAS"

  runTest "Initial backup" "" "" regular

  dd if=/dev/urandom of=content/a bs=1024 count=123 2>/dev/null
  runTest "Change one file" "" "" regular

  rm content/b
  runTest "Delete one file" "" "" regular "Only in compare/content: b"

  runTest "Run without any changes" \
    "skip" \
    '
  function pretest() {
    if ! ${ICESHELF} --changes config_regular; then
      echo "ERROR: Changes detected when there should not be any"
      exit 255
    fi
  }
    ' \
    regular ""

  rm content/c
  dd if=/dev/urandom of=content/a bs=1024 count=123 2>/dev/null
  runTest "Delete one file and change another" "" "" regular "Only in compare/content: c"

  dd if=/dev/urandom of=content/b bs=1024 count=243 2>/dev/null
  runTest "Create new file with same name as deleted file" "" "" regular

  rm content/b
  runTest "Delete the new file again" "" "" regular "Only in compare/content: b"

  runTest "Test prefix config" \
    "skip" \
    '
  function posttest() {
    ls -laR done/ | grep prefix > /dev/null
    if [ $? -ne 0 ]; then
      echo "Prefix not working"
      return 1
    fi
  }
    ' \
    prefix "" --full

  mv content/d content/dd
  runTest "Moved file" "" "" regular "Only in compare/content: d
Only in content: dd"

  mv content/e content/ee || echo "ERROR: moving content/e to content/ee"
  cp content/ee content/eee || echo "ERROR: copying content/ee to content/eee"
  runTest "Move file and copy the same as well" "" "" regular "Only in compare/content: e
Only in content: ee"

exit 0

  rm content/ee content/eee
  runTest "Remove two files and generate backup with filelist and verify checksums" "" '
  function posttest() {
    pushd $(lastFolder)
    if ! shasum -c *.lst ; then
      echo "filelist.txt checksum failed"
      return 1
    fi
    popd
  }
  ' filelist "Only in compare/content: ee
Only in compare/content: eee"

  if [[ "$V" == *"encrypted"* ]]; then
    cp content/q content/qq
    runTest "Copy file and use encrypted manifest" "" '
    function posttest() {
      if ! ls -1 $(lastFolder) | grep json.gpg ; then
        echo "No encrypted json was found"
        return 1
      fi
    }
    ' encryptmani ""
  fi
done

echo -e "\nAll tests ended successfully"
cleanup
exit 0

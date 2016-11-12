#!/bin/bash

ICESHELF=../iceshelf
COUNT=0

# Removes old data and creates fresh
function initialize() {
  # Clean and prep
  rm -rf data tmp content done  >/dev/null 2>/dev/null
  rm config_* >/dev/null 2>/dev/null
  mkdir data tmp content done

  # Generate content
  # First, bunch of files
  for FILE in a b c d e f g h i j k l m n o p q r s t u v w x y z åäö éùü ø Hörbücher " "; do
  	dd if=/dev/zero of=content/${FILE} bs=1024 count=1 2>/dev/null
    FOLDER="folder-${FILE}"
    mkdir "content/${FOLDER}"
    for FILE2 in a b c åäö éùü " " ø; do
      dd if=/dev/zero of=content/${FOLDER}/${FILE2} bs=1024 count=1 2>/dev/null
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

# Runs an iceshelf session, first checking if there is any changes.
# If no changes are found, it fails
#
# Param 1: Name of the test
# Param 2: Run --changes ? If non-empty, it's skipped
# Param 3: Optional script (pretest() and posttest())
# Param 4: Configfile to use
# Param 5+: Sent directly to iceshelf
#
function runTest() {
  let "COUNT+=1"
  printf "Test #%03d: %s\n" ${COUNT} "$1"

  # Create functions
  eval "$3"

  if [ "$(type -t pretest)" == "function" ]; then
    RESULT="$(pretest)"
    unset -f pretest
    if [ $? -ne 0 ]; then
      echo "Pretest failed: $RESULT"
      exit 255
    fi
  fi

  if [ "$2" == "" ]; then
    RESULT="$(${ICESHELF} 2>&1 config_$4 --changes)"
    if [ $? -ne 1 ]; then
      echo "Test failed: Didn't detect changes"
      echo "$RESULT"
      exit 255
    fi
  fi

  RESULT="$(${ICESHELF} 2>&1 config_${@:4})"
  echo "${RESULT}"
  if [ $? -ne 0 ]; then
    echo "Test failed:"
    echo "$RESULT"
    exit 255
  fi

  if [ "$(type -t posttest)" == "function" ]; then
    RESULT="$(posttest)"
    unset -f posttest
    if [ $? -ne 0 ]; then
      echo "Posttest failed: $RESULT"
      exit 255
    fi
  fi


}

function hasGPGconfig() {
  gpg --list-keys 2>/dev/null | grep test@test.test >/dev/null 2>/dev/null
  return $?
}

VARIATIONS=("normal" "parity")

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
  VARIATIONS=("normal")
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

  echo "...Running suite using variation $V..."

  initialize
  generateConfig regular "$EXTRAS"
  generateConfig prefix "[options]\nprefix: prefixed-\n$EXTRAS"

  runTest "Initial backup" "" "" regular

  dd if=/dev/urandom of=content/a bs=1024 count=123 2>/dev/null
  runTest "Change one file" "" "" regular

  rm content/b
  runTest "Delete one file" "" "" regular

  rm content/c
  dd if=/dev/urandom of=content/a bs=1024 count=123 2>/dev/null
  runTest "Delete one file and change another" "" "" regular

  dd if=/dev/urandom of=content/b bs=1024 count=243 2>/dev/null
  runTest "Create new file with same name as deleted file" "" "" regular

  rm content/b
  runTest "Delete the new file again" "" "" regular

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
    prefix --full

  mv content/d content/dd
  runTest "Moved file" "" "" regular

  mv content/e content/ee
  cp content/ee content/eee
  runTest "Move file and copy the same as well" "" "" regular
done

echo -e "\nAll tests ended successfully"
exit 0

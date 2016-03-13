#!/bin/bash

ICESHELF=../iceshelf
COUNT=0

# Removes old data and creates fresh
function initialize() {
  # Clean and prep
  rm -rf data tmp content done
  rm config_*
  mkdir data tmp content done


  # Generate content
  I=0
  for FILE in a b c d e f g h i j k l m n o p q r s t u v w x y z åäö éùü; do
  	I=$(($I + 1))
  	dd if=/dev/zero of=content/${FILE} bs=1024 count=$(( $I * 123 )) 2>/dev/null
  done
}

# Creates a configuration file
#
# Param 1: Name of the config file, always prefixed with "config_"
# Param 2: additional config parameters (supports escaping)
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
  if [ $? -ne 0 ]; then
    echo "Test failed:"
    echo "$RESULT"
    exit 255
  fi

  if [ "$(type -t posttest)" == "function" ]; then
    RESULT="$(posttest)"
    if [ $? -ne 0 ]; then
      echo "Posttest failed: $RESULT"
      exit 255
    fi
  fi


}

initialize
generateConfig regular
generateConfig prefix "[options]\nprefix: prefixed-\n"

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

echo -e "\nAll tests ended successfully"
exit 0

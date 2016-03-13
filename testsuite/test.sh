#!/bin/bash

# Clean and prep
rm -rf data tmp content done
mkdir data tmp content done

# Generate content
I=0
for FILE in a b c d e f g h i j k l m n o p q r s t u v w x y z; do
	I=$(($I + 1))
	dd if=/dev/zero of=content/${FILE} bs=1024 count=$(( $I * 123 )) 2>/dev/null
done

../iceshelf config --changes
if [ $? -ne 1 ]; then
  echo "Failed to detect changes"
  exit 255
fi

../iceshelf config
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi

echo -e "\n\nTest 2: Change one file"
dd if=/dev/urandom of=content/a bs=1024 count=123 2>/dev/null
../iceshelf config --changes
if [ $? -ne 1 ]; then
  echo "Failed to detect changes"
  exit 255
fi

../iceshelf config
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi

echo -e "\n\nDelete a file"
rm content/b
../iceshelf config --changes
if [ $? -ne 1 ]; then
  echo "Failed to detect changes"
  exit 255
fi

../iceshelf config
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi

echo -e "\n\nDelete a file and change another"
rm content/c
dd if=/dev/urandom of=content/a bs=1024 count=123 2>/dev/null
../iceshelf config --changes
if [ $? -ne 1 ]; then
  echo "Failed to detect changes"
  exit 255
fi

../iceshelf config
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi

echo -e "\n\nRestore a deleted file"
dd if=/dev/urandom of=content/b bs=1024 count=243 2>/dev/null
../iceshelf config --changes
if [ $? -ne 1 ]; then
  echo "Failed to detect changes"
  exit 255
fi

../iceshelf config
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi

echo -e "\n\nDelete it again"
rm content/b
../iceshelf config --changes
if [ $? -ne 1 ]; then
  echo "Failed to detect changes"
  exit 255
fi

../iceshelf config
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi

echo -e "\n\nTesting prefix"
../iceshelf --full config_prefix
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi
ls -laR done/ | grep prefix > /dev/null
if [ $? -ne 0 ]; then
  echo "Prefix not working"
  exit 255
fi

echo -e "\n\nMoved file"
mv content/d content/dd
../iceshelf config --changes
if [ $? -ne 1 ]; then
  echo "Failed to detect changes"
  exit 255
fi
../iceshelf config
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi

echo -e "\n\nMoved file and copy the same"
mv content/e content/ee
cp content/ee content/eee
../iceshelf config --changes
if [ $? -ne 1 ]; then
  echo "Failed to detect changes"
  exit 255
fi
../iceshelf config
if [ $? -ne 0 ]; then
  echo "Failed to backup"
  exit 255
fi

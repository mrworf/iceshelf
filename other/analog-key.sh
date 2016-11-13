#!/bin/bash
#
# Converts your private key to/from QR codes
#
# Requires:
# - gpg
# - qrencode
# - zbarimg
# - split
# - base64
#
EXPORT=false
IMPORT=false
VALIDATE=false

# Make sure user has all necessary commands
for CMD in gpg qrencode base64 split replace zbarimg diff ; do
  if ! hash $CMD ; then
    echo "ERROR: Command $CMD is not available, see README.md for more details"
    exit 255
  fi
done

if [ "$1" == "export" ]; then
  EXPORT=true
elif [ "$1" == "import" ]; then
  IMPORT=true
elif [ "$1" == "validate" ]; then
  VALIDATE=true
else
  echo 'analog-key.sh - A simple utility to transfer digital keys to/from analog format'
  echo ''
  echo 'To export GPG key: analog-key.sh export "<gpg key id>"'
  echo 'To import GPG key: analog-key.sh import "<scanned document as pdf>"'
  echo '                   analog-key.sh import "*.jpg"'
  echo ''
  echo 'When importing the key using images, make sure you name them so they are in the'
  echo 'correct order (a-z or 0-9 or similar). Then just give the right pattern as 2nd'
  echo 'parameter. For example, if your files are named "page-1.tiff", "page-2.tiff", etc.'
  echo 'just execute:'
  echo ''
  echo '  analog-key.sh import "page-*.tiff"'
  echo ''
  echo 'and you should be able to decode it properly.'
  echo ""
  exit 255
fi

if ! $EXPORT && ! $IMPORT && ! $VALIDATE ; then
  echo "You must either export or import a key"
  exit 255
fi

if [ "$2" = "" ]; then
  if $IMPORT; then
    echo "You must provide a base filename"
  else
    echo "You must provide a GPG key identifier"
  fi
  exit 255
fi
ITEM="$2"

if $VALIDATE; then
  echo 'Validate will export and then immediately reimport the key and compare it to GPG'
  echo 'to confirm that the functionality in analog-key.sh works as expected.'
  echo ''
  echo 'No changes are done to GPG and all files are erased after testing.'
  echo ''
  echo 'Exporting...'
  if ! $0 export "${ITEM}" ; then
    echo 'ERROR: Unable to export key'
    exit 255
  fi
  echo 'Importing...'
  if ! $0 import "key-*.png" ; then
    echo 'ERROR: Unable to import key'
    exit 255
  fi
  echo 'Comparing...'
  if ! gpg --export-secret-key "${ITEM}" | diff - secret-key.gpg ; then
    echo "ERROR: Export->Import produced a key which differs from the one in gpg's keychain"
    exit 255
  fi
  rm "secret-key.gpg" key-*.png key.html
  echo "Everything checks out!"
  exit 0
elif $EXPORT; then
  rm key-* >/dev/null 2>/dev/null
  gpg --export-secret-key "${ITEM}" | base64 | split -d -b 2048 - key-
  for F in key-0[0-9]; do
    qrencode < $F -o $F.png
    rm $F
  done
  cat >key.html <<EOF
<html>
<style>
 @media print {
     img {
         width:100%;
         height:auto;
         page-break-after:always
     }
 }
 </style>
 <head><title>$ITEM</title></head>
 <body>
 <h1>Your key in QR codes</h1>
EOF
  for F in key-0[0-9].png; do
    echo >>key.html "$F:<br><img src=\"$F\"><br>"
  done
  echo >>key.html "</body></html>"

  echo "Please open and print key.html"
elif $IMPORT; then
  if [ "${ITEM: -4}" == ".pdf" ]; then
    if ! zbarimg "${ITEM}" --raw -q | replace "QR-Code:" "" | base64 -d >secret-key.gpg ; then
      echo "ERROR: Was unable to interpret the QR codes."
      echo " Some reasons this could fail:"
      echo " - Is zbarimg compiled with PDF support?"
      echo " - Did you scan the QR codes out-of-order?"
      exit 255
    fi
  else
    rm 2>/dev/null 1>/dev/null secret-key.b64.txt
    for F in ${ITEM}; do
      if ! zbarimg "${F}" --raw -q | replace "QR-Code:" "" >> "secret-key.b64.txt" ; then
        echo "ERROR: Unable to determine a QR code in the provided file."
        exit 255
      fi
    done
    if ! base64 -d < "secret-key.b64.txt" >secret-key.gpg ; then
      echo "ERROR: Not a valid key. Did you forget to enclose the 2nd parameter in quotes?"
      exit 255
    fi
    rm 2>/dev/null 1>/dev/null secret-key.b64.txt
  fi
  echo 'Restored key can be found as "secret-key.gpg"'
fi
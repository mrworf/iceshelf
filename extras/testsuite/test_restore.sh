#!/bin/bash
# Functional validation suite for iceshelf-restore.
#
# The script runs a number of restore scenarios covering
#  - unencrypted backups
#  - encrypted and/or signed backups (if gpg is available)
#  - archives with parity data (if par2 is available)
# It validates the output from --list and --validate and then
# restores the backup both using the manifest and using the
# prefix path.  Various failure conditions such as missing
# manifests and corrupt archives are also tested.

set -e

# Move to the directory where the script resides so that all
# relative paths work regardless of where the test is invoked
cd "$(dirname "$0")"

function hasGPGconfig() {
  gpg --list-secret-keys 2>/dev/null | grep test@test.test >/dev/null 2>/dev/null
  return $?
}

# The test is executed for a number of backup variants. By default we
# only run the plain "normal" setup. If additional tooling is
# available the set expands to cover parity data as well as gpg based
# encryption/signatures.
VARIATIONS=("normal")
if hash par2 >/dev/null 2>&1; then
  VARIATIONS+=("parity")
fi

if hash gpg >/dev/null 2>&1; then
  # If gpg is available, attempt to import the test key so that
  # encrypted and signed backups can be produced.  When the key is
  # present we extend the test matrix to cover those variants.
  HASKEY=false
  if ! hasGPGconfig; then
    echo "Importing test-key for test usage"
    gpg --no-tty --batch --pinentry-mode loopback --passphrase test --fast-import test_key.* >/dev/null 2>&1
    echo "010034E91082BF022DBAF1FEA00E5EDACC9D1828:6:" | gpg --import-ownertrust >/dev/null 2>&1
    if hasGPGconfig ; then
      HASKEY=true
    else
      echo "=== ERROR: Unable to import GPG key for testing, encryption will not be tested"
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
    VARIATIONS+=("${ADD[@]}")
  fi
fi

for VARIANT in "${VARIATIONS[@]}"; do
  echo "--- Restore variant ${VARIANT} ---"
  # Prepare a fresh backup environment
  rm -rf content tmp data done restore restore2
  mkdir content tmp data done restore restore2
  echo "hello restore" > content/file.txt

  # Compose additional configuration depending on current variant
  EXTRAS="[security]"
  if [[ "$VARIANT" == *"encrypted"* ]]; then
    EXTRAS="$EXTRAS\nencrypt: test@test.test\nencrypt phrase: test"
  fi
  if [[ "$VARIANT" == *"signed"* ]]; then
    EXTRAS="$EXTRAS\nsign: test@test.test\nsign phrase: test"
  fi
  if [[ "$VARIANT" == *"parity"* ]]; then
    EXTRAS="$EXTRAS\nadd parity: 5"
  fi

  # Minimal configuration to generate a single backup using the
  # currently selected options
  cat > config_restore <<CONF
[sources]
 test=$(pwd)/content/

[paths]
 prep dir: $(pwd)/tmp/
 data dir: $(pwd)/data/
 done dir: $(pwd)/done/

[options]
 delta manifest: yes
 compress: no
 persuasive: yes
 ignore overlimit: no
 incompressible:
 max keep: 0
 detect move: yes
${EXTRAS}
CONF

  # Generate the backup using iceshelf and collect the produced
  # manifest and archive names for later use
  ../../iceshelf config_restore
  BDIR=$(ls done)
  PREFIX="done/$BDIR/${BDIR}"
  MANIFEST=$(ls -1 --color=never done/$BDIR/${BDIR}.json*)
  ARCHIVE=""
  # Pick the main archive file from the generated backup folder. The
  # name varies depending on encryption/signing settings so we simply
  # look for the first matching tar file.
  for f in done/$BDIR/${BDIR}.tar*; do
    case "$f" in
      *.tar|*.tar.gpg|*.tar.sig|*.tar.gpg.sig)
        ARCHIVE="$f"
        break
        ;;
    esac
  done

  # Sanity check that list and validate output mention the expected texts
  LISTOUT="$(../../iceshelf-restore --list "$MANIFEST")"
  echo "$LISTOUT" | grep -q "Modified or new file" || {
    echo "list output did not contain expected entry";
    echo "$LISTOUT";
    exit 1;
  }

  VALOUT="$(../../iceshelf-restore --validate "$MANIFEST")"
  echo "$VALOUT" | grep -q "Validating metadata files" || {
    echo "validate output missing expected text";
    echo "$VALOUT";
    exit 1;
  }

  # Restore using the manifest path and verify the result matches
  ../../iceshelf-restore --restore restore "$MANIFEST"
  DEST="restore$(pwd)/content"
  if ! diff -r content "$DEST" >diff.out; then
    echo "Mismatch after manifest restore"
    cat diff.out
    exit 1
  fi
  rm diff.out

  # Restore using the prefix notation (no manifest) and verify again
  ../../iceshelf-restore --restore restore2 "$PREFIX"
  DEST2="restore2$(pwd)/content"
  if ! diff -r content "$DEST2" >diff.out; then
    echo "Mismatch after prefix restore"
    cat diff.out
    exit 1
  fi
  rm diff.out

  # Negative tests: remove the manifest and ensure restore/validate fail
  mv "$MANIFEST" "$MANIFEST.bak"
  if ../../iceshelf-restore "$PREFIX" 2>/dev/null; then
    echo "restore succeeded unexpectedly when manifest missing"
    exit 1
  fi
  if ../../iceshelf-restore --force --validate "$PREFIX" 2>/dev/null; then
    echo "forced validation unexpectedly succeeded"
    exit 1
  fi
  mv "$MANIFEST.bak" "$MANIFEST"

  # Corrupt the archive and verify that validation fails. When parity
  # data is present we also exercise the repair functionality.
  cp "$ARCHIVE" "$ARCHIVE.bak"
  dd if=/dev/urandom of="$ARCHIVE" bs=1 count=10 seek=10 conv=notrunc >/dev/null 2>&1
  if ../../iceshelf-restore --validate "$MANIFEST" 2>/dev/null; then
    echo "corrupt archive validated unexpectedly"
    exit 1
  fi
  if [[ "$VARIANT" == *"parity"* ]]; then
    ../../iceshelf-restore --repair --validate "$MANIFEST" || true
  fi
  mv "$ARCHIVE.bak" "$ARCHIVE"

done

# All variants completed successfully
echo "iceshelf-restore test suite completed successfully"

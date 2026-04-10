"""Helpers shared by iceshelf-restore and its unit tests."""

import logging
import os
import os.path
import re
import shutil
import sys
import tempfile

from modules import fileutils


MANIFEST_SUFFIXES = ('.json.gpg.asc', '.json.asc', '.json.gpg', '.json')
# Prefer most-wrapped first so we never use left-over decrypted intermediates
ARCHIVE_SUFFIXES = (
    '.tar.bz2.gpg.sig', '.tar.bz2.gpg', '.tar.bz2.sig', '.tar.bz2',
    '.tar.gpg.sig', '.tar.gpg', '.tar.sig', '.tar')
FILELIST_SUFFIXES = ('.lst.asc', '.lst')
# PAR2: archive_filename.par2, archive_filename.volN+MM.par2, optional .sig
PAR2_VOL_PATTERN = re.compile(r'^\.vol\d+\+\d+\.par2(\.sig)?$')


def get_manifest_file(basepath, basename):
    """Return path to manifest file if it exists; check only iceshelf manifest names in order."""
    for suffix in MANIFEST_SUFFIXES:
        path = os.path.join(basepath, basename + suffix)
        if os.path.isfile(path):
            return path
    return None


def get_archive_file(basepath, basename):
    """Return path to main archive file if it exists; check only iceshelf archive names in order."""
    for suffix in ARCHIVE_SUFFIXES:
        path = os.path.join(basepath, basename + suffix)
        if os.path.isfile(path):
            return path
    return None


def get_filelist_file(basepath, basename):
    """Return path to filelist file if it exists; check only iceshelf filelist names in order."""
    for suffix in FILELIST_SUFFIXES:
        path = os.path.join(basepath, basename + suffix)
        if os.path.isfile(path):
            return path
    return None


def get_parity_files(basepath, archive_filename):
    """Return list of paths that are PAR2 files for this archive (exact iceshelf PAR2 naming)."""
    results = []
    base_par2 = os.path.join(basepath, archive_filename + '.par2')
    base_par2_sig = base_par2 + '.sig'
    if os.path.isfile(base_par2):
        results.append(base_par2)
    if os.path.isfile(base_par2_sig):
        results.append(base_par2_sig)
    try:
        for entry in os.listdir(basepath):
            if not entry.startswith(archive_filename + '.vol'):
                continue
            rest = entry[len(archive_filename):]
            if PAR2_VOL_PATTERN.match(rest):
                results.append(os.path.join(basepath, entry))
    except OSError:
        pass
    return sorted(results)


def get_files_for_basename(basepath, basename):
    """Return list of file names in basepath that belong to this backup (established patterns only)."""
    if not os.path.isdir(basepath):
        return []
    files = []
    manifest_path = get_manifest_file(basepath, basename)
    if manifest_path:
        files.append(os.path.basename(manifest_path))
    archive_path = get_archive_file(basepath, basename)
    if archive_path:
        files.append(os.path.basename(archive_path))
        for parity_path in get_parity_files(basepath, os.path.basename(archive_path)):
            files.append(os.path.basename(parity_path))
    filelist_path = get_filelist_file(basepath, basename)
    if filelist_path:
        files.append(os.path.basename(filelist_path))
    return files


def valid_archive(base_dir, list_file_path, corrupt_list, found_files):
    """
    Validate files listed in the filelist. list_file_path is the full path to the list file
    (may be in a temp dir); base_dir is the backup directory for resolving relative paths in the list.
    """
    pattern = re.compile('([a-f0-9]+)\\s+([^\\s]+)')
    criticalerror = False
    archivecorrupt = False
    paritycount = 0
    del found_files[:]
    with open(list_file_path, "r", encoding='utf-8') as list_fp:
        all_lines = list_fp.readlines()

    to_validate = []
    total_bytes = 0
    for line in all_lines:
        res = pattern.match(line)
        if not res:
            logging.error("filelist.txt is corrupt")
            return False
        full_path = os.path.join(base_dir, res.group(2))
        if not os.path.exists(full_path):
            logging.error('File "%s" is missing from backup', res.group(2))
            return False
        total_bytes += os.path.getsize(full_path)
        to_validate.append((res.group(1), full_path, line))

    bytes_done = 0
    last_pct = -1

    def progress_callback(file_done, _file_total):
        nonlocal bytes_done, last_pct
        pct = (100 * (bytes_done + file_done) // total_bytes) if total_bytes else 100
        if pct != last_pct:
            sys.stderr.write('\rValidating archive, %d%% done    ' % pct)
            sys.stderr.flush()
            last_pct = pct

    try:
        for checksum, full_path, line in to_validate:
            found_files.append(os.path.relpath(full_path, base_dir))
            sha = fileutils.hashFile(
                full_path, 'sha1', progress_callback=progress_callback)
            bytes_done += os.path.getsize(full_path)
            if sha != checksum:
                corrupt_list.append(os.path.relpath(full_path, base_dir))
                if ".json" in line:
                    logging.error('Manifest is corrupt, please restore manually')
                    criticalerror = True
                elif ".tar" in line:
                    archivecorrupt = True
                elif ".par2" in line:
                    logging.warning(
                        'Parity file "%s" is corrupt and will not be used',
                        os.path.relpath(full_path, base_dir))
            elif ".par2" in line:
                paritycount += 1
    finally:
        sys.stderr.write('\n')
        sys.stderr.flush()

    if archivecorrupt and paritycount == 0:
        logging.error('Archive is corrupt and no available parity files')
        criticalerror = True
    elif archivecorrupt:
        logging.warning(
            'Archive is corrupt, but parity is available making repair a possibility')
        criticalerror = True
    return not criticalerror


def prepare_parity_for_repair(basepath, archive_filename, parity_files, keyring_dir=None,
                              work_dir=None, validate_file_fn=None, strip_file_fn=None):
    """Return staged repair inputs for par2, including signed parity when needed.

    Returns (info_dict, None) on success, where info_dict contains:
    - repair_dir: temp directory to clean up, or None when using in-place unsigned parity
    - main_par2: path to the main .par2 file to pass to par2
    - archive_path: path to the archive file that par2 will repair
    Returns (None, error_text) when parity exists but cannot be prepared for repair.
    """
    if not parity_files:
        return None, 'no parity files available'

    archive_path = os.path.join(basepath, archive_filename)
    if not os.path.isfile(archive_path):
        return None, 'archive file is missing'

    usable_files = []
    for parity_path in parity_files:
        if validate_file_fn is not None and not validate_file_fn(parity_path, keyring_dir):
            logging.warning(
                'Skipping parity file "%s" due to failed validation',
                os.path.basename(parity_path))
            continue
        usable_files.append(parity_path)

    if not usable_files:
        return None, 'no usable parity files available'

    main_par2_name = archive_filename + '.par2'
    needs_staging = any(path.endswith('.sig') for path in usable_files)
    if not needs_staging:
        main_par2 = os.path.join(basepath, main_par2_name)
        if os.path.isfile(main_par2):
            return {
                'repair_dir': None,
                'main_par2': main_par2,
                'archive_path': archive_path,
            }, None

    if strip_file_fn is None:
        return None, 'cannot prepare signed parity files without strip support'

    repair_dir = tempfile.mkdtemp(
        prefix='iceshelf-parity.',
        dir=work_dir if work_dir and os.path.isdir(work_dir) else None)
    staged_archive = os.path.join(repair_dir, archive_filename)
    shutil.copy2(archive_path, staged_archive)

    try:
        for parity_path in usable_files:
            basename = os.path.basename(parity_path)
            staged_path = os.path.join(
                repair_dir, basename[:-4] if basename.endswith('.sig') else basename)
            if basename.endswith('.sig'):
                stripped_path, strip_err = strip_file_fn(
                    parity_path, keyring_dir, output_path=staged_path, work_dir=repair_dir)
                if stripped_path is None:
                    logging.warning(
                        'Skipping parity file "%s": %s',
                        basename, strip_err or 'unable to strip signature')
                    continue
            else:
                shutil.copy2(parity_path, staged_path)

        main_par2 = os.path.join(repair_dir, main_par2_name)
        if not os.path.isfile(main_par2):
            shutil.rmtree(repair_dir)
            return None, 'no usable main parity file available'

        return {
            'repair_dir': repair_dir,
            'main_par2': main_par2,
            'archive_path': staged_archive,
        }, None
    except Exception:
        shutil.rmtree(repair_dir)
        raise

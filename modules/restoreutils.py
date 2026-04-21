"""Helpers shared by iceshelf-restore and its unit tests."""

import logging
import math
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
ACTIVITY_LOG_SUFFIXES = (
    '.activity.log.bz2.gpg.asc',
    '.activity.log.bz2.asc',
    '.activity.log.bz2.gpg',
    '.activity.log.bz2',
)
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


def get_activity_log_file(basepath, basename):
    """Return path to uploaded activity log sidecar if it exists."""
    for suffix in ACTIVITY_LOG_SUFFIXES:
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
    activity_log_path = get_activity_log_file(basepath, basename)
    if activity_log_path:
        files.append(os.path.basename(activity_log_path))
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


def normalize_manifest_path(path):
    """Normalize a manifest path to a leading-slash POSIX-like form."""
    if not path:
        return '/'
    normalized = path.replace('\\', '/')
    if not normalized.startswith('/'):
        normalized = '/' + normalized
    normalized = os.path.normpath(normalized).replace('\\', '/')
    if not normalized.startswith('/'):
        normalized = '/' + normalized
    return normalized.rstrip('/') or '/'


def manifest_parent_backup(manifest):
    """Return parent backup id from manifest (lastbackup or previousbackup)."""
    return manifest.get('lastbackup') or manifest.get('previousbackup')


def normalize_moved_entry(info, backup_id):
    """Normalize a manifest moved entry to dict form."""
    if isinstance(info, dict):
        return {
            'original': info.get('original', ''),
            'reference': info.get('reference', backup_id),
        }
    return {'original': info if isinstance(info, str) else '', 'reference': backup_id}


def parse_analysis_threshold(raw_value, total_actions):
    """Parse --analyze-activity value and resolve it against total_actions."""
    if raw_value is None:
        raw_value = '10%'
    value = str(raw_value).strip()
    if not value:
        raise ValueError('activity threshold cannot be empty')

    is_percent = value.endswith('%')
    number_text = value[:-1] if is_percent else value
    if not number_text:
        raise ValueError('activity threshold is missing a numeric value')
    try:
        parsed_value = int(number_text)
    except ValueError as exc:
        raise ValueError(
            'activity threshold must be an integer or a percentage such as 10%'
        ) from exc

    clipped_value = max(parsed_value, 1)
    if is_percent:
        threshold = int(math.ceil((total_actions * clipped_value) / 100.0)) if total_actions > 0 else 1
        return {
            'input': value,
            'kind': 'percent',
            'value': clipped_value,
            'threshold': max(threshold, 1),
            'display': '%d%% of %d actions' % (clipped_value, total_actions),
        }

    return {
        'input': value,
        'kind': 'absolute',
        'value': clipped_value,
        'threshold': clipped_value,
        'display': '%d action(s)' % clipped_value,
    }


def _path_folder(path):
    """Return the normalized parent folder for a manifest path."""
    return os.path.dirname(normalize_manifest_path(path)) or '/'


def _new_lifecycle(checksum):
    """Create a lifecycle tracker for one checksum."""
    return {
        'checksum': checksum,
        'latest_path': None,
        'paths': set(),
        'modification_count': 0,
        'deletion_count': 0,
        'backups_touched': set(),
        'current_folder': None,
        'active': False,
        'pending_folder_modifications': {},
    }


def analyze_manifest_history(manifests_by_basename):
    """Build manifest-only lifecycle and transient-folder analysis."""
    lifecycles = {}
    active_paths = {}
    folders = {}
    total_actions = 0
    skipped_modified_without_checksum = 0

    for backup_id, manifest in manifests_by_basename.items():
        modified = manifest.get('modified', {}) or {}
        deleted = manifest.get('deleted', []) or []
        moved = manifest.get('moved', {}) or {}
        total_actions += len(modified) + len(deleted)

        for raw_path, meta in modified.items():
            path = normalize_manifest_path(raw_path)
            checksum = meta.get('checksum', '')
            if not checksum:
                skipped_modified_without_checksum += 1
                continue

            lifecycle = lifecycles.get(checksum)
            if lifecycle is None:
                lifecycle = _new_lifecycle(checksum)
                lifecycles[checksum] = lifecycle

            if not lifecycle['active']:
                lifecycle['pending_folder_modifications'] = {}
            previous_path = lifecycle.get('latest_path')
            if previous_path and previous_path != path and active_paths.get(previous_path) == checksum:
                active_paths.pop(previous_path, None)

            folder = _path_folder(path)
            lifecycle['latest_path'] = path
            lifecycle['paths'].add(path)
            lifecycle['modification_count'] += 1
            lifecycle['backups_touched'].add(backup_id)
            lifecycle['current_folder'] = folder
            lifecycle['active'] = True
            lifecycle['pending_folder_modifications'][folder] = (
                lifecycle['pending_folder_modifications'].get(folder, 0) + 1
            )
            active_paths[path] = checksum

        for raw_newpath, info in moved.items():
            newpath = normalize_manifest_path(raw_newpath)
            normalized = normalize_moved_entry(info, backup_id)
            oldpath = normalize_manifest_path(normalized.get('original', ''))

            checksum = ''
            if newpath in modified:
                checksum = modified[newpath].get('checksum', '')
            if not checksum:
                checksum = active_paths.get(oldpath, '')
            if not checksum:
                continue

            lifecycle = lifecycles.get(checksum)
            if lifecycle is None:
                lifecycle = _new_lifecycle(checksum)
                lifecycles[checksum] = lifecycle

            if oldpath != '/' or normalized.get('original', ''):
                lifecycle['paths'].add(oldpath)
            lifecycle['paths'].add(newpath)
            lifecycle['backups_touched'].add(backup_id)
            lifecycle['latest_path'] = newpath
            lifecycle['current_folder'] = _path_folder(newpath)
            lifecycle['active'] = True
            if active_paths.get(oldpath) == checksum:
                active_paths.pop(oldpath, None)
            active_paths[newpath] = checksum

        for raw_path in deleted:
            path = normalize_manifest_path(raw_path)
            checksum = active_paths.pop(path, None)
            if not checksum:
                continue

            lifecycle = lifecycles.get(checksum)
            if lifecycle is None:
                continue

            folder = _path_folder(path)
            lifecycle['latest_path'] = path
            lifecycle['paths'].add(path)
            lifecycle['deletion_count'] += 1
            lifecycle['backups_touched'].add(backup_id)
            lifecycle['current_folder'] = folder
            lifecycle['active'] = False

            folder_modified = lifecycle['pending_folder_modifications'].get(folder, 0)
            folder_info = folders.setdefault(folder, {
                'path': folder,
                'action_count': 0,
                'modification_count': 0,
                'deletion_count': 0,
                'lifecycles': set(),
            })
            folder_info['action_count'] += folder_modified + 1
            folder_info['modification_count'] += folder_modified
            folder_info['deletion_count'] += 1
            folder_info['lifecycles'].add(checksum)

            lifecycle['pending_folder_modifications'] = {}

    file_items = []
    for lifecycle in lifecycles.values():
        action_count = lifecycle['modification_count'] + lifecycle['deletion_count']
        display_path = lifecycle['latest_path'] or lifecycle['checksum']
        file_items.append({
            'checksum': lifecycle['checksum'],
            'display_path': display_path,
            'action_count': action_count,
            'modification_count': lifecycle['modification_count'],
            'deletion_count': lifecycle['deletion_count'],
            'path_count': len(lifecycle['paths']),
            'exclude_rule': display_path,
            'active': lifecycle['active'],
            'backups_touched': len(lifecycle['backups_touched']),
        })

    folder_items = []
    for folder, info in folders.items():
        folder_items.append({
            'display_path': folder,
            'action_count': info['action_count'],
            'modification_count': info['modification_count'],
            'deletion_count': info['deletion_count'],
            'transient_lifecycles': len(info['lifecycles']),
            'exclude_rule': folder if folder == '/' else folder.rstrip('/') + '/',
        })

    file_items.sort(key=lambda item: (-item['action_count'], item['display_path']))
    folder_items.sort(key=lambda item: (-item['action_count'], item['display_path']))

    return {
        'total_actions': total_actions,
        'backup_count': len(manifests_by_basename),
        'file_items': file_items,
        'folder_items': folder_items,
        'skipped_modified_without_checksum': skipped_modified_without_checksum,
    }


def format_manifest_analysis(report, threshold_info):
    """Format manifest analysis output as display-ready lines."""
    total_actions = report.get('total_actions', 0)
    threshold = threshold_info.get('threshold', 1)

    def action_share(action_count):
        if total_actions <= 0:
            return '0.0%'
        return '%.1f%%' % ((100.0 * action_count) / total_actions)

    def select_items(items):
        return [item for item in items if item.get('action_count', 0) >= threshold]

    file_items = select_items(report.get('file_items', []))
    folder_items = select_items(report.get('folder_items', []))
    lines = [
        'Manifest analysis summary:',
        '  backups analyzed: %d' % report.get('backup_count', 0),
        '  manifest actions: %d' % total_actions,
        '  activity threshold: %d (%s)' % (threshold, threshold_info.get('display', '')),
    ]

    skipped = report.get('skipped_modified_without_checksum', 0)
    if skipped:
        lines.append('  skipped modified entries without checksum: %d' % skipped)

    lines.append('Frequently changing file lifecycles:')
    if not file_items:
        lines.append('  No items met the activity threshold.')
    else:
        for item in file_items:
            parts = [
                '  %s' % item['display_path'],
                'actions=%d' % item['action_count'],
                'share=%s' % action_share(item['action_count']),
                'modified=%d' % item['modification_count'],
                'deleted=%d' % item['deletion_count'],
            ]
            if item.get('path_count', 0) > 1:
                parts.append('paths=%d' % item['path_count'])
            parts.append('exclude=%s' % item['exclude_rule'])
            lines.append(' | '.join(parts))

    lines.append('Transient folders:')
    if not folder_items:
        lines.append('  No items met the activity threshold.')
    else:
        for item in folder_items:
            lines.append(
                '  %s | actions=%d | share=%s | modified=%d | deleted=%d | '
                'lifecycles=%d | exclude=%s'
                % (
                    item['display_path'],
                    item['action_count'],
                    action_share(item['action_count']),
                    item['modification_count'],
                    item['deletion_count'],
                    item['transient_lifecycles'],
                    item['exclude_rule'],
                )
            )

    return lines

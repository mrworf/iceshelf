# pylint: disable=invalid-name
"""GPG helpers (subprocess-based, no python-gnupg).

Provides encrypt, sign, decrypt, verify and key-import operations
used by iceshelf, iceshelf-restore and the test suite.
"""

import os
import subprocess
import tempfile


def gpg_env(keyring_dir):
    """Return environment dict with GNUPGHOME set if keyring_dir is not None."""
    env = os.environ.copy()
    if keyring_dir is not None:
        env['GNUPGHOME'] = keyring_dir
    return env


def gpg_available():
    """Return True if the gpg binary exists and is runnable."""
    try:
        result = subprocess.run(
            ['gpg', '--version'],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _base_args(keyring_dir):
    """Common args for gpg invocations."""
    args = ['gpg', '--no-tty', '--batch']
    if keyring_dir is not None:
        args.extend(['--trust-model', 'always'])
    return args


def _passphrase_args(passphrase, env):
    """Return (extra_args, stdin_bytes, passphrase_fd) for passphrase handling.
    Uses a temp file so we don't put passphrase on command line.
    Caller must unlink the temp file when done.
    """
    if not passphrase:
        return [], None, None
    fd, path = tempfile.mkstemp(prefix='iceshelf-gpg.', text=False)
    try:
        os.write(fd, passphrase.encode('utf-8', errors='replace') if isinstance(passphrase, str) else passphrase)
        os.close(fd)
        fd = None
        return ['--pinentry-mode', 'loopback', '--passphrase-file', path], None, path
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(path)
            except OSError:
                pass


def _cleanup_passphrase_file(passphrase_file):
    """Remove and wipe passphrase temp file if present."""
    if not passphrase_file or not os.path.isfile(passphrase_file):
        return
    try:
        with open(passphrase_file, 'r+b') as f:
            length = f.seek(0, 2)
            f.seek(0)
            f.write(b'\x00' * length)
    except OSError:
        pass
    try:
        os.unlink(passphrase_file)
    except OSError:
        pass


def gpg_verify(filepath, keyring_dir, skip_signature=False):
    """Run gpg --verify on filepath. Return (success, stderr_text)."""
    if skip_signature:
        return True, ''
    args = _base_args(keyring_dir) + ['--verify', filepath]
    env = gpg_env(keyring_dir)
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        stderr = (result.stderr or '').strip()
        return result.returncode == 0, stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def gpg_decrypt_one(input_path, output_path, keyring_dir, passphrase=None):
    """Single gpg --decrypt from input_path to output_path. Return (success, stderr)."""
    args = _base_args(keyring_dir) + ['--decrypt', '--output', output_path]
    env = gpg_env(keyring_dir)
    passphrase_file = None
    try:
        extra, _, passphrase_file = _passphrase_args(passphrase, env)
        args.extend(extra)
        args.append(input_path)
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            timeout=3600,
        )
        stderr = (result.stderr or '').strip()
        return result.returncode == 0, stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    finally:
        _cleanup_passphrase_file(passphrase_file)


def gpg_decrypt_piped(input_path, output_path, keyring_dir, passphrase=None):
    """Two gpg --decrypt in pipeline: input_path (signed+encrypted) -> output_path (plain).
    First gpg verifies and outputs payload to stdout; second decrypts stdin to output_path.
    Return (success, combined_stderr). No intermediate file.
    """
    env = gpg_env(keyring_dir)
    passphrase_file = None
    try:
        extra, _, passphrase_file = _passphrase_args(passphrase, env)
        base = _base_args(keyring_dir)
        args_a = base + extra + ['--decrypt', input_path]
        args_b = base + extra + ['--decrypt', '--output', output_path, '-']
        try:
            proc_a = subprocess.Popen(
                args_a,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            proc_b = subprocess.Popen(
                args_b,
                stdin=proc_a.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=env,
            )
            proc_a.stdout.close()
            _, stderr_b = proc_b.communicate(timeout=3600)
            _, stderr_a = proc_a.communicate(timeout=5)
            ok = proc_a.returncode == 0 and proc_b.returncode == 0
            stderr = (stderr_a.decode('utf-8', errors='replace') + '\n' +
                      stderr_b.decode('utf-8', errors='replace')).strip()
            return ok, stderr
        except subprocess.TimeoutExpired:
            proc_a.kill()
            proc_b.kill()
            proc_a.wait()
            proc_b.wait()
            return False, 'gpg pipeline timed out'
    except OSError as e:
        return False, str(e)
    finally:
        _cleanup_passphrase_file(passphrase_file)


def gpg_import_and_trust(keyring_dir, key_data_bytes):
    """Import key data into keyring_dir and set ultimate trust. Return (success, stderr)."""
    env = gpg_env(keyring_dir)
    try:
        result = subprocess.run(
            _base_args(keyring_dir) + ['--import'],
            input=key_data_bytes,
            capture_output=True,
            timeout=30,
            env=env,
        )
        if result.returncode != 0:
            stderr = (result.stderr or b'').decode('utf-8', errors='replace').strip()
            return False, stderr
        # List keys to get fingerprints
        result = subprocess.run(
            ['gpg', '--no-tty', '--batch', '--list-keys', '--with-colons'],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        if result.returncode != 0:
            return True, ''  # import succeeded
        fingerprints = []
        want_next = False
        for line in (result.stdout or '').splitlines():
            if line.startswith('pub:') or line.startswith('sec:'):
                want_next = True
                continue
            if line.startswith('fpr:'):
                if want_next:
                    parts = line.split(':')
                    if len(parts) >= 10 and parts[9]:
                        fingerprints.append(parts[9])
                want_next = False
        if not fingerprints:
            return False, 'No key could be imported from key data.'
        ownertrust = ''.join('%s:6:\n' % f for f in fingerprints if f)
        subprocess.run(
            ['gpg', '--no-tty', '--batch', '--import-ownertrust'],
            input=ownertrust.encode(),
            capture_output=True,
            timeout=10,
            env=env,
            check=False,
        )
        return True, ''
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def gpg_encrypt_file(input_path, output_path, recipient, keyring_dir=None,
                     passphrase=None, armor=False):
    """Encrypt input_path to output_path for recipient. Return (success, stderr)."""
    args = _base_args(keyring_dir) + ['-z', '0', '--encrypt',
                                       '--recipient', recipient,
                                       '--output', output_path]
    if armor:
        args.append('--armor')
    env = gpg_env(keyring_dir)
    passphrase_file = None
    try:
        extra, _, passphrase_file = _passphrase_args(passphrase, env)
        args.extend(extra)
        args.append(input_path)
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            timeout=3600,
        )
        stderr = (result.stderr or '').strip()
        return result.returncode == 0, stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    finally:
        _cleanup_passphrase_file(passphrase_file)


def gpg_sign_file(input_path, output_path, keyid, keyring_dir=None,
                  passphrase=None, binary=False):
    """Create an inline signature wrapping input_path. Return (success, stderr).

    The original data is embedded inside the signed output so the recipient
    can extract it with ``gpg --decrypt``.

    binary=True  -> binary signed message (--sign)
    binary=False -> ASCII-armored signed message (--sign --armor)
    """
    args = _base_args(keyring_dir) + ['--sign',
                                       '--local-user', keyid,
                                       '--output', output_path]
    if not binary:
        args.append('--armor')
    env = gpg_env(keyring_dir)
    passphrase_file = None
    try:
        extra, _, passphrase_file = _passphrase_args(passphrase, env)
        args.extend(extra)
        args.append(input_path)
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            timeout=3600,
        )
        stderr = (result.stderr or '').strip()
        return result.returncode == 0, stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    finally:
        _cleanup_passphrase_file(passphrase_file)


def gpg_test_encrypt(recipient, keyring_dir=None, passphrase=None):
    """Quick test that we can encrypt for recipient. Return (success, stderr)."""
    args = _base_args(keyring_dir) + ['-z', '0', '--encrypt',
                                       '--recipient', recipient,
                                       '--armor']
    env = gpg_env(keyring_dir)
    passphrase_file = None
    try:
        extra, _, passphrase_file = _passphrase_args(passphrase, env)
        args.extend(extra)
        result = subprocess.run(
            args,
            input=b'test',
            capture_output=True,
            env=env,
            timeout=30,
        )
        stderr = (result.stderr or b'').decode('utf-8', errors='replace').strip()
        return result.returncode == 0 and len(result.stdout or b'') > 0, stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    finally:
        _cleanup_passphrase_file(passphrase_file)


def gpg_test_sign(keyid, keyring_dir=None, passphrase=None):
    """Quick test that we can sign with keyid. Return (success, stderr)."""
    args = _base_args(keyring_dir) + ['--detach-sign', '--armor',
                                       '--local-user', keyid]
    env = gpg_env(keyring_dir)
    passphrase_file = None
    try:
        extra, _, passphrase_file = _passphrase_args(passphrase, env)
        args.extend(extra)
        result = subprocess.run(
            args,
            input=b'test',
            capture_output=True,
            env=env,
            timeout=30,
        )
        stderr = (result.stderr or b'').decode('utf-8', errors='replace').strip()
        return result.returncode == 0 and len(result.stdout or b'') > 0, stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    finally:
        _cleanup_passphrase_file(passphrase_file)

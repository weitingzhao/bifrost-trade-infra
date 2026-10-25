import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('identity', Path(__file__).with_name('check-local-credential-identity.py'))
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)
HOST = '192.168.10.73:30300'
URL = f'http://{HOST}/bifrost/repo.git'


@pytest.fixture
def audit(tmp_path, monkeypatch):
    # Only synthetic Git configuration and mocked Keychain metadata are read.
    for key in list(os.environ):
        if key.startswith('GIT_CONFIG') or key in ('GIT_DIR', 'GIT_WORK_TREE'):
            monkeypatch.delenv(key)
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(tmp_path / 'global'))
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'remote', 'add', 'origin', URL], check=True)
    calls = []
    def check(config, keychain=44):
        (tmp_path / 'global').write_text(config)
        def run(args, **kwargs):
            calls.append(args)
            if args[0] == 'security':
                return subprocess.CompletedProcess(args, keychain, 'fixture-metadata', '')
            return subprocess.run(args, **kwargs)
        result = identity.check(HOST, ['weitingzhao'], run, checkout=tmp_path)
        assert all('-g' not in c and '-w' not in c and 'fill' not in c for c in calls)
        return result
    check.path, check.calls = tmp_path, calls
    return check


def test_admin_keychain_is_refused_without_reading_password(audit):
    failures, unknown = audit('[credential]\n helper = osxkeychain\n', keychain=0)
    assert failures and not unknown


def test_helper_chain_store_then_osxkeychain_never_passes(audit):
    failures, unknown = audit('[credential]\n helper = store\n helper = osxkeychain\n')
    assert not failures and unknown
    assert str(audit.path / 'global') in unknown[0]


def test_path_scoped_admin_username_and_helper(audit):
    failures, unknown = audit(f'[credential]\n helper = osxkeychain\n'
                              f'[credential "http://{HOST}/bifrost"]\n username = weitingzhao\n helper = store\n')
    assert failures and unknown


def test_configured_admin_and_lookup_errors(audit):
    failures, unknown = audit('[credential]\n username = weitingzhao\n', keychain=1)
    assert failures and unknown


def test_clean_metadata(audit):
    assert audit('[credential]\n helper = osxkeychain\n username = bifrost-mbp\n') == ([], [])


def test_path_reset_clears_previous_helpers(audit):
    assert audit(f'[credential]\n helper = store\n'
                 f'[credential "http://{HOST}/bifrost"]\n helper =\n helper = osxkeychain\n') == ([], [])


def test_nonmatching_reset_does_not_clear_chain(audit):
    failures, unknown = audit(f'[credential]\n helper = store\n'
                              f'[credential "http://{HOST}/bifrost-other"]\n helper =\n helper = osxkeychain\n')
    assert not failures and unknown


def test_included_config_and_local_reset(audit):
    included = audit.path / 'included'
    included.write_text('[credential]\n helper = store\n')
    config = f'[include]\n path = {included}\n[credential]\n helper = osxkeychain\n'
    assert str(included) in audit(config)[1][0]
    with (audit.path / '.git/config').open('a') as f:
        f.write('[credential]\n helper =\n helper = osxkeychain\n')
    assert audit(config) == ([], [])


def test_unknown_origin_never_passes(audit, monkeypatch):
    monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
    monkeypatch.setenv('GIT_CONFIG_KEY_0', 'credential.helper')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0', 'osxkeychain')
    assert 'unknown origin' in ' '.join(audit('')[1])


def test_all_fetch_push_urls_and_rewrites(audit):
    with (audit.path / '.git/config').open('a') as f:
        f.write(f'[remote "origin"]\n pushurl = audit:repo.git\n pushurl = http://{HOST}/other/repo.git\n'
                f'[url "http://{HOST}/admin/"]\n insteadOf = audit:\n')
    failures, unknown = audit(f'[credential "http://{HOST}/admin"]\n username = weitingzhao\n')
    assert failures and not unknown
    assert any('--push' in c and '--all' in c for c in audit.calls)


def test_unrelated_path_and_host_do_not_apply(audit):
    assert audit(f'[credential "http://{HOST}/bifrost-other"]\n helper = store\n username = weitingzhao\n'
                 '[credential "https://other.test"]\n helper = store\n') == ([], [])


def test_no_matching_remote_is_inconclusive(audit):
    subprocess.run(['git', '-C', str(audit.path), 'remote', 'remove', 'origin'], check=True)
    assert audit('')[1]


def test_url_username_is_checked(audit):
    subprocess.run(['git', '-C', str(audit.path), 'remote', 'set-url', 'origin',
                    f'http://weitingzhao@{HOST}/bifrost/repo.git'], check=True)
    assert audit('[credential]\n username = bifrost-mbp\n')[0]

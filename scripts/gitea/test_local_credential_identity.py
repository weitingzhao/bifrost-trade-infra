import importlib.util
from pathlib import Path
from subprocess import CompletedProcess

spec = importlib.util.spec_from_file_location('identity', Path(__file__).with_name('check-local-credential-identity.py'))
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


def test_admin_keychain_is_refused_without_reading_password():
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return CompletedProcess(args, 0, 'credential.helper osxkeychain\n' if args[0] == 'git' else 'metadata', '')
    failures, unknown = identity.check('192.168.10.73:30300', ['weitingzhao'], run)
    assert failures and not unknown
    assert all('-g' not in c and '-w' not in c and 'fill' not in c for c in calls)


def test_unknown_helper_never_passes():
    def run(args, **kwargs):
        return CompletedProcess(args, 0 if args[0] == 'git' else 44, 'credential.helper store\n', '')
    failures, unknown = identity.check('192.168.10.73:30300', ['weitingzhao'], run)
    assert not failures and unknown


def test_configured_admin_and_lookup_errors():
    def run(args, **kwargs):
        return CompletedProcess(args, 0 if args[0] == 'git' else 1, 'credential.username weitingzhao\n', '')
    failures, unknown = identity.check('192.168.10.73:30300', ['weitingzhao'], run)
    assert failures and unknown


def test_clean_metadata():
    def run(args, **kwargs):
        return CompletedProcess(args, 0 if args[0] == 'git' else 44, 'credential.helper osxkeychain\ncredential.username bifrost-mbp\n', '')
    assert identity.check('192.168.10.73:30300', ['weitingzhao'], run) == ([], [])

"""Workspace discovery must work without a developer's home directory."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location('pick_workspace', Path(__file__).with_name('pick.py'))
pick = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pick)


def workspace(path):
    marker = path / pick.MARKER
    marker.parent.mkdir(parents=True)
    marker.touch()
    return path


def test_environment_overrides_ancestor(tmp_path, monkeypatch):
    ancestor = workspace(tmp_path / 'ancestor')
    configured = workspace(tmp_path / 'configured')
    monkeypatch.setenv('BIFROST_WORKSPACE', str(configured))
    monkeypatch.setattr(pick, '__file__', str(ancestor / 'infra/scripts/benchmark/pick.py'))
    assert pick.workspace_root() == configured


def test_ancestor_discovery_from_another_cwd(tmp_path, monkeypatch):
    root = workspace(tmp_path / 'relocated')
    monkeypatch.delenv('BIFROST_WORKSPACE', raising=False)
    monkeypatch.setattr(pick, '__file__', str(root / 'infra/scripts/benchmark/pick.py'))
    monkeypatch.chdir(tmp_path)
    assert pick.workspace_root() == root


def test_invalid_environment_does_not_fall_back(tmp_path, monkeypatch):
    root = workspace(tmp_path / 'ancestor')
    monkeypatch.setenv('BIFROST_WORKSPACE', str(tmp_path / 'missing'))
    monkeypatch.setattr(pick, '__file__', str(root / 'infra/scripts/benchmark/pick.py'))
    with pytest.raises(ValueError, match='BIFROST_WORKSPACE has no'):
        pick.workspace_root()


@pytest.mark.parametrize('arguments,expected', [
    (['/explicit/repo'], [Path('/explicit/repo')]),
    (['--root', '/explicit/root'], [Path('/explicit/root') / name for name in pick.REPOS]),
])
def test_explicit_paths_need_no_workspace(arguments, expected, monkeypatch):
    monkeypatch.setattr(pick.sys, 'argv', ['pick.py', *arguments])
    with patch.object(pick, 'workspace_root', side_effect=AssertionError('must not discover')), \
            patch.object(pick, 'scan', return_value=[]) as scan:
        assert pick.main() == 0
    assert [call.args[0] for call in scan.call_args_list] == expected


def test_missing_workspace_is_cli_error(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('BIFROST_WORKSPACE', raising=False)
    monkeypatch.setattr(pick, '__file__', str(tmp_path / 'pick.py'))
    monkeypatch.setattr(pick.sys, 'argv', ['pick.py'])
    with pytest.raises(SystemExit) as result:
        pick.main()
    assert result.value.code == 2
    assert 'set BIFROST_WORKSPACE or --root' in capsys.readouterr().err

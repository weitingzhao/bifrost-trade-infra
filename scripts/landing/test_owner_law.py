"""The governance check reads agent-config/OWNER_LAW.md (section 8).

Origin of every case here: 2026-11-14. The Owner's directions lived only in the
coordinator's memory; the rule files still carried the old wording, and that night
the lanes filed about ten approval cards that the old wording asked for. The Owner:
a rule file that was not changed is a bug.
"""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'agent-config/scripts/check-governance-consistency.sh'
HEAD = '| # | 哪天 | 要点 | 落在哪 | 机器强制 | 状态 | 旧说法 |\n|---|---|---|---|---|---|---|\n'


def tree(tmp_path, law, rules='## 交单\n交单要短\n'):
    (tmp_path / '.claude/skills').mkdir(parents=True)
    (tmp_path / 'bifrost-platform/config').mkdir(parents=True)
    (tmp_path / 'bifrost-platform/config/ops-context.yaml').write_text('- id: D10\n  status: BLOCKED\n')
    (tmp_path / 'CLAUDE.md').write_text('D10 BLOCKED\n')
    (tmp_path / 'AGENT_FACTS.md').write_text('D10 BLOCKED\n')
    config = tmp_path / 'bifrost-trade-infra/agent-config'
    config.mkdir(parents=True)
    (config / 'CLAUDE.md').write_text(rules)
    (config / 'OWNER_LAW.md').write_text(HEAD + law)
    return config


def check(tmp_path):
    done = subprocess.run(['bash', str(SCRIPT), '--static-tree', str(tmp_path)],
                          capture_output=True, text=True, check=False)
    return done.returncode, done.stdout


ROW = '| 10 | 2026-11-14 | 交单要短 | `agent-config/CLAUDE.md`「交单要短」 | 只有文字 | 已落 | 「输出结构化报告」 |\n'


def test_a_landed_row_that_holds_passes(tmp_path):
    tree(tmp_path, ROW)
    code, out = check(tmp_path)
    assert code == 0, out
    assert '已落 1 行' in out


def test_an_old_wording_left_in_a_rule_file_is_red(tmp_path):
    # Positive control of the case above: the same row, the superseded sentence written back.
    tree(tmp_path, ROW, rules='交单要短\n完成后输出结构化报告\n')
    code, out = check(tmp_path)
    assert code == 1 and '旧说法：输出结构化报告' in out, out


def test_a_landed_row_pointing_at_a_sentence_that_is_gone_is_red(tmp_path):
    tree(tmp_path, ROW, rules='别的内容\n')
    code, out = check(tmp_path)
    assert code == 1 and '找不到这一句：交单要短' in out, out


def test_a_landed_row_pointing_at_a_missing_file_is_red(tmp_path):
    tree(tmp_path, ROW.replace('agent-config/CLAUDE.md', 'agent-config/GONE.md'))
    code, out = check(tmp_path)
    assert code == 1 and '指的文件不存在：agent-config/GONE.md' in out, out


def test_a_row_not_landed_does_not_bind_the_rule_files(tmp_path):
    # Until a row lands, the rule files still carry the old wording; that is the stated state.
    tree(tmp_path, ROW.replace('| 已落 |', '| 未落：等重签 |') + ROW.replace('| 10 |', '| 11 |').replace('「输出结构化报告」', '—'),
         rules='交单要短\n完成后输出结构化报告\n')
    code, out = check(tmp_path)
    assert code == 0, out


def test_a_table_no_row_can_be_read_from_is_red(tmp_path):
    # Positive control against the check running empty (a column added or dropped).
    tree(tmp_path, '| 10 | 2026-11-14 | 交单要短 | `agent-config/CLAUDE.md`「交单要短」 | 已落 | — |\n')
    code, out = check(tmp_path)
    assert code == 1 and '一行「已落」都读不出来' in out, out


def test_this_repository_holds_its_own_table(tmp_path):
    (tmp_path / '.claude/skills').mkdir(parents=True)
    (tmp_path / 'bifrost-platform/config').mkdir(parents=True)
    (tmp_path / 'bifrost-platform/config/ops-context.yaml').write_text('- id: D10\n  status: BLOCKED\n')
    (tmp_path / 'CLAUDE.md').write_text('D10 BLOCKED\n')
    (tmp_path / 'AGENT_FACTS.md').write_text('D10 BLOCKED\n')
    infra = tmp_path / 'bifrost-trade-infra'
    (infra / 'agent-config/claude').mkdir(parents=True)
    for name in ('CLAUDE.md', 'OWNER_EXEC.md', 'AGENT_MODES.md', 'OWNER_LAW.md'):
        shutil.copy(ROOT / 'agent-config' / name, infra / 'agent-config' / name)
    shutil.copytree(ROOT / 'agent-config/claude/skills', infra / 'agent-config/claude/skills')
    (infra / 'docs').mkdir()
    shutil.copy(ROOT / 'docs/RELEASE.md', infra / 'docs/RELEASE.md')
    code, out = check(tmp_path)
    assert code == 0, out

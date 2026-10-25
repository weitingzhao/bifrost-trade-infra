"""D-L5 approval text and the signed command must describe the same disposition."""
import json
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2] / 'agent-config/work/multi-agent'
ARTIFACTS = ROOT / 'd-l5-2026-10-25'


@pytest.mark.parametrize('environment', ['stg', 'prod'])
def test_signed_sql_and_reason_match_review_copies(environment):
    request = json.loads((ARTIFACTS / f'{environment}-request-action.json').read_text())
    assert request['reason'] == request['params']['reason']
    command = request['params']['command']
    embedded = command.split("<<'D_L5_SQL'\n", 1)[1].split('\nD_L5_SQL\n', 1)[0] + '\n'
    assert embedded.encode() == (ARTIFACTS / f'{environment}-no-merge.sql').read_bytes()
    subprocess.run(['bash', '-n'], input=command, text=True, check=True)


def test_prod_recovered_work_keeps_no_merge_without_being_a_drill():
    request = json.loads((ARTIFACTS / 'prod-request-action.json').read_text())
    sql = (ARTIFACTS / 'prod-no-merge.sql').read_text()
    ticket = (ROOT / 'TICKET-D-L5-landing-s0-2026-10-24.md').read_text()
    recovered = re.search(r"CASE WHEN mission_id IN \('M-1','M-2','M-4'\) THEN '(.*?)'::text ELSE '(.*?)'::text END", sql)
    assert recovered
    for text in (request['reason'], recovered[1]):
        for term in ('Owner', '不是演练', 'w31/dl5-comments', 'platform main', '2026-10-25',
                     '93399f27', 'ce5d2c30', 'ca4f8149', 'no_merge', '原尝试不合入'):
            assert term in text
    assert '历史演练' not in recovered[1]
    assert '历史演练' in recovered[2] and '已处置、未交付' in recovered[2]
    prod = ticket.split('## PROD 当前 mission 与全部任务', 1)[1]
    for mission, commit in [('M-1', 'ce5d2c30'), ('M-2', 'ca4f8149'), ('M-4', '93399f27')]:
        section = prod.split(f'### {mission} ·', 1)[1].split('\n##', 1)[0]
        assert '不是演练' in section and '历史演练' not in section
        assert commit in section and '原尝试不合入' in section
    assert '除上述已用新提交取回的三项外' in ticket
    assert sql.count('UPDATE agentrt.mission') == 1
    assert "WHERE mission_id IN ('M-1','M-13','M-15','M-2','M-3','M-4');" in sql

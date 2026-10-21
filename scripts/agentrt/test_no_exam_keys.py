"""No repository an Agent host can check out holds the chief exam's grading keys (TD-396).

    python3 -m pytest -q scripts/agentrt/test_no_exam_keys.py

The chief of staff's qualifying exam (W-31 2.4; CUT-chief-exam-2026-10-19.md) is graded by
rules kept out of every repository: agentd on the Agent host checks infra out (since 10-19) and
every repository is public on GitHub, so keys here are keys the examinee, or anyone, can read,
and the exam would measure recall instead of judgement. They live on the Owner's Mac beside the
set (~/agent-work/chief-exam-2026-10-19/) and, for grading, in the platform's exam Secret.

Three ways keys have leaked or would, each refused here over every tracked file:
  - a rule id of the set (only its sha256 is kept below, never the id; regenerate with
    python3 -I ~/agent-work/chief-exam-2026-10-19/keyhashes.py when the set changes);
  - a table of the sub-questions (three or more rows that start with a sub-question such as
    | Q3a |), the shape of the cut's old §10;
  - a file of the set itself (q<n>-<name>.json, controls.json, grade_reference.py).

The pre-commit hook (agent-config/scripts/git-hooks/pre-commit) runs the same checks over the
staged copies of what a commit stages: python3 -I scripts/agentrt/test_no_exam_keys.py --staged.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULE_ID_SHA256 = {
    "1168ce8d46f362de398e9932d3bc95cfaee2a54d5083da48e3211a503a7355db",
    "14624f2ec2a5390e862eadcca1699c6e5e2dc0d8a3efe2b65210a53d51f63187",
    "313101751b93a3ae6e21fa1f9aaef890fce667934fe04e53e822a50beaf84484",
    "33bffa7fb5db286de0d1c39bd180ad28a1c6183ffc3326f9c0b08f488db28977",
    "60190d8b60dc300784905e06ffc5e07e915cc97726046d03955d45cea6b87705",
    "6967d9e8c29c1ff956bb28f663f8dd6bdec9a29d85b49eecd14fe0939fdea83d",
    "71aa7947444de601d88ad5231d8d6e24c6dd10d46ba53d035911d20ef3a945b4",
    "7519f503bb8e987e0ff0246fe15db9618464bfe902bcf802f997231c99d60ded",
    "775ec12f795e3b8937dc90f933217e007a024bd2d3bb9cc59b305a87721bcacb",
    "999a4c403ee8171a7976838dce7206a42aeb0daffa3545b0b45c3d613764645b",
    "9e589e859b53a2ba6c2291a3bd675f1f11ecd59a97f9e7d05d51fc6635b6969d",
    "aae503232c2638c4fba48e83ba6112bbdc72c7ed79a06626ae1fef53f8d3a47b",
    "ad44f983fd97e56483410ffcea97d6989f64772ff192cb469a12ffffcaa37776",
    "b01980bba922151d93e582030c85004d1913699039422fb37c64a4d86991ce7e",
    "b4a1510ee29ef9710d6170e25294a5dc12c1b25b5539ffb74adca4bf5d284b26",
    "b9f0f3598dda85e05ce45fe7df0ca7421c2210d1de8459402f6925b54471fba6",
    "bbcd0965dee081d1f37125806565ef39bb778bb8d06f47ad712309fc850bf691",
    "bd60ec61be6a111f955ba44a85e44e0be5c9365940ab1b539bd718f63b2120e6",
    "bd77bcd73ef6a04c7380c97303b2e147974931cea8e65b39b27bbfa75ba4089e",
    "bf65c344dd70f8276d78ca64c7d4a987d6f7d2a7eca8aa6022fc862b9c2a820d",
    "bfe8474b9351154561c73cb8401bacfd9498e52a2d9df337b4e9d045c86746a1",
    "c06c2b3568f20decd600cde9de74aa3bc0cd8e64d2107b31104197d2d9b5f75a",
    "d15f8d4eac4d7c3a835da05c5ce4059c2ac9d675ec2c46258f88d6c508052710",
    "d25931b9a27426b193439fd1fb769866d986cacd1234c2e7578a8ab9f56a14b3",
    "d2946c470a22c3267c6e250b668ccb378a20dc28375a7ab8fa121009c1e0b711",
    "d60acf00e6858b65dadfb273c3395d9cfc8ee80a8be3efe4bb7451f7c64505f5",
    "d94d2290744f94efb2e9344c8545bf1401171355fb318dfdc3e7f1ef549339cb",
    "d9d315bd6bfb072fc104dfc73e2590bdfdd453952172da23e376f315e46db161",
    "e8f811173ddb303c183d8880b80789d77e107d02a98f5dfcf8f4b90c07a16a2e",
    "ef819fa902318de15882448d1cc653e1bbd9a227ff98482576d54897b32db2fb",
}
TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){2,}")
ITEM_ROW = re.compile(r"^\|\s*Q[1-5][a-e]\s*\|", re.MULTILINE)
SET_FILE = re.compile(r"(^|/)(q[1-5]-[a-z0-9-]+\.json|controls\.json|grade_reference\.py)$")
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".txt", ".go", ".ts", ".tsx", ".service", ".toml", ""}


def tracked() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True).stdout
    return [p for p in out.decode().split("\0") if p]


def text(path: str) -> str | None:
    p = ROOT / path
    if p.suffix not in TEXT_SUFFIXES or not p.is_file() or p.stat().st_size > 2_000_000:
        return None
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def test_the_set_has_ids_to_look_for() -> None:
    assert len(RULE_ID_SHA256) >= 20 and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in RULE_ID_SHA256)


def test_no_file_of_the_set_is_tracked() -> None:
    found = [p for p in tracked() if SET_FILE.search(p)]
    assert found == [], f"files of the chief exam's set are tracked: {found} (TD-396: they stay on the Owner's Mac)"


def test_no_tracked_text_names_a_rule_of_the_set() -> None:
    found = []
    for path in tracked():
        body = text(path)
        if body is None:
            continue
        hits = sorted({t for t in TOKEN.findall(body) if hashlib.sha256(t.encode()).hexdigest() in RULE_ID_SHA256})
        if hits:
            found.append(f"{path}: {len(hits)} rule id(s) of the chief exam's set")
    assert found == [], "grading keys of the chief exam in the repository (TD-396): " + "; ".join(found)


def test_no_tracked_text_lists_the_sub_questions() -> None:
    found = [p for p in tracked() if (body := text(p)) is not None and len(ITEM_ROW.findall(body)) >= 3]
    assert found == [], f"a table of the chief exam's sub-questions (the old §10's shape) in {found} (TD-396)"


def findings(path: str, body: str | None) -> list[str]:
    """What of the three a file holds: its path and the kind of key, never the key."""
    out = []
    if SET_FILE.search(path):
        out.append("a file of the set")
    if body is not None:
        if any(hashlib.sha256(t.encode()).hexdigest() in RULE_ID_SHA256 for t in TOKEN.findall(body)):
            out.append("a rule id of the set")
        if len(ITEM_ROW.findall(body)) >= 3:
            out.append("a table of the sub-questions")
    return out


def staged() -> int:
    """The pre-commit check: the staged copy of every file the commit adds or changes."""
    names = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                           check=True, capture_output=True).stdout.decode().split("\0")
    bad = []
    for path in filter(None, names):
        body = None
        if Path(path).suffix in TEXT_SUFFIXES:
            blob = subprocess.run(["git", "-C", str(ROOT), "show", ":" + path], capture_output=True).stdout
            try:
                body = blob.decode("utf-8") if len(blob) <= 2_000_000 else None
            except UnicodeDecodeError:
                body = None
        bad += [f"{path}: {what}" for what in findings(path, body)]
    for line in bad:
        print(f"pre-commit: the chief exam's grading keys stay out of the repository (TD-396): {line}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--staged"]:
        sys.exit("usage: test_no_exam_keys.py --staged")
    sys.exit(staged())

"""The command of the card that signs a staged release policy (TD-576).

Origin: 决定 2026-11-15: re-signing must not need the computer that holds
the key. The first design put the policy text in the card's command; the
text lists the D10 paths, and platform-api classifies an owner_run_command
whose text names one as tier X (actions/ownerrun_d10.go). So the command names
the text only by its sha256 and reads it from the cluster.
"""
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
SHA = "9e9911bd161cdd94f3ff5a7a68d2e081709deb3cef3750e96f938ae6fa4f233c"


def card_command(sha: str) -> str:
    return subprocess.run([sys.executable, str(HERE / "release_policy.py"), "card", "--sha256", sha],
                          check=True, capture_output=True, text=True).stdout


def test_the_command_is_one_line_names_the_sha_and_checks_it_before_the_key_is_read():
    cmd = card_command(SHA)
    assert cmd.count("\n") == 1 and cmd.endswith("\n")
    assert f"want={SHA};" in cmd
    check, key = cmd.index("sha256sum -c"), cmd.index("get secret release-policy-signer")
    assert check < key < cmd.index("ssh-keygen -Y sign") < cmd.index("patch configmap")
    assert "rm -f key" in cmd


def test_the_command_names_no_d10_path():
    """A word of the command that is a no_d10_paths file, or a directory two or
    more segments above one, makes the card tier X. Control: the policy text
    itself has such words, which is why it does not ride in the command."""
    paths = json.loads((REPO / "agent-config/release-policy/paths.json").read_text())["paths"]["no_d10_paths"]
    fixed = [re.split(r"[*?]", p)[0] for rule in paths for p in rule["paths"]]

    def hit(text: str) -> bool:
        for word in re.split(r"[^A-Za-z0-9_./*?-]+", text):
            word = word.strip("./")
            for i in range(len(word)):
                if i and word[i - 1] != "/":
                    continue
                tail = word[i:]
                if "/" in tail and any(f == tail or f.startswith(tail + "/") for f in fixed):
                    return True
        return False

    assert not hit(card_command(SHA))
    assert hit(json.dumps(paths))


def test_the_command_prints_no_secret_and_starts_nothing_in_the_background():
    cmd = card_command(SHA)
    assert "-o yaml" not in cmd and "cat key" not in cmd
    assert not re.search(r"(?<!&)&(?!&)\s*(;|$)", cmd) and "nohup" not in cmd
    for trap in ("--raw", "--dry-run", "--kubeconfig", "--server", "--token"):
        assert trap not in cmd


def test_a_sha_that_is_not_64_hex_is_refused():
    r = subprocess.run([sys.executable, str(HERE / "release_policy.py"), "card", "--sha256", "abc; rm -rf /"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and r.stdout == ""

import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "verify_materials", HERE / "verify_materials.py"
)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

# Shared with platform api/internal/agentrt/rules/s5check/testdata/
# ci-materials-golden.json (Go s5check.ToolchainDigest and the TS checker's
# canonical encoder reproduce the same values): one toolchainDigest definition.
LOCK_DIGEST = "05bdcf4a2b3596ca40667cb8010e682c5bab2630076275351876f68f8aab54e7"
EDGE_LOCK = {
    "typescript": {
        "version": "5.9.3",
        "note": '<>& \u0001\u007f é 😀 "q" \\\\',
    },
    "z": [3, 2, 1, {"10": 1, "2": 2}],
    "": True,
}
EDGE_DIGEST = "29397cbaa2ed45b897bc8927c044e90e2363de00f08d73005c46ceb659bbfa25"


def test_toolchain_digest_matches_cross_language_golden():
    lock = json.loads((HERE / "TOOLS.lock.json").read_text())
    assert v.toolchain_digest(lock) == LOCK_DIGEST
    assert v.toolchain_digest(EDGE_LOCK) == EDGE_DIGEST
    for bad in [[], {}, {"typescript": {}}, {"node": {"version": "22.14.0"}}]:
        with pytest.raises(ValueError):
            v.toolchain_digest(bad)


def image(tmp_path, materials, raw=None):
    (tmp_path / "TOOLS.lock.json").write_text((HERE / "TOOLS.lock.json").read_text())
    (tmp_path / "materials.json").write_text(
        raw if raw is not None else v.canonical(materials).decode() + "\n"
    )
    return tmp_path


BUILT = {
    "profileDigest": "a" * 64,
    "toolchainDigest": LOCK_DIGEST,
    "callersDigest": "c" * 64,
    "typesDigest": "d" * 64,
    "testsDigest": "e" * 64,
    "uiSHA": "7" * 40,
}


def test_verify_accepts_complete_materials_bound_to_the_lock(tmp_path):
    v.verify(image(tmp_path, BUILT))


@pytest.mark.parametrize(
    "change",
    [
        {"toolchainDigest": "b" * 64},
        {"uiSHA": "0" * 40},
        {"testsDigest": "0" * 64},
        {"extra": "x"},
        {"callersDigest": "C" * 64},
    ],
)
def test_verify_rejects_incomplete_or_unbound_materials(tmp_path, change):
    with pytest.raises(ValueError):
        v.verify(image(tmp_path, {**BUILT, **change}))


def test_verify_rejects_noncanonical_materials(tmp_path):
    with pytest.raises(ValueError, match="canonical"):
        v.verify(image(tmp_path, None, json.dumps(BUILT, indent=1)))


def test_placeholder_is_all_zero_and_only_for_unbuilt():
    zero = {k: "0" * len(x) for k, x in BUILT.items()}
    assert v.check_materials(zero, placeholder=True) == zero
    with pytest.raises(ValueError, match="missing"):
        v.check_materials(zero)
    with pytest.raises(ValueError, match="placeholder"):
        v.check_materials(BUILT, placeholder=True)

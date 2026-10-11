"""The suite must not leave files under scripts/release/prod_matrix/."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session", autouse=True)
def prod_matrix_tree_stays_clean():
    yield
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "scripts/release/prod_matrix"],
        cwd=REPO,
    )
    assert status.decode() == "", status.decode()

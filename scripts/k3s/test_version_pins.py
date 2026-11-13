"""The upstream-URL installs read their version from scripts/k3s/versions.env.

Before 2026-11-13 they defaulted to `latest` / `stable`, so re-running an
install script upgraded the cluster to whatever upstream had that day and
nothing in the repository said which version was running.
"""

from __future__ import annotations

import re
from pathlib import Path

K3S = Path(__file__).resolve().parent
PINS = K3S / "versions.env"
SCRIPTS = [
    "install-stack-tekton.sh",
    "install-cicd-stack.sh",
    "install-tekton-triggers.sh",
    "install-ci-triggers.sh",
    "install-argocd.sh",
]


def pins() -> dict[str, str]:
    out = {}
    for line in PINS.read_text().splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key] = value
    return out


def test_every_pin_is_an_exact_version_with_a_renovate_line():
    lines = PINS.read_text().splitlines()
    assert pins(), "versions.env has no values"
    for i, line in enumerate(lines):
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            assert re.fullmatch(r"v\d+\.\d+\.\d+", value), f"{key}={value} is not an exact version"
            assert re.fullmatch(r"# renovate: datasource=\S+ depName=\S+", lines[i - 1]), f"{key} has no renovate line above it"


def test_install_scripts_read_the_pins_and_never_default_to_a_moving_tag():
    for name in SCRIPTS:
        text = (K3S / name).read_text()
        assert "/versions.env" in text, f"{name} does not source versions.env"
        moving = re.findall(r"_VERSION:-(?:latest|stable)\}", text)
        assert not moving, f"{name} defaults to a moving tag: {moving}"


def test_tekton_urls_use_the_tagged_release_path():
    # Upstream serves a tag at .../previous/<tag>/; .../<tag>/ is a 404.
    for name in SCRIPTS:
        for url in re.findall(r"tekton-releases/\S+", (K3S / name).read_text()):
            if "VERSION}" in url:
                assert "/previous/${" in url, f"{name}: {url}"

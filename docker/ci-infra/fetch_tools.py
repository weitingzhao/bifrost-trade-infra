"""Build-only downloads, checked against pinned SHA-256 before use."""
import hashlib
import os
import urllib.request
from pathlib import Path

ASSETS = (
    ("https://go.dev/dl/go1.25.3.linux-amd64.tar.gz", "/tmp/go.tar.gz",
     "0335f314b6e7bfe08c3d0cfaa7c19db961b7b99fb20be62b0a826c992ad14e0f"),
    ("https://dl.k8s.io/release/v1.31.4/bin/linux/amd64/kubectl", "/usr/local/bin/kubectl",
     "298e19e9c6c17199011404278f0ff8168a7eca4217edad9097af577023a5620f"),
)


def main():
    for url, destination, digest in ASSETS:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit("tool_checksum_mismatch " + destination)
        # kubectl is also compared with the publisher's checksum at build time;
        # a downloaded checksum alone is never the trust anchor.
        if destination.endswith("kubectl"):
            with urllib.request.urlopen(url + ".sha256", timeout=30) as response:
                if response.read().decode().strip() != digest:
                    raise SystemExit("publisher_checksum_mismatch kubectl")
        Path(destination).write_bytes(data)
        os.chmod(destination, 0o755 if destination.endswith("kubectl") else 0o644)


if __name__ == "__main__":
    main()

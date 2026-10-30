"""Build-time only. Fixed release archives, no npm lifecycle scripts."""

import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request


def main():
    root = Path("/opt/s5")
    tools = json.loads((root / "TOOLS.lock.json").read_text())
    for name, item in tools.items():
        algorithm = "sha512" if name == "typescript" else "sha256"
        with urllib.request.urlopen(item["url"], timeout=120) as response:
            data = response.read()
        if hashlib.new(algorithm, data).hexdigest() != item[algorithm]:
            raise ValueError("tool checksum mismatch: " + name)
        archive = Path("/tmp/" + name + ".tar.gz")
        archive.write_bytes(data)
        destination = root / (
            "node_modules/typescript" if name == "typescript" else name
        )
        destination.mkdir(parents=True)
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                # All three release archives have a single top-level directory.
                member.name = "/".join(member.name.split("/")[1:])
                if member.name:
                    tf.extract(member, destination, filter="data")
        archive.unlink()


if __name__ == "__main__":
    main()

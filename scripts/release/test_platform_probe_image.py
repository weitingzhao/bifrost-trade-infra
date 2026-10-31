"""W-31 B5: the platform image carries the read-only pre-open probe.

CANARY.md (platform api/cmd/stg-release-probe) runs it as a one-off Job on the
workers' exact image digest, so the binary must be in that image. PROD builds
nothing (TD-335): it promotes what bifrost-deliver-platform built from this file.
"""

from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "k8s/cicd/docker/Dockerfile.platform-api-stg"


def test_probe_is_built_and_installed_but_not_the_entrypoint() -> None:
    lines = [line.strip() for line in DOCKERFILE.read_text().splitlines()]
    build = "RUN CGO_ENABLED=0 GOOS=linux go build -o /stg-release-probe ./cmd/stg-release-probe"
    copy = "COPY --from=builder /stg-release-probe /usr/local/bin/stg-release-probe"
    assert build in lines and copy in lines
    final = lines.index("FROM alpine:3.20")
    assert lines.index(build) < final < lines.index(copy)
    assert lines[-1] == 'ENTRYPOINT ["platform-api"]'

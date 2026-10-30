# linux/amd64 only. This seed pin is published by Docker Official Images.
# Before the FIRST build, coordinator must resolve the build-day 3.12 tag,
# update FROM + TOOLS.expected, and review the lock change (design §5.3).
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

RUN apt-get update && apt-get install -y --no-install-recommends \
    git=1:2.39.5-0+deb12u3 bash=5.2.15-2+b13 ca-certificates=20250419~deb12u2 \
    && rm -rf /var/lib/apt/lists/*

COPY docker/ci-infra/fetch_tools.py /opt/ci-infra/fetch_tools.py
RUN python3 -I /opt/ci-infra/fetch_tools.py \
    && tar -C /usr/local -xzf /tmp/go.tar.gz && rm /tmp/go.tar.gz
ENV PATH="/opt/ci-python/bin:/usr/local/go/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GOTOOLCHAIN=local

COPY docker/ci-infra/requirements.lock docker/ci-infra/TOOLS.expected /opt/ci-infra/
# The global environment stays untouched. quick gets its own venv from the
# platform generator; the isolated CI interpreter also uses the same wheels.
RUN python3 -m pip download --require-hashes --only-binary=:all: \
    --dest /opt/wheels -r /opt/ci-infra/requirements.lock \
    && python3 -m venv /opt/ci-python \
    && /opt/ci-python/bin/python3 -m pip install --no-index --find-links /opt/wheels \
       --require-hashes --only-binary=:all: -r /opt/ci-infra/requirements.lock
COPY scripts/landing/ci-infra.sh scripts/landing/coverage_infra.py scripts/landing/doc_policy.py scripts/landing/doc_consumers.py /opt/ci-infra/
RUN bash /opt/ci-infra/ci-infra.sh --stage tools
WORKDIR /ws

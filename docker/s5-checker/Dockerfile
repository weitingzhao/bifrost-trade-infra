# Build context: separately reviewed infra/ and platform/ checkouts. Never R.
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git=1:2.39.5-0+deb12u3 ca-certificates=20250419~deb12u2 \
    && rm -rf /var/lib/apt/lists/*
COPY infra/docker/s5-checker/TOOLS.lock.json infra/docker/s5-checker/fetch_tools.py /opt/s5/
RUN python3 -I /opt/s5/fetch_tools.py
ENV PATH="/opt/s5/go/bin:/opt/s5/node/bin:${PATH}" GOTOOLCHAIN=local CGO_ENABLED=0
RUN test "$(node --version)" = v22.14.0 \
    && test "$(node -p 'require("/opt/s5/node_modules/typescript/package.json").version')" = 5.9.3 \
    && test "$(go version)" = 'go version go1.26.4 linux/amd64'

FROM tools AS build
COPY platform/api/ /build/api/
WORKDIR /build/api
# go.sum authenticates modules; no candidate package.json, scripts or Makefile.
RUN go mod download && go mod verify \
    && go build -mod=readonly -trimpath -o /opt/s5/bin/s5check ./cmd/s5check
COPY platform/api/internal/agentrt/rules/s5check/ /opt/s5/s5check/
# This CLI is supplied by line A. Missing CLI/materials is a build failure.
RUN /opt/s5/bin/s5check --ci-materials /opt/s5/s5check /opt/s5/TOOLS.lock.json > /opt/s5/materials.json
COPY infra/docker/s5-checker/verify_materials.py /opt/s5/verify_materials.py
RUN python3 -I /opt/s5/verify_materials.py

FROM tools AS runtime
COPY --from=build /opt/s5/bin/ /opt/s5/bin/
COPY --from=build /opt/s5/s5check/ /opt/s5/s5check/
COPY --from=build /opt/s5/materials.json /opt/s5/materials.json
COPY infra/docker/s5-checker/runner.py /opt/s5/runner.py
RUN ln -s /opt/s5/node/bin/node /usr/local/bin/node \
    && rm -rf /opt/s5/go \
    && chmod -R a-w /opt/s5
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/s5
ENTRYPOINT ["python3", "-I", "/opt/s5/runner.py"]

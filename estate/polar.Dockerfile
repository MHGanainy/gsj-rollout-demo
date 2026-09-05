# estate/polar.Dockerfile — the Polar leg of the demo estate, as ONE image.
#
# What it carries and why (ADR-0001 of this repo):
#   - Polar (NVIDIA ProRL-Agent-Server) installed from the PUBLIC library
#     repo's vendored, patched tree at a pinned ref — the same bytes the
#     library's estate runs, patches P1-P3 included. No Polar venv, no
#     checkout for the stranger: CP-32's F-45 measured exactly that seam.
#   - gsj-harness-rollout-server from PyPI, pinned — same site-packages, so
#     Polar's import_path resolves gsj_rollout.pi_harness with no PYTHONPATH.
#   - the docker CLI (client only) — Polar's DockerRuntime shells out to
#     `docker create/start/exec/cp/rm`; with /var/run/docker.sock mounted,
#     episode containers start as SIBLINGS on the host daemon.
#   - git + pyarrow — the corpus pipeline's scaffold/verify clones and the
#     taskbank's parquet run inside this image, on the estate network.
#
# Build (maintainers; strangers pull from GHCR). MULTI-ARCH is load-bearing:
# a single-platform build inherits the build host's architecture and dies as
# `exec format error` on the other one — measured, Apple-Silicon build vs
# amd64 estate box, CP-34 smoke:
#   docker buildx build -f estate/polar.Dockerfile \
#     --platform linux/amd64,linux/arm64 \
#     --build-arg LIB_REF=v<lib-version> --build-arg LIB_VERSION=<lib-version> \
#     -t ghcr.io/mhganainy/gsj-polar:<polar-sha8>-gsj<lib-version> --push estate/

FROM docker:28-cli AS dockercli

FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

# The library repo pin: vendor/polar/ in this tree is Polar at
# POLAR_SHA f0e8343a with patches P1-P3 already applied (committed post-patch).
ARG LIB_REPO=https://github.com/MHGanainy/gsj-harness-rollout-server
ARG LIB_REF=main
RUN git clone --depth 1 --branch ${LIB_REF} ${LIB_REPO} /tmp/lib \
 && mkdir -p /opt/gsj \
 && git -C /tmp/lib rev-parse HEAD > /opt/gsj/library-repo.sha \
 && cp /tmp/lib/POLAR_SHA /opt/gsj/POLAR_SHA \
 && pip install --no-cache-dir /tmp/lib/vendor/polar \
 && rm -rf /tmp/lib

# The wheel, from PyPI, pinned. pyarrow serves the corpus pipeline's
# taskbank/verify and `gsj-rollout submit --from-bank`; it is an IMAGE
# dependency, never a library one (the root pyproject stays parquet-free).
ARG LIB_VERSION=0.1.8
RUN pip install --no-cache-dir gsj-harness-rollout-server==${LIB_VERSION} pyarrow

WORKDIR /estate

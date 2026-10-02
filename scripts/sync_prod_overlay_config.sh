#!/usr/bin/env bash
# RETIRED 2026-10-02 (debt TD-06). This script regenerated the deployed overlay config
# (k8s/overlays/prod/config/config.prod.yaml) from a root copy and hard-coded heredocs. Each run silently reverted overlay
# edits: baece5b dropped server.architecture.ops_port (api-monitor CrashLoop, fixed in
# 6580885) and turned PROD platform audit off (TD-05).
#
# The overlay file is now the only config for its K3s env. Edit it directly, commit, and
# let the deliver pipeline's gitops-sync (STG/PROD) or `kubectl apply -k` (DEV) apply it.
# Secrets stay in the bifrost-<env>-secrets Secret, never in the overlay.
echo "sync_prod_overlay_config.sh is retired: edit k8s/overlays/prod/config/config.prod.yaml directly (see the header of this script)." >&2
exit 1

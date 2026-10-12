#!/bin/sh
# Age only. Pinned identically to cluster-state-backup; no kubectl/keygen.
set -eu
set -o pipefail
AGE_URL=https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz
AGE_SHA=cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10
cd /tools
wget -q -O age.tar.gz "$AGE_URL"
printf '%s  %s\n' "$AGE_SHA" age.tar.gz | sha256sum -c -
tar -xzf age.tar.gz age/age
mv age/age /tools/age.bin
rm -rf age age.tar.gz
mv /tools/age.bin /tools/age
chmod 755 /tools/age

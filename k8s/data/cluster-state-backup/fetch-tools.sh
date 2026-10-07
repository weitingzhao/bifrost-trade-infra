#!/bin/sh
# Pull pinned static age and kubectl into /tools. Checksums are verified
# before either binary is kept. The archive also contains a key generator;
# only the age binary is unpacked.
set -eu

AGE_URL=https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz
AGE_SHA=cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10
KUBECTL_URL=https://dl.k8s.io/release/v1.35.5/bin/linux/amd64/kubectl
KUBECTL_SHA=90f75ea6ecc9ea5633262e1c0b83a40560003b30fc94a04cb099404fcef0c224

cd /tools
wget -q -O age.tar.gz "$AGE_URL"
printf '%s  %s\n' "$AGE_SHA" age.tar.gz | sha256sum -c -
tar -xzf age.tar.gz age/age
mv age/age /tools/age.bin
rm -rf age age.tar.gz
mv /tools/age.bin /tools/age
chmod 755 /tools/age

wget -q -O /tools/kubectl "$KUBECTL_URL"
printf '%s  %s\n' "$KUBECTL_SHA" kubectl | sha256sum -c -
chmod 755 /tools/kubectl

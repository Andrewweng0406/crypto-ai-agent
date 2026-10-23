#!/usr/bin/env bash
set -Eeuo pipefail
# Run locally on a freshly created Ubuntu 24.04 ARM64 Oracle VM.
# Idempotent; installs Docker Engine and Compose from Docker's official apt repository.
if [[ $(id -u) -ne 0 ]]; then
  echo "Run as: sudo bash deploy/oci/install-docker-ubuntu.sh" >&2
  exit 1
fi
if [[ $(uname -m) != aarch64 && $(uname -m) != arm64 ]]; then
  echo "This pilot targets ARM64; actual arch: $(uname -m)" >&2
  exit 1
fi
. /etc/os-release
if [[ "${ID:-}" != ubuntu ]]; then
  echo "Unsupported host OS (expected Ubuntu)" >&2
  exit 1
fi
apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl --fail --show-error --silent --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version
docker compose version
echo "Docker ready. Do NOT put secrets on the command line or in GitHub."

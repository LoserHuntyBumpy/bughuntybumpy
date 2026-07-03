#!/usr/bin/env bash
# BugHuntyBumpy - Linux-Deploy Wrapper: prereqs -> bootstrap -> deploy.
# Aufruf:  sudo deploy/deploy.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

bash "$HERE/00_prereqs.sh"
bash "$HERE/01_bootstrap.sh"
bash "$HERE/02_deploy.sh"

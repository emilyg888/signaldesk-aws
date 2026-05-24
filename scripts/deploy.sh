#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to build the pipeline Lambda container image, but docker was not found on PATH." >&2
  echo "Install and start Docker Desktop, OrbStack, or another Docker-compatible runtime, then rerun make deploy." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but not running or not reachable. Start your Docker runtime, then rerun make deploy." >&2
  exit 1
fi
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r infrastructure/requirements.txt
cd infrastructure
cdk bootstrap
cdk deploy --all --require-approval never

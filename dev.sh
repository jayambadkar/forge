#!/usr/bin/env bash
# Start the Forge API and the workstation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="${HOME}/.dotnet:${PATH}"
export DOTNET_ROOT="${DOTNET_ROOT:-$HOME/.dotnet}"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export FORGE_ROOT="$ROOT"
cd "$ROOT"
dotnet run --project backend/Forge.Api.csproj --urls http://0.0.0.0:43124 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
npm --prefix frontend run dev

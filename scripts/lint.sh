#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.dotnet:${PATH}"
export DOTNET_ROOT="${DOTNET_ROOT:-$HOME/.dotnet}"

ruff check .
mypy
dotnet format backend/Forge.Api.csproj --verify-no-changes
dotnet build backend/Forge.Api.csproj --nologo
npm --prefix frontend run lint
( cd frontend && npx tsc -p tsconfig.app.json --noEmit --pretty false )

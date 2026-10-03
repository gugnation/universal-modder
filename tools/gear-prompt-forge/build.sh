#!/usr/bin/env bash
# Cross-compiles GearPromptForge.exe (Windows x64) from any OS with Go installed.
set -euo pipefail
cd "$(dirname "$0")"
go run github.com/akavel/rsrc@v0.10.2 -manifest gear-prompt-forge.manifest -ico assets/icon.ico -arch amd64 -o rsrc_windows_amd64.syso
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -H windowsgui" -o "${1:-GearPromptForge.exe}" .
rm -f rsrc_windows_amd64.syso
echo "built ${1:-GearPromptForge.exe}"

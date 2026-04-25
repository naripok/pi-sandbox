#!/bin/bash
set -euo pipefail

IMAGE_NAME="${PI_AGENT_IMAGE:-pi-agent-isolated}"
CONTAINER_NAME="pi-agent-$(basename "$PWD")"
GLOBAL_CONFIG="${PI_AGENT_CONFIG:-${HOME}/.pi/agent}"

# Ensure mount sources exist
mkdir -p "${GLOBAL_CONFIG}"
mkdir -p "${GLOBAL_CONFIG}/sessions"

# Build image if it doesn't exist
if ! podman image exists "$IMAGE_NAME"; then
    echo "Building image ${IMAGE_NAME}..."
    podman build -t "$IMAGE_NAME" "$(dirname "$0")"
fi

# Allocate TTY only when stdin is a terminal
TTY_FLAG=""
[ -t 0 ] && TTY_FLAG="-t"

exec podman run -i ${TTY_FLAG} --rm \
    --name "$CONTAINER_NAME" \
    --userns=keep-id \
    -v "$(pwd):/workspace" \
    -v "${GLOBAL_CONFIG}:/pi-data:ro" \
    -v "${GLOBAL_CONFIG}/sessions:/pi-data/sessions:rw" \
    -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" \
    -e OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
    "$IMAGE_NAME" \
    "$@"

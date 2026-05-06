#!/bin/bash
set -euo pipefail

IMAGE_NAME="${PI_AGENT_IMAGE:-pi-agent-isolated}"
CONTAINER_NAME="pi-agent-$(basename "$PWD")-${RANDOM}"
GLOBAL_CONFIG="${PI_AGENT_CONFIG:-${HOME}/.pi/agent}"
ENV_FILE="${PI_AGENT_ENV_FILE:-${HOME}/.env}"

# Derive persistent volume name from project path.
# The basename makes "podman volume ls" output meaningful.
# The 8-char hash suffix guarantees uniqueness.
PROJECT_PATH="$(realpath "$(pwd)")"
PROJECT_NAME="$(basename "$PROJECT_PATH")"
PERSIST_VOLUME="pi-agent-persist-${PROJECT_NAME}-$(echo "$PROJECT_PATH" | sha256sum | cut -c1-8)"

# Handle --reset flag: remove the persistent volume and exit.
if [ "${1:-}" = "--reset" ]; then
    podman volume rm "$PERSIST_VOLUME" 2>/dev/null || true
    echo "Volume $PERSIST_VOLUME removed."
    exit 0
fi

# Ensure mount source exists
mkdir -p "${GLOBAL_CONFIG}"

# Create persistent volume (idempotent — no-op if exists).
# Stores sessions, installed tools, and shell config across runs.
podman volume create "$PERSIST_VOLUME" >/dev/null 2>&1 || true

# Build image if it doesn't exist
if ! podman image exists "$IMAGE_NAME"; then
    echo "Building image ${IMAGE_NAME}..."
    podman build -t "$IMAGE_NAME" "$(dirname "$0")"
fi

# Forward all variables defined in the env file
ENV_ARGS=()
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a

    while IFS= read -r key; do
        [[ -z "$key" ]] && continue
        ENV_ARGS+=(-e "$key")
    done < <(awk '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*$/ { next }
        {
            gsub(/^[[:space:]]*export[[:space:]]+/, "")
            match($0, /^[[:space:]]*[^=[:space:]]+/)
            if (RLENGTH > 0) {
                key = substr($0, RSTART, RLENGTH)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
                print key
            }
        }
    ' "$ENV_FILE")
fi

# Allocate TTY only when stdin is a terminal
TTY_FLAG=""
[ -t 0 ] && TTY_FLAG="-t"

exec podman run -i ${TTY_FLAG} --rm \
    --name "$CONTAINER_NAME" \
    --userns=keep-id \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --read-only \
    --tmpfs /tmp \
    --pids-limit 1024 \
    --memory 8g \
    --cpus 4 \
    -v "$(pwd):/workspace" \
    -v "${GLOBAL_CONFIG}:/pi-source:ro" \
    -v "${PERSIST_VOLUME}:/home/pi:U" \
    "${ENV_ARGS[@]}" \
    "$IMAGE_NAME" \
    "$@"

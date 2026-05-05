#!/bin/bash
set -euo pipefail

IMAGE_NAME="${PI_AGENT_IMAGE:-pi-agent-isolated}"
CONTAINER_NAME="pi-agent-$(basename "$PWD")-${RANDOM}"
GLOBAL_CONFIG="${PI_AGENT_CONFIG:-${HOME}/.pi/agent}"
ENV_FILE="${PI_AGENT_ENV_FILE:-${HOME}/.env}"

# Ensure mount sources exist
mkdir -p "${GLOBAL_CONFIG}"
mkdir -p "${GLOBAL_CONFIG}/sessions"

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
    -v "${GLOBAL_CONFIG}:/pi-data:ro" \
    -v "${GLOBAL_CONFIG}/sessions:/pi-data/sessions:rw" \
    "${ENV_ARGS[@]}" \
    "$IMAGE_NAME" \
    "$@"

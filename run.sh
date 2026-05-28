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

# --- Per-project package handling ---
# Must be AFTER the --reset handler so `run.sh --reset` works even with invalid .pi-packages

parse_packages() {
    # Parse .pi-packages: strip whitespace, CRLF, skip comments/blanks.
    # Output: space-separated package list on stdout.
    local file="$1"
    if [ ! -f "$file" ]; then
        echo ""
        return
    fi
    # Use || true to prevent pipefail from killing the script when grep finds no matches
    sed 's/\r$//' "$file" | \
        sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | \
        { grep -v '^#' || true; } | \
        { grep -v '^$' || true; } | \
        tr '\n' ' ' || true
}

validate_packages() {
    # Reject .pi-packages lines containing shell metacharacters.
    # Returns 1 and prints error if dangerous characters found.
    local file="$1"
    if [ ! -f "$file" ]; then
        return 0
    fi
    local invalid_line
    invalid_line=$(sed 's/\r$//' "$file" | \
        grep -n '[;|$\`&><*?~\\!]' || true)
    if [ -n "$invalid_line" ]; then
        echo "Error: .pi-packages contains dangerous characters:" >&2
        echo "$invalid_line" >&2
        echo "Only alphanumeric characters, hyphens, dots, and underscores are allowed." >&2
        return 1
    fi
    return 0
}

compute_hash() {
    # Compute deterministic hash of .pi-packages raw bytes.
    # Output: first 8 hex chars of SHA-256.
    local file="$1"
    if [ ! -f "$file" ]; then
        echo ""
        return
    fi
    sha256sum "$file" | cut -c1-8
}

# Read packages only if PI_AGENT_IMAGE is not set (override bypasses .pi-packages entirely)
EXTRA_PACKAGES=""
HAS_PACKAGES=0
if [ -z "${PI_AGENT_IMAGE:-}" ] && [ -f ".pi-packages" ]; then
    if ! validate_packages ".pi-packages"; then
        exit 1
    fi
    EXTRA_PACKAGES=$(parse_packages ".pi-packages")
    if [ -n "$(echo "$EXTRA_PACKAGES" | tr -d '[:space:]')" ]; then
        HAS_PACKAGES=1
    fi
fi

# Ensure mount source exists
mkdir -p "${GLOBAL_CONFIG}"

# Create persistent volume (idempotent — no-op if exists).
# Stores sessions, installed tools, and shell config across runs.
podman volume create "$PERSIST_VOLUME" >/dev/null 2>&1 || true

# Build image if it doesn't exist
if ! podman image exists "$IMAGE_NAME"; then
    echo "Building image ${IMAGE_NAME}..."
    if [ "$HAS_PACKAGES" -eq 1 ]; then
        podman build --build-arg "PACKAGES=${EXTRA_PACKAGES}" -t "$IMAGE_NAME" "$(dirname "$0")"
    else
        podman build -t "$IMAGE_NAME" "$(dirname "$0")"
    fi
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

# Pass extra packages info to the container
if [ "$HAS_PACKAGES" -eq 1 ]; then
    ENV_ARGS+=(-e "EXTRA_PACKAGES=${EXTRA_PACKAGES}")
fi

exec podman run -i ${TTY_FLAG} --rm \
    --name "$CONTAINER_NAME" \
    --userns=keep-id \
    --network=pasta \
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

#!/bin/bash
set -euo pipefail

# Install the pi-agent sandbox.
# Checks prerequisites, builds the container image, and
# prints the alias to add to your shellrc.

IMAGE_NAME="${PI_AGENT_IMAGE:-pi-agent-isolated}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[x]${NC} $*"; exit 1; }

# --- Prerequisites ---

# Bash 4+ (needed for arrays)
bash_version="${BASH_VERSINFO[0]}"
[ "$bash_version" -ge 4 ] || fail "Bash 4+ required (have $bash_version)"

# Podman (rootless)
command -v podman >/dev/null 2>&1 || fail "Podman not found. Install it first: https://podman.io/getting-started/installation"

# Rootless podman setup checks (per https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md)
subuid_entry=$(grep "^$(whoami):" /etc/subuid 2>/dev/null || true)
if [ -z "$subuid_entry" ]; then
    fail "No subuid range for $(whoami). Ask your admin to run:
  sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 $(whoami)"
fi

if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
    fail "XDG_RUNTIME_DIR is not set. Podman needs it for its socket.
  On systemd systems this is /run/user/$(id -u). Try logging out/in or set it manually."
fi

# Final integration check — validates storage, networking, and the podman service
if ! podman info >/dev/null 2>&1; then
    fail "Rootless Podman is not working. Common fixes:
  - Start the background service: podman system service --time=0 &
  - On systemd: systemctl --user start podman
  - See: https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md"
fi

info "Podman is working (v$(podman --version | awk '{print $3}'))"

# --- Build image ---

if podman image exists "$IMAGE_NAME" 2>/dev/null; then
    warn "Image ${IMAGE_NAME} already exists. Rebuild with: podman build -t $IMAGE_NAME ."
else
    info "Building image ${IMAGE_NAME}..."
    podman build -t "$IMAGE_NAME" "$SCRIPT_DIR"
    info "Image built successfully."
fi

# --- Done ---

echo ""
echo "============================="
echo " Sandbox installed!"
echo "============================="
echo ""
echo " Add this alias to your ~/.bashrc (or ~/.zshrc):"
echo ""
echo "   alias pi-sandbox='${SCRIPT_DIR}/run.sh'"
echo ""
echo " Then use it from any project:"
echo ""
echo "   cd ~/Projects/my-project"
echo "   pi-sandbox pi -p \"Review this codebase\""
echo ""
echo " Other commands:"
echo "   pi-sandbox                  # interactive shell in container"
echo "   pi-sandbox npm test         # run any command inside"
echo "   pi-sandbox --reset          # wipe persistent volume for current project"
echo ""

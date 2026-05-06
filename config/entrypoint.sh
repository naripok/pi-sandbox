#!/bin/bash
set -euo pipefail

# Container entrypoint for persistent per-project volume.
# Runs as pi user (USER pi in Containerfile). No privilege drop needed.
# The :U volume mount flag ensures /home/pi is owned by the container user.

DATA_DIR=/home/pi/.pi-agent-data

# Sync host config into persistent volume on every start.
# Propagates new/modified files while preserving user-generated data.
# Excludes sessions/ and lock files to avoid overwriting runtime state.
# Guard: skip if /pi-source is not mounted (e.g. direct podman run).
if [ -d /pi-source ]; then
    rsync -rltDp --no-o --no-g --exclude='sessions/' --exclude='*.lock' /pi-source/. "$DATA_DIR/" || true
fi

# Ensure sessions directory exists
mkdir -p "$DATA_DIR/sessions"

# Copy .bashrc on first run only
if [ ! -f /home/pi/.bashrc ]; then
    cp /etc/pi/.bashrc /home/pi/.bashrc
fi

# Create .bash_profile that sources .bashrc on first run.
# Required for login shells to load PATH and env vars.
if [ ! -f /home/pi/.bash_profile ]; then
    printf 'if [ -f ~/.bashrc ]; then\n  . ~/.bashrc\nfi\n' > /home/pi/.bash_profile
fi

# Configure package managers for user-level installs on first run
if [ ! -d /home/pi/.local ]; then
    mkdir -p /home/pi/.local
    npm config set prefix "/home/pi/.local"
fi

# Set up environment
export HOME=/home/pi
export SHELL=/bin/bash
export USER=pi
export LOGNAME=pi
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"

# Exec the user command
exec "$@"

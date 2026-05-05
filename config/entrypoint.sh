#!/bin/bash
set -euo pipefail

# Container entrypoint for persistent per-project volume.
# Runs as root (USER root in Containerfile), drops to pi via su -l.

DATA_DIR=/home/pi/.pi-agent-data

# Sync host config into persistent volume on every start.
# Propagates new/modified files while preserving user-generated data.
# Excludes sessions/ and lock files to avoid overwriting runtime state.
rsync -au --exclude='sessions/' --exclude='*.lock' /pi-source/. "$DATA_DIR/"

# Ensure sessions directory exists
mkdir -p "$DATA_DIR/sessions"

# Copy .bashrc on first run only
if [ ! -f /home/pi/.bashrc ]; then
    cp /etc/pi/.bashrc /home/pi/.bashrc
fi

# Create .bash_profile that sources .bashrc on first run.
# Required for non-interactive login shells (su -l) to load PATH and env vars.
if [ ! -f /home/pi/.bash_profile ]; then
    printf 'if [ -f ~/.bashrc ]; then\n  . ~/.bashrc\nfi\n' > /home/pi/.bash_profile
fi

# Ensure pi user owns their home directory.
# The :U volume mount flag should handle this, but chown is defense-in-depth
# for the first run and any ownership drift.
chown -R pi:pi /home/pi

# Configure package managers for user-level installs on first run
if [ ! -d /home/pi/.local ]; then
    mkdir -p /home/pi/.local
    su -l pi -c 'npm config set prefix "$HOME/.local"'
fi

# Drop privileges and exec the user command
exec su -l pi -- "$@"

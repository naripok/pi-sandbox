FROM archlinux:latest

ARG EXTRA_PACKAGES=""

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep diffutils python python-pip uv gcc make ast-grep rsync ${EXTRA_PACKAGES} || \
    { echo "" >&2; echo "Error: package installation failed." >&2; echo "Extra packages requested: ${EXTRA_PACKAGES}" >&2; echo "Verify names at https://archlinux.org/packages/ or run 'pacman -Ss <name>' to search." >&2; exit 1; } && \
    pacman -Scc --noconfirm

# Strip setuid/setgid bits — hardening the image
RUN find / \( -path /proc -o -path /sys \) -prune -o -perm /6000 -type f -exec chmod a-s {} +

ARG PI_AGENT_VERSION=0.73.1
RUN npm install -g @mariozechner/pi-coding-agent@${PI_AGENT_VERSION}

RUN useradd -m -u 1000 -s /bin/bash pi

# Clean up root-owned npm artifacts from /home/pi/ that would cause
# EACCES when running as pi. (npm may have created ~/.npm cache during
# the global install above with HOME=/home/pi from a later ENV directive.)
RUN rm -rf /home/pi/.npm /home/pi/.npmrc

# Store .bashrc outside $HOME — it gets copied into the persistent volume at startup.
RUN mkdir -p /etc/pi
COPY config/.bashrc /etc/pi/.bashrc

# Copy and install entrypoint script.
# Runs as pi to sync host config into the persistent volume.
COPY config/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

ENV HOME=/home/pi
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

# Run as pi user. The entrypoint handles volume setup without root.
# With --cap-drop=ALL, root has no capabilities anyway, and :U volume
# flag needs the container user to be pi for correct ownership.
USER pi

# Disable npm lifecycle scripts by default — a malicious or hijacked package
# can run arbitrary code during install, which combined with network access
# creates a direct exfiltration channel. Users can opt-in with
# `npm install --ignore-scripts=false`.
RUN npm config set ignore-scripts true

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

FROM archlinux:latest

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep python uv gcc make ast-grep rsync shadow && \
    pacman -Scc --noconfirm

# Strip setuid/setgid bits — hardening the image
RUN find / \( -path /proc -o -path /sys \) -prune -o -perm /6000 -type f -exec chmod a-s {} +

RUN npm install -g @mariozechner/pi-coding-agent

RUN useradd -m -u 1000 -s /bin/bash pi

# Clean up root-owned npm artifacts from /home/pi/ that would cause
# EACCES when running as pi. (npm may have created ~/.npm cache during
# the global install above with HOME=/home/pi from a later ENV directive.)
RUN rm -rf /home/pi/.npm /home/pi/.npmrc

# Store .bashrc outside $HOME — it gets copied into the persistent volume at startup.
RUN mkdir -p /etc/pi
COPY config/.bashrc /etc/pi/.bashrc

# Copy and install entrypoint script.
# Runs as root to set up the persistent volume, then drops to pi via su.
COPY config/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

ENV HOME=/home/pi
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

# Run as pi user. The entrypoint handles volume setup without root.
# With --cap-drop=ALL, root has no capabilities anyway, and :U volume
# flag needs the container user to be pi for correct ownership.
USER pi
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

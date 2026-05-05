FROM archlinux:latest

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep python uv gcc make ast-grep rsync shadow && \
    pacman -Scc --noconfirm

# Strip setuid/setgid bits — hardening the image
RUN find / \( -path /proc -o -path /sys \) -prune -o -perm /6000 -type f -exec chmod a-s {} +

RUN npm install -g @mariozechner/pi-coding-agent

RUN useradd -m -u 1000 -s /bin/bash pi

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

USER root
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

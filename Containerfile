FROM archlinux:latest

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep python uv gcc make ast-grep && \
    pacman -Scc --noconfirm

# Strip setuid/setgid bits — hardening the image
RUN find / \( -path /proc -o -path /sys \) -prune -o -perm /6000 -type f -exec chmod a-s {} +

RUN npm install -g @mariozechner/pi-coding-agent

RUN useradd -m -u 1000 -s /bin/bash pi

# Store .bashrc outside $HOME — it gets copied at startup since
# --mount type=tmpfs,destination=/home/pi wipes the image layer.
RUN mkdir -p /etc/pi
COPY config/.bashrc /etc/pi/.bashrc

ENV PI_CODING_AGENT_DIR=/pi-data
ENV HOME=/home/pi
ENV TERM=xterm-256color
ENV COLORTERM=truecolor

USER pi
WORKDIR /workspace

# Copy .bashrc into the writable tmpfs home, then launch bash.
CMD ["sh", "-c", "cp /etc/pi/.bashrc $HOME/.bashrc && exec /bin/bash --login"]

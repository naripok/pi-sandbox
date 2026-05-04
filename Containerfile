FROM archlinux:latest

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep python uv gcc make ast-grep && \
    pacman -Scc --noconfirm

# Strip setuid/setgid bits — hardening the image
RUN find / \( -path /proc -o -path /sys \) -prune -o -perm /6000 -type f -exec chmod a-s {} +

RUN npm install -g @mariozechner/pi-coding-agent

RUN useradd -m -u 1000 -s /bin/bash pi

COPY config/.bashrc /home/pi/.bashrc
RUN chown pi:pi /home/pi/.bashrc

ENV PI_CODING_AGENT_DIR=/pi-data
ENV HOME=/home/pi
ENV TERM=xterm-256color

USER pi
WORKDIR /workspace

CMD ["/bin/bash", "--login"]

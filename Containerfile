FROM archlinux:latest

RUN pacman -Syu --noconfirm && \
    pacman -S --noconfirm nodejs npm git openssh bash fd ripgrep && \
    pacman -Scc --noconfirm

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

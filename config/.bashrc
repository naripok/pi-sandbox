# Pi Agent Isolation Environment shell configuration

export PS1='[\u@pi-agent \W]\$ '
alias ls='ls --color=auto'

# Persistent volume paths — tools installed in the container survive across runs.
export PATH="$HOME/.local/bin:$PATH"
export PYTHONUSERBASE="$HOME/.local"
export NPM_CONFIG_PREFIX="$HOME/.local"

# Point pi-coding-agent at the synced config inside the persistent volume.
export PI_CODING_AGENT_DIR="$HOME/.pi-agent-data"

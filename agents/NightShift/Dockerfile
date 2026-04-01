FROM python:3.12-slim

# Install git, gh CLI, and SSH client
RUN apt-get update && apt-get install -y \
    git \
    openssh-client \
    curl \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Node.js (needed for Claude Code CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm i -g @anthropic-ai/claude-code

# Disable Python output buffering for Docker logs
ENV PYTHONUNBUFFERED=1

# Set working directory to engine (where Python code lives)
WORKDIR /app/engine

# Copy requirements and install Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the Python engine
COPY engine/ /app/engine/

# Copy entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create directories for repos, logs, and SSH keys
RUN mkdir -p /app/repos /app/logs /root/.ssh

# Git config
RUN git config --global user.name "NightShift Bot" \
    && git config --global user.email "nightshift@ruh-ai.com"

ENTRYPOINT ["/app/entrypoint.sh"]

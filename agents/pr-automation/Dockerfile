FROM python:3.12-slim

# Install git and gh CLI
RUN apt-get update && apt-get install -y \
    git \
    openssh-client \
    curl \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Node.js (needed for Claude CLI conflict resolution)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI (used for auto-resolving merge conflicts)
RUN npm i -g @anthropic-ai/claude-code

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python deps
COPY github-linear-automation/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the full project
COPY . /app/

# Create directories
RUN mkdir -p /app/repos /root/.ssh

# Git config
RUN git config --global user.name "PR Automation Bot" \
    && git config --global user.email "pr-automation@ruh-ai.com"

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

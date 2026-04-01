FROM node:20-slim

# Install git, gh CLI, openssh, and bash utilities
RUN apt-get update && apt-get install -y \
    git \
    openssh-client \
    curl \
    jq \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install OpenClaw CLI globally (used by the fixer/reviewer agents)
RUN npm i -g openclaw@latest

WORKDIR /app

# Copy the full agent workspace
COPY . /app/

# Create directories
RUN mkdir -p /app/state /app/logs /app/metrics /root/.ssh /root/.openclaw

# Make scripts executable
RUN chmod +x /app/lib/pr-resolver.sh /app/lib/linear.sh

# Git config
RUN git config --global user.name "PR Resolver Bot" \
    && git config --global user.email "pr-resolver@ruh-ai.com"

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

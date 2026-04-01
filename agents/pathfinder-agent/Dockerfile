FROM node:20-slim

# Install git, openssh (for private repos), and openclaw
RUN apt-get update && apt-get install -y \
    git \
    openssh-client \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install OpenClaw CLI globally
RUN npm i -g openclaw@latest

# Disable Node output buffering
ENV NODE_NO_WARNINGS=1

WORKDIR /app

# Copy the full agent workspace
COPY . /app/

# Create directories
RUN mkdir -p /app/memory /root/.ssh /root/.openclaw

# Git config
RUN git config --global user.name "Pathfinder Bot" \
    && git config --global user.email "pathfinder@ruh-ai.com"

# Pathfinder runs as an OpenClaw heartbeat agent
# The entrypoint starts openclaw with this workspace
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

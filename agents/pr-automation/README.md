# PR Automation

A collection of tools for automating PR workflows with Jira integration.

## Skills

### [github-jira-automation](./github-jira-automation/)

Automates release workflows by syncing Jira tickets to GitHub PRs:
- Query Jira for tickets in target status
- Scan repos for matching commits
- Cherry-pick onto release branches
- Auto-resolve conflicts with Claude CLI
- Create/update PRs with detailed summaries

### [pr-review](./pr-review/)

OpenClaw skill for reviewing release PRs targeting `qa` or `main` branches.

## License

MIT

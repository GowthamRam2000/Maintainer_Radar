---
emoji: 🧭
name: AGENTS Maintenance
description: Keep AGENTS.md accurate by reviewing merged pull requests and recent source changes each week.
on:
  schedule: weekly
  workflow_dispatch:
permissions:
  contents: read
  pull-requests: read
strict: true
network:
  allowed:
    - defaults
    - github
    - github-actions
tools:
  github:
    mode: gh-proxy
    toolsets: [default]
  cache-memory: true
safe-outputs:
  create-pull-request:
    title-prefix: "[agents] "
    branch-prefix: "agents-maintenance/"
    draft: true
    if-no-changes: "warn"
    allowed-files:
      - AGENTS.md
---

# AGENTS.md Maintainer

## Task

Use the weekly schedule to keep `AGENTS.md` current.

- Review merged pull requests and updated source files since the last run.
- Use cache-memory to remember the last processed watermark and avoid repeating work.
- Compare current repository conventions, commands, and paths against `AGENTS.md`.
- Update only `AGENTS.md` when it is out of date.
- Create a pull request with the configured safe output when a change is needed.
- If no update is needed, call `noop` with a brief explanation.

## Safe Outputs

- Use `create-pull-request` only for `AGENTS.md`.
- Keep the edit narrowly scoped to repository instructions.
- Use `noop` when the file is already accurate.

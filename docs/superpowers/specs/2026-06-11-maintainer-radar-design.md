# Maintainer Radar Design

## Summary

Maintainer Radar is an open-source Python CLI, GitHub Action, and OpenClaw
companion skill that turns a repository's open issues and pull requests into a
prioritized maintenance digest. It helps maintainers decide what needs
attention now without replacing their judgment or requiring a hosted service.

The project works without an AI provider. Its deterministic scoring and
Markdown report are the core product. An optional OpenAI integration adds a
short executive summary and suggested next actions while retaining the
deterministic report as the source of truth.

## Target Users

The primary user is a maintainer of a public GitHub repository who has a growing
queue of issues and pull requests but no dedicated project-management staff.
The initial release is optimized for repositories with one to several hundred
open items.

## Goals

- Produce a useful maintenance digest from GitHub repository data.
- Surface stale issues, blocked pull requests, review bottlenecks, failing
  checks, and likely release candidates.
- Run locally as a CLI and on a schedule through GitHub Actions.
- Let OpenClaw users request and interpret the same digest conversationally.
- Update one stable GitHub issue instead of creating notification noise.
- Work without paid infrastructure or an OpenAI API key.
- Support optional OpenAI summarization with an explicit, bounded prompt.
- Be easy to adopt through a documented example workflow.

## Non-Goals

- Replacing a project-management system.
- Automatically closing issues, merging pull requests, or changing labels.
- Making security claims or scanning source code for vulnerabilities.
- Supporting GitLab, Bitbucket, or self-hosted GitHub in the initial release.
- Persisting repository data outside GitHub Actions artifacts or the dashboard
  issue.

## User Experience

### Local CLI

The maintainer runs:

```bash
maintainer-radar scan --repo owner/repository
```

The command reads `GITHUB_TOKEN`, fetches open issues and pull requests,
calculates priorities, and writes a Markdown report to standard output. The
report can also be saved with `--output report.md`.

For deterministic demos and tests, the command accepts:

```bash
maintainer-radar scan --fixture examples/demo-repository.json
```

### GitHub Action

A repository adds a scheduled workflow that invokes the action with the
built-in `GITHUB_TOKEN`. The action generates the same report and creates or
updates an issue identified by a stable marker:

```html
<!-- maintainer-radar-dashboard -->
```

The action can run in report-only mode, where it writes the Markdown report to
an output path without changing GitHub.

### Optional AI Summary

When `OPENAI_API_KEY` is present and AI summarization is enabled, Maintainer
Radar sends only the normalized maintenance findings, not source code, to the
OpenAI Responses API. The returned summary appears in a clearly labeled
"AI-assisted summary" section. If the API request fails, the command logs a
warning and publishes the deterministic report.

### OpenClaw Skill

The repository includes an installable `maintainer-radar` skill under
`integrations/openclaw/maintainer-radar/`. The skill is gated on the
`maintainer-radar` executable and teaches OpenClaw to:

- ask for or infer the repository slug
- run the CLI without exposing credentials in command arguments
- explain the deterministic priority reasons before offering recommendations
- distinguish report generation from the write-capable publish operation
- require explicit user intent before publishing or updating a GitHub issue

The skill uses the documented OpenClaw `SKILL.md` format and is structured for
later publication to ClawHub. It is an integration layer, not a second
implementation of scoring or GitHub access.

## Architecture

The package uses focused modules with typed interfaces:

- `models.py` defines normalized issues, pull requests, checks, and findings.
- `github.py` fetches paginated GitHub REST API data and normalizes responses.
- `scoring.py` applies documented rules and returns ranked findings.
- `render.py` creates stable, human-readable Markdown.
- `ai.py` optionally summarizes normalized findings through the OpenAI API.
- `publish.py` finds and creates or updates the dashboard issue.
- `cli.py` handles configuration, orchestration, output, and exit codes.

The GitHub Action is a composite action that installs the Python package and
invokes the CLI. This keeps all behavior available locally and avoids
maintaining a separate JavaScript runtime.

The OpenClaw skill invokes that same CLI through the existing `exec` tool. Its
frontmatter declares a binary requirement so OpenClaw only activates it when
Maintainer Radar is installed.

## Data Model

Each normalized work item includes:

- repository
- number
- title
- URL
- author
- labels
- creation and update timestamps
- assignees
- kind (`issue` or `pull_request`)

Pull requests additionally include draft state, requested reviewers, review
decision, mergeability, latest check conclusion, and milestone.

A finding includes:

- category
- priority score
- concise reason
- recommended action
- normalized work item

## Priority Rules

Scores are deterministic and additive:

- `+40`: pull request has failing checks
- `+30`: pull request is blocked or changes are requested
- `+25`: pull request has waited at least seven days for review
- `+20`: non-draft pull request is approved and checks pass
- `+15`: issue or pull request has had no activity for thirty days
- `+10`: item is unassigned
- `+10`: item has a `security`, `regression`, or `release-blocker` label
- `-30`: pull request is a draft

Scores never imply that an item is safe to merge or close. The report explains
every applied rule. Ties are ordered by oldest update time and then item number.
Thresholds are configurable through CLI options and Action inputs.

## Report Structure

The Markdown dashboard contains:

1. Repository and generation timestamp
2. Queue-health counts
3. Optional AI-assisted summary
4. "Act now" findings
5. "Review next" findings
6. "Ready to land" pull requests
7. Stale and unassigned items
8. Scoring explanation and configuration

Every item links to GitHub and includes its score, reasons, and a suggested
human action. Empty sections say that no matching items were found.

## Configuration

The CLI and Action expose:

- repository slug
- GitHub token
- stale-day threshold
- review-wait threshold
- maximum items per section
- output path
- whether to publish a dashboard issue
- dashboard issue title
- whether to enable AI summarization
- OpenAI model, defaulting to a documented low-cost model

Secrets are accepted only through environment variables. Tokens and API keys
must never appear in logs, reports, prompts, fixtures, or exception messages.

## Error Handling

- Missing or malformed repository names exit with code `2`.
- Authentication, rate-limit, and GitHub API failures exit with code `1` and a
  concise remediation message.
- Invalid fixture data exits with code `2` and identifies the invalid field.
- Dashboard publication failures do not claim success and exit with code `1`.
- OpenAI failures are non-fatal and fall back to deterministic output.
- Partial GitHub pagination failures fail the scan rather than publish an
  incomplete dashboard.

## Security and Privacy

- Default GitHub workflow permissions are read-only, with `issues: write`
  required only when publishing.
- The optional AI request contains normalized metadata and findings only.
- The project documents prompt-injection risk from untrusted issue titles and
  instructs the model to treat repository content strictly as data.
- Markdown content is rendered without raw HTML from GitHub fields.
- Dependency versions are bounded and Dependabot is enabled.
- A `SECURITY.md` file documents responsible vulnerability reporting.

## Testing

Tests use realistic JSON fixtures and mocked HTTP transports, never live
credentials.

- Unit tests cover normalization, every scoring rule, tie-breaking, rendering,
  and validation.
- Client tests cover pagination, API errors, and rate-limit messages.
- Publication tests cover finding, creating, and updating the stable dashboard
  issue.
- AI tests verify bounded payloads and deterministic fallback behavior.
- CLI tests cover fixture mode, output files, exit codes, and report-only mode.
- A structure test validates the OpenClaw skill frontmatter and required safety
  instructions.
- A smoke test runs the packaged CLI against the demo fixture.

CI runs tests, Ruff linting, and package builds on supported Python versions.

## Repository Documentation

The public repository includes:

- a README with the problem, example output, quick start, Action setup,
  permissions, scoring rules, privacy notes, and roadmap
- an MIT license
- contribution and security guides
- issue and pull-request templates
- a demo fixture and generated example report
- an OpenClaw installation and conversational usage guide
- a changelog beginning with version `0.1.0`

## Release Scope

Version `0.1.0` is complete when:

- the CLI generates a deterministic report from fixtures and live GitHub data
- the Action can publish or update one dashboard issue
- the OpenClaw skill can invoke the installed CLI using documented commands
- optional OpenAI summarization fails safely
- tests, linting, and package build pass
- documentation enables installation and adoption without reading source code

## Program Alignment

Maintainer Radar directly targets triage, review, release, and maintainer
automation workflows named by the Codex for Open Source program. The
application will state accurately that the repository is new, has no established
usage metrics, and is being submitted because it is purpose-built for an
important maintainer workflow. It will not claim existing adoption, ecosystem
importance, or maintainer status that cannot be verified.

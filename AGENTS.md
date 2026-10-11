# AGENTS.md — Webtor isolated validation

This repository is a focused, ephemeral Docker/network smoke-test fixture, **not** the TMX TV product UI. Start with README.md.

- Preserve isolated runs on standard free GitHub-hosted runners, with no production secrets, real customer data or permanent hosting.
- Keep any test, container and CI changes tightly scoped; never use this repository to bypass platform limitations or usage quotas.
- Before changing execution logic, inspect CI workflows, verify assumptions and run the relevant local/static checks.
- Report failures and untested paths honestly; never treat passing synthetic tests as proof of production performance.
- Optional UI/design resource catalog: [DESIGN-TOOLBOX.md](DESIGN-TOOLBOX.md), **only relevant when a UI is explicitly requested**. It is not a package list to install.
- Third-party tool and MCP installations, PC control, and privileged shell execution require separate informed approval.

## Focused agent skill and automated static preflight

- Read [docs/GITHUB-10-AGENT-TOOLBOX.md](docs/GITHUB-10-AGENT-TOOLBOX.md) as optional research and [.agents/skills/smoke-safety/SKILL.md](.agents/skills/smoke-safety/SKILL.md) for scoped changes.
- Before a Docker build or any CI change, run `python3 -m unittest discover -s ci -p 'test_*.py'` and `python3 ci/preflight.py`. Both are dependency-free. The manual GitHub Action also runs these steps first.
- These static checks verify declared configuration only; they do not prove a container starts or that authenticated media playback succeeds. Report Docker smoke results separately.

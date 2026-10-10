# AGENTS.md — Webtor isolated validation

This repository is a focused, ephemeral Docker/network smoke-test fixture, **not** the TMX TV product UI. Start with README.md.

- Preserve isolated runs on standard free GitHub-hosted runners, with no production secrets, real customer data or permanent hosting.
- Keep any test, container and CI changes tightly scoped; never use this repository to bypass platform limitations or usage quotas.
- Before changing execution logic, inspect CI workflows, verify assumptions and run the relevant local/static checks.
- Report failures and untested paths honestly; never treat passing synthetic tests as proof of production performance.
- Optional UI/design resource catalog: [DESIGN-TOOLBOX.md](DESIGN-TOOLBOX.md), **only relevant when a UI is explicitly requested**. It is not a package list to install.
- Third-party tool and MCP installations, PC control, and privileged shell execution require separate informed approval.

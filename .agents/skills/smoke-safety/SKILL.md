---
name: smoke-safety
description: Review changes to TMX's isolated, no-cost Docker/Webtor smoke-test harness and prove its security guardrails remain intact.
---

# TMX — smoke test isolé et vérifiable

This repository is only a synthetic test environment, **not** the live product, content catalog or streaming infrastructure.

1. Read `README.md`, `AGENTS.md`, `Dockerfile`, `.github/workflows/webtor-smoke.yml`, `ci/startup.py` and `docs/GITHUB-10-AGENT-TOOLBOX.md`.
2. Make tests fail for precise, reproducible reasons. Separate **preflight configuration**, real boot/health, authorization, and timed synthetic media decoding. Never claim production reliability from synthetic passes.
3. Preserve pinned base-image digests, pinned GitHub Actions, minimum permissions, disabled Docker-build networking, locally bound ports and temporary per-run secrets.
4. Never publish credentials, customer data, raw auth logs, videos, caches or artifacts. Do not add privileged runners or paid services.
5. Run `python3 -m unittest discover -s ci -p 'test_*.py'` and `python3 ci/preflight.py` before changing CI. If Docker is available, run only the approved isolated smoke workflow; otherwise clearly report it as untested.
6. For errors, record redacted category, reproduction conditions and failure location. Do not ingest session traces into third-party agent memory automatically.
7. Avoid unrelated agent frameworks, voice cloning, reverse engineering, surveillance tools and UI packages. No unreviewed install scripts.

"""Static safety checks for the isolated TMX Webtor smoke-test repository.

No third-party dependencies; run before Docker builds. This verifies repository
configuration, not runtime security or successful playback.
"""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def check_repository(root=ROOT):
    findings = []
    try:
        docker = (root / "Dockerfile").read_text(encoding="utf-8")
        workflow = (root / ".github/workflows/webtor-smoke.yml").read_text(encoding="utf-8")
        startup = (root / "ci/startup.py").read_text(encoding="utf-8")
        ignored = (root / ".dockerignore").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return ["missing or unreadable required file: " + type(exc).__name__]

    def require(condition, message):
        if not condition:
            findings.append(message)

    from_lines = re.findall(r"(?im)^\s*FROM\s+(\S+)", docker)
    require(bool(from_lines) and all(re.search(r"@sha256:[0-9a-f]{64}$", image) for image in from_lines),
            "Docker base images must be SHA-256 pinned")
    require(bool(re.search(r"actions/checkout@[0-9a-f]{40}\b", workflow)),
            "checkout action must use a full commit SHA")
    require("persist-credentials: false" in workflow,
            "checkout must not persist credentials")
    require(bool(re.search(r"(?m)^permissions:\s*\n\s*contents: read\s*$", workflow)),
            "workflow must use read-only content permissions")
    require("docker build --network=none" in workflow,
            "Docker build network must remain disabled")
    require("workflow_dispatch:" in workflow and not re.search(r"(?m)^\s*(push|schedule|pull_request):", workflow),
            "smoke test must remain manually triggered")
    require(bool(re.search(r"timeout-minutes:\s*20\b", workflow)),
            "workflow job must keep the 20 minute timeout")
    require("python3 ci/startup.py" in workflow,
            "startup probe must be invoked")
    require("127.0.0.1:18080:8080" in startup,
            "test container port must remain loopback-only")
    require("secrets.token_hex" in startup,
            "test secrets must be generated per run")
    require("configured_test_secrets_absent_from_logs" in startup,
            "secret leak check must remain enabled")
    ignore_lines = {line.strip() for line in ignored.splitlines() if line.strip() and not line.startswith("#")}
    require("*" in ignore_lines and {"!Dockerfile", "!entrypoint.sh", "!redact-logs.sh"}.issubset(ignore_lines),
            "Docker build context allowlist must remain strict")
    return findings


if __name__ == "__main__":
    issues = check_repository()
    print(json.dumps({"check": "static_security_preflight", "passed": not issues, "issues": issues}))
    sys.exit(1 if issues else 0)

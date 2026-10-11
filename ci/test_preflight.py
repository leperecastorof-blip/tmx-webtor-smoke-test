"""No-network unit tests for TMX preflight rules."""
import tempfile
from pathlib import Path
import unittest
from preflight import check_repository

PIN = "6d6062a4c941ccd9649c38927c791390539f6f287571195370e8e1c4ad1cbda2"
CHECKOUT = "11bd71901bbe5b1630ceea73d27597364c9af683"


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write("Dockerfile", f"FROM ghcr.io/webtor-io/self-hosted@sha256:{PIN}\n")
        self.write(".github/workflows/webtor-smoke.yml", f"""on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  smoke:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@{CHECKOUT}
        with:
          persist-credentials: false
      - run: docker build --network=none --tag tmx-webtor:test .
      - run: python3 ci/startup.py
""")
        self.write("ci/startup.py", "secrets.token_hex(24)\n127.0.0.1:18080:8080\nconfigured_test_secrets_absent_from_logs\n")
        self.write(".dockerignore", "*\n!Dockerfile\n!entrypoint.sh\n!redact-logs.sh\n")

    def write(self, name, body):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(body, encoding="utf-8")

    def test_valid_fixture(self):
        self.assertEqual(check_repository(self.root), [])

    def test_unpinned_image_detected(self):
        self.write("Dockerfile", "FROM ghcr.io/webtor-io/self-hosted:latest\n")
        self.assertTrue(any("SHA-256" in s for s in check_repository(self.root)))

    def test_network_enabled_detected(self):
        path = self.root / ".github/workflows/webtor-smoke.yml"
        self.write(".github/workflows/webtor-smoke.yml", path.read_text().replace("--network=none", "--network=host"))
        self.assertTrue(any("network" in s.lower() for s in check_repository(self.root)))

    def test_persisted_checkout_credentials_detected(self):
        path = self.root / ".github/workflows/webtor-smoke.yml"
        self.write(".github/workflows/webtor-smoke.yml", path.read_text().replace("persist-credentials: false", "persist-credentials: true"))
        self.assertTrue(any("credentials" in s for s in check_repository(self.root)))

    def test_missing_files_fail_closed(self):
        (self.root / "Dockerfile").unlink()
        self.assertNotEqual(check_repository(self.root), [])


if __name__ == "__main__":
    unittest.main()

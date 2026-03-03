#!/usr/bin/env python3
"""
AgentCost — Release Verification Script

Verifies all install paths work correctly before publishing.

Usage:
    python scripts/verify_release.py
    python scripts/verify_release.py --full   # includes Docker test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def check(name: str, fn):
    """Run a check and print result."""
    try:
        result = fn()
        print(f"  ✅ {name}")
        return True
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return False


def verify_python_package():
    """Verify the Python package is importable and functional."""
    print("\n📦 Python Package")

    passed = 0
    total = 0

    def _run_import(code):
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, cwd=os.getcwd())
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip().split("\n")[-1])

    def _import_core():
        _run_import("from agentcost.sdk import trace; from agentcost.sdk.trace import TraceEvent")
    total += 1; passed += check("Core SDK imports", _import_core)

    def _import_forecast():
        _run_import("from agentcost.forecast import CostForecaster")
    total += 1; passed += check("Forecasting imports", _import_forecast)

    def _import_optimizer():
        _run_import("from agentcost.optimizer import CostOptimizer")
    total += 1; passed += check("Optimizer imports", _import_optimizer)

    def _import_analytics():
        _run_import("from agentcost.analytics import UsageAnalytics")
    total += 1; passed += check("Analytics imports", _import_analytics)

    def _import_estimator():
        _run_import("from agentcost.estimator import CostEstimator")
    total += 1; passed += check("Estimator imports", _import_estimator)

    def _import_edition():
        _run_import("from agentcost.edition import get_edition, edition_info; i = edition_info(); assert i['core']['tracing'] is True")
    total += 1; passed += check("Edition detection", _import_edition)

    def _check_version():
        import tomllib
        with open("pyproject.toml", "rb") as f:
            d = tomllib.load(f)
        assert d["project"]["version"] == "1.0.0"
        assert d["project"]["license"] == "MIT"
    total += 1; passed += check("Version 1.0.0 + MIT license", _check_version)

    return passed, total


def verify_cli():
    """Verify CLI commands work."""
    print("\n🖥️  CLI")

    passed = 0
    total = 0

    def _cli_info():
        r = subprocess.run([sys.executable, "-m", "agentcost", "info"],
                           capture_output=True, text=True, env={**os.environ, "AGENTCOST_EDITION": "community"})
        assert r.returncode == 0
        assert "AgentCost v1.0.0" in r.stdout
    total += 1; passed += check("agentcost info", _cli_info)

    def _cli_help():
        r = subprocess.run([sys.executable, "-m", "agentcost", "--help"], capture_output=True, text=True)
        assert r.returncode == 0
        assert "benchmark" in r.stdout
    total += 1; passed += check("agentcost --help", _cli_help)

    return passed, total


def verify_server():
    """Verify server starts and responds."""
    print("\n🌐 Server")

    passed = 0
    total = 0

    port = 19876
    env = {**os.environ, "AGENTCOST_EDITION": "community", "AGENTCOST_PORT": str(port)}

    # Start server in background process
    proc = subprocess.Popen(
        [sys.executable, "-m", "agentcost.api.server"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    import time
    import urllib.request
    time.sleep(4)  # wait for startup

    def _health():
        resp = urllib.request.urlopen(f"http://localhost:{port}/api/health", timeout=5)
        data = json.loads(resp.read())
        assert data["status"] == "ok"
        assert data["edition"] == "community"
    total += 1; passed += check("GET /api/health", _health)

    def _projects():
        resp = urllib.request.urlopen(f"http://localhost:{port}/api/projects", timeout=5)
        assert resp.getcode() == 200
    total += 1; passed += check("GET /api/projects", _projects)

    def _seed():
        req = urllib.request.Request(
            f"http://localhost:{port}/api/seed",
            data=json.dumps({"days": 1, "clear": True}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        assert data["status"] == "ok"
        assert data["seeded"] > 0
    total += 1; passed += check("POST /api/seed", _seed)

    def _dashboard():
        resp = urllib.request.urlopen(f"http://localhost:{port}/", timeout=5)
        html = resp.read().decode()
        assert "AgentCost" in html
    total += 1; passed += check("GET / (dashboard HTML)", _dashboard)

    # Cleanup
    proc.terminate()
    proc.wait(timeout=5)

    return passed, total


def verify_docs():
    """Verify docs structure."""
    print("\n📚 Documentation")

    passed = 0
    total = 0

    def _mkdocs_yml():
        assert os.path.exists("mkdocs.yml")
    total += 1; passed += check("mkdocs.yml exists", _mkdocs_yml)

    def _doc_pages():
        import glob
        pages = glob.glob("docs/**/*.md", recursive=True)
        assert len(pages) >= 14, f"Only {len(pages)} pages found"
    total += 1; passed += check("Documentation pages (>=14)", _doc_pages)

    return passed, total


def verify_npm():
    """Verify npm package.json."""
    print("\n📦 npm Package")

    passed = 0
    total = 0

    def _package_json():
        with open("sdks/typescript/package.json") as f:
            pkg = json.load(f)
        assert pkg["version"] == "1.0.0"
        assert pkg["license"] == "MIT"
        assert pkg["name"] == "@agentcostin/sdk"
    total += 1; passed += check("package.json v1.0.0 + MIT", _package_json)

    return passed, total


def verify_docker():
    """Verify Docker build."""
    print("\n🐳 Docker")

    passed = 0
    total = 0

    def _dockerfile():
        assert os.path.exists("docker/Dockerfile.dashboard")
    total += 1; passed += check("Dockerfile.dashboard exists", _dockerfile)

    def _compose_dev():
        assert os.path.exists("docker-compose.dev.yml")
    total += 1; passed += check("docker-compose.dev.yml exists", _compose_dev)

    return passed, total


def main():
    parser = argparse.ArgumentParser(description="Verify AgentCost release readiness")
    parser.add_argument("--full", action="store_true", help="Run all checks including server")
    args = parser.parse_args()

    print("🧮 AgentCost Release Verification")
    print("=" * 50)

    total_passed = 0
    total_checks = 0

    for verify_fn in [verify_python_package, verify_cli, verify_docs, verify_npm, verify_docker]:
        p, t = verify_fn()
        total_passed += p
        total_checks += t

    if args.full:
        p, t = verify_server()
        total_passed += p
        total_checks += t

    print(f"\n{'=' * 50}")
    print(f"  {'✅' if total_passed == total_checks else '⚠️'}  {total_passed}/{total_checks} checks passed")

    if total_passed < total_checks:
        print(f"  {total_checks - total_passed} checks failed — fix before publishing")
        sys.exit(1)
    else:
        print("  Ready to publish! 🚀")


if __name__ == "__main__":
    main()

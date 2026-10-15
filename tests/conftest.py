# SPDX-License-Identifier: Apache-2.0
"""Isolation des tests : aucun catalogue personnel ni index rafraîchi du poste ne doit compter."""

from __future__ import annotations

import os
import tempfile

import pytest

_HOME = tempfile.mkdtemp(prefix="devops-builder-tests-")
os.environ["DEVOPS_BUILDER_HOME"] = _HOME

# CI complète : chaque outil est installé, un test sauté signale un outil perdu en route
STRICT = os.environ.get("DEVOPS_BUILDER_TESTS_COMPLETS") == "1"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if STRICT and report.skipped and not hasattr(report, "wasxfail"):
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        report.outcome = "failed"
        report.longrepr = f"test sauté alors que tous les outils doivent être présents : {reason}"


def pytest_runtest_logreport(report):
    """Sous GitHub Actions, chaque échec devient une annotation : lisible sans ouvrir le journal du job."""
    if os.environ.get("GITHUB_ACTIONS") != "true" or not report.failed:
        return
    text = str(report.longrepr)[-1500:]
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"\n::error title={report.nodeid.replace(':', '∶').replace(',', '‚')}::{text}")

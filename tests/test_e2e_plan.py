# SPDX-License-Identifier: Apache-2.0
"""Lot 0.17 : les scénarios de bout en bout restent valides entre deux passages sur GitHub Actions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("e2e_run", ROOT / "tools" / "e2e" / "run.py")
e2e = importlib.util.module_from_spec(spec)
sys.modules["e2e_run"] = e2e
spec.loader.exec_module(e2e)


@pytest.mark.parametrize("name", list(e2e.SCENARIOS))
def test_scenario_genere_et_planifie(name, capsys, tmp_path):
    assert e2e.main([name, "--plan", "--keep", str(tmp_path)]) == 0
    plan = capsys.readouterr().out
    assert "(toujours)" in plan                       # nettoyage prévu même après un échec
    out = tmp_path / "projet"
    assert (out / "devops-builder.yaml").exists()
    if name.startswith("kind-"):
        assert "kind delete cluster" in plan              # le cluster jetable est toujours supprimé
        assert "test-kind.sh" in plan or "platform/install.sh" in plan
    else:
        assert {"secrets.sh", "docker-compose.yml"} <= {p.name for p in (out / "deploy").iterdir()}
        assert "docker compose" in plan and "down -v" in plan       # volumes supprimés après le test
        if name in ("compose-postgresql", "compose-zabbix"):     # scénarios qui vérifient la sauvegarde
            assert "db-backup.sh" in plan and "db-restore.sh" in plan
        if name == "compose-sops":
            assert "secrets-seed.sh" in plan and "ci-secrets.sh" in plan and "age-keygen" in plan


def test_le_workflow_lance_chaque_scenario():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "e2e.yml").read_text(encoding="utf-8"))
    assert wf["jobs"]["scenario"]["strategy"]["matrix"]["scenario"] == list(e2e.SCENARIOS)


def test_application_de_demonstration_sans_base(monkeypatch):
    spec = importlib.util.spec_from_file_location("e2e_app", ROOT / "tools" / "e2e" / "app" / "app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    for var in ("DATABASE_URL", "REDIS_URL", "OIDC_ISSUER_URL"):
        monkeypatch.delenv(var, raising=False)
    assert app.databases() == (False, {})
    assert app.oidc() == (False, {"OIDC_ISSUER_URL": "absente"})


def test_scenario_inconnu_code_2():
    assert e2e.main(["inexistant"]) == 2


def test_blocs_du_mode_d_emploi_zabbix(tmp_path):
    """Le scénario compose-zabbix joue les deux blocs de la section Zabbix : ils doivent exister."""
    assert e2e.main(["compose-zabbix", "--plan", "--keep", str(tmp_path)]) == 0
    blocks = e2e.runbook_blocks(tmp_path / "projet", "Zabbix")
    assert len(blocks) == 2 and "user.update" in blocks[0] and "host.get" in blocks[1]

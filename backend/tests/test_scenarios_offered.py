"""Study picker shows only the 5 offered scenarios (S1–S5), ordered, with researcher-only
fields stripped (groundTruthHiddenIntentions, hiddenIntentionMechanism)."""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_meta_scenarios_returns_only_offered_five(client):
    scs = client.get("/api/meta/scenarios").json()["scenarios"]
    assert len(scs) == 5, [s["id"] for s in scs]
    assert {s["id"] for s in scs} == {
        "first_time_exploration", "taste_identity", "specific_context",
        "gift_for_other", "high_involvement",
    }
    # ordered by studyOrder S1..S5
    assert [s.get("studyOrder") for s in scs] == [1, 2, 3, 4, 5]
    # researcher-only fields not exposed to participants
    for s in scs:
        assert "groundTruthHiddenIntentions" not in s
        assert "hiddenIntentionMechanism" not in s


def test_get_scenario_still_resolves_non_offered(client):
    # sim/eval path (get_scenario by id) must keep ALL scenarios resolvable
    from app.products.seed_loader import get_scenario
    assert get_scenario("budget_value") is not None  # non-offered but still present in seed

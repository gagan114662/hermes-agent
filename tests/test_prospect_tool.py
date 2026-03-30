"""Tests for prospect tracker tool."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def tmp_prospects(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    import importlib
    import tools.prospect_tool as mod
    importlib.reload(mod)
    yield mod


def test_prospect_add(tmp_prospects):
    result = tmp_prospects.prospect_add_fn(
        name="Bob's Plumbing",
        source="reddit",
        source_url="https://reddit.com/r/smallbusiness/comments/abc",
        pain_point="overwhelmed, missing calls, no time",
        contact_hint="u/bobs_plumbing",
        score=8,
    )
    assert "added" in result.lower() or "bob" in result.lower()
    data = json.loads(Path(tmp_prospects._prospects_path()).read_text())
    assert len(data["prospects"]) == 1
    pid = list(data["prospects"].keys())[0]
    assert data["prospects"][pid]["score"] == 8
    assert data["prospects"][pid]["status"] == "new"


def test_prospect_list_filters_by_status(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="A", source="reddit", pain_point="x")
    tmp_prospects.prospect_add_fn(name="B", source="twitter", pain_point="y")
    result = tmp_prospects.prospect_list_fn(status="new")
    assert "A" in result and "B" in result


def test_prospect_update_status(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="C Corp", source="indeed", pain_point="z")
    data = json.loads(Path(tmp_prospects._prospects_path()).read_text())
    pid = list(data["prospects"].keys())[0]
    result = tmp_prospects.prospect_update_fn(prospect_id=pid, status="contacted", notes="Sent DM")
    assert "contacted" in result.lower() or "updated" in result.lower()
    data2 = json.loads(Path(tmp_prospects._prospects_path()).read_text())
    assert data2["prospects"][pid]["status"] == "contacted"
    assert data2["prospects"][pid]["notes"] == "Sent DM"


def test_prospect_update_rejects_invalid_status(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="D", source="maps", pain_point="x")
    data = json.loads(Path(tmp_prospects._prospects_path()).read_text())
    pid = list(data["prospects"].keys())[0]
    result = tmp_prospects.prospect_update_fn(prospect_id=pid, status="nonsense")
    assert "invalid" in result.lower() or "error" in result.lower()


def test_prospect_digest(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="D Inc", source="maps", pain_point="missed calls", score=9)
    tmp_prospects.prospect_add_fn(name="E LLC", source="indeed", pain_point="hiring sales rep", score=7)
    result = tmp_prospects.prospect_digest_fn()
    assert "D Inc" in result and "E LLC" in result
    assert "APPROVE" in result
    # Sorted by score — D Inc (9) should appear before E LLC (7)
    assert result.index("D Inc") < result.index("E LLC")


def test_prospect_list_all_statuses(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="F", source="reddit", pain_point="x")
    data = json.loads(Path(tmp_prospects._prospects_path()).read_text())
    pid = list(data["prospects"].keys())[0]
    tmp_prospects.prospect_update_fn(prospect_id=pid, status="contacted")
    result = tmp_prospects.prospect_list_fn(status="")
    assert "F" in result


def test_prospect_list_empty(tmp_prospects):
    result = tmp_prospects.prospect_list_fn(status="new")
    assert "no prospects" in result.lower()


def test_prospect_update_no_op_returns_error(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="G", source="reddit", pain_point="x")
    data = json.loads(Path(tmp_prospects._prospects_path()).read_text())
    pid = list(data["prospects"].keys())[0]
    result = tmp_prospects.prospect_update_fn(prospect_id=pid)
    assert "error" in result.lower()


def test_prospect_add_rejects_invalid_score(tmp_prospects):
    result = tmp_prospects.prospect_add_fn(name="H", source="reddit", pain_point="x", score=99)
    assert "error" in result.lower()
    p = Path(tmp_prospects._prospects_path())
    data = json.loads(p.read_text()) if p.exists() else {"prospects": {}}
    assert len(data["prospects"]) == 0

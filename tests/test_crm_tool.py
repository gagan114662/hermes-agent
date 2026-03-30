"""Tests for CRM tool — contact and deal management."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def tmp_crm(tmp_path, monkeypatch):
    """Redirect CRM storage to a temp directory."""
    crm_dir = tmp_path / ".hermes"
    crm_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    import importlib.util
    import sys
    import types

    root = Path(__file__).resolve().parent.parent

    # Ensure the tools package stub exists so importing tools.registry doesn't
    # trigger tools/__init__.py (which has heavy optional deps like firecrawl).
    if "tools" not in sys.modules:
        pkg = types.ModuleType("tools")
        pkg.__path__ = [str(root / "tools")]
        pkg.__package__ = "tools"
        sys.modules["tools"] = pkg

    # Load tools.registry directly (no heavy deps)
    if "tools.registry" not in sys.modules:
        reg_file = root / "tools" / "registry.py"
        reg_spec = importlib.util.spec_from_file_location("tools.registry", reg_file)
        reg_mod = importlib.util.module_from_spec(reg_spec)
        reg_spec.loader.exec_module(reg_mod)
        sys.modules["tools.registry"] = reg_mod

    # Load crm_tool directly, bypassing tools/__init__.py
    crm_file = root / "tools" / "crm_tool.py"
    crm_spec = importlib.util.spec_from_file_location("tools.crm_tool", crm_file)
    mod = importlib.util.module_from_spec(crm_spec)
    crm_spec.loader.exec_module(mod)
    sys.modules["tools.crm_tool"] = mod
    yield mod


def test_crm_save_new_contact(tmp_crm):
    result = tmp_crm.crm_save_fn(
        name="Alice Smith",
        phone="+14155550100",
        email="alice@example.com",
        notes="Met at trade show",
    )
    assert "saved" in result.lower() or "alice" in result.lower()
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert "+14155550100" in data["contacts"]


def test_crm_save_updates_existing(tmp_crm):
    tmp_crm.crm_save_fn(name="Bob", phone="+14155550101")
    tmp_crm.crm_save_fn(name="Bob Updated", phone="+14155550101", notes="Follow-up done")
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert data["contacts"]["+14155550101"]["name"] == "Bob Updated"


def test_crm_log_interaction(tmp_crm):
    tmp_crm.crm_save_fn(name="Carol", phone="+14155550102")
    result = tmp_crm.crm_log_fn(
        phone="+14155550102",
        channel="call",
        summary="Interested in demo, call back Thursday",
    )
    assert "logged" in result.lower() or "carol" in result.lower()
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert len(data["contacts"]["+14155550102"]["interactions"]) == 1


def test_crm_find_by_name(tmp_crm):
    tmp_crm.crm_save_fn(name="Dave Johnson", phone="+14155550103")
    result = tmp_crm.crm_find_fn(query="Dave")
    assert "dave" in result.lower()


def test_crm_deal_add(tmp_crm):
    tmp_crm.crm_save_fn(name="Eve", phone="+14155550104")
    result = tmp_crm.crm_deal_fn(
        phone="+14155550104",
        title="AI Employee subscription",
        value=299,
        status="open",
    )
    assert "deal" in result.lower() or "eve" in result.lower()
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert len(data["contacts"]["+14155550104"]["deals"]) == 1


def test_crm_log_works_for_email_keyed_contact(tmp_crm):
    """crm_log must work for contacts saved with email only (no phone)."""
    tmp_crm.crm_save_fn(name="Email Only", email="emailonly@example.com")
    result = tmp_crm.crm_log_fn(
        phone="emailonly@example.com",  # using email as the key
        channel="email",
        summary="Sent intro email",
    )
    assert "logged" in result.lower() or "email only" in result.lower()
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert len(data["contacts"]["emailonly@example.com"]["interactions"]) == 1

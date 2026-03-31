"""Tests for the async delegation mailbox."""
import time
import threading
import pytest
from agent.mailbox import Mailbox


def test_reserve_returns_unique_handles():
    m = Mailbox()
    handles = {m.reserve() for _ in range(10)}
    assert len(handles) == 10


def test_poll_returns_none_before_send():
    m = Mailbox()
    h = m.reserve()
    assert m.poll(h) is None


def test_send_then_poll():
    m = Mailbox()
    h = m.reserve()
    m.send(h, {"result": "done"})
    assert m.poll(h) == {"result": "done"}


def test_receive_blocks_until_send():
    m = Mailbox()
    h = m.reserve()
    results = []

    def sender():
        time.sleep(0.05)
        m.send(h, "hello")

    t = threading.Thread(target=sender)
    t.start()
    result = m.receive(h, timeout=2)
    t.join()

    assert result == "hello"


def test_receive_times_out():
    m = Mailbox()
    h = m.reserve()
    result = m.receive(h, timeout=0.05)
    assert result is None


def test_discard_removes_entry():
    m = Mailbox()
    h = m.reserve()
    m.send(h, "done")
    m.discard(h)
    assert m.poll(h) is None


def test_delegate_task_async_returns_handle():
    """delegate_task_async returns a JSON with task_handle_id immediately."""
    import json
    from unittest.mock import patch, MagicMock
    from tools.delegate_tool import delegate_task_async

    with patch("tools.delegate_tool.delegate_task", return_value='{"response": "done"}'):
        result = json.loads(delegate_task_async(goal="test goal"))

    assert "task_handle_id" in result
    assert result["status"] == "running"


def test_check_delegation_pending():
    """check_delegation returns pending for unknown handle."""
    import json
    from tools.delegate_tool import check_delegation
    result = json.loads(check_delegation("nonexistent-handle-xyz"))
    assert result["status"] == "pending"

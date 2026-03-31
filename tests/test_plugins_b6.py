"""Tests for B6: hot reload and new hook events."""
import os
from unittest.mock import MagicMock, patch

from hermes_cli.plugins import PluginManager, LoadedPlugin, PluginManifest, emit_hook, invoke_hook


def test_emit_hook_never_raises():
    """emit_hook swallows all exceptions."""
    with patch("hermes_cli.plugins.invoke_hook", side_effect=RuntimeError("boom")):
        emit_hook("on_tool_error", tool="test", error="boom")  # must not raise


def test_emit_hook_returns_none():
    """emit_hook always returns None."""
    result = emit_hook("on_memory_write", content="test", target="memory")
    assert result is None


def test_hot_reload_triggers_on_mtime_change():
    """Plugin module is reloaded when source file mtime changes."""
    manager = PluginManager()

    mock_module = MagicMock()
    mock_module.__file__ = "/fake/plugin.py"
    mock_module.on_tool_error = MagicMock(return_value=None)

    # Use LoadedPlugin dataclass as PluginManager expects
    manifest = PluginManifest(name="test_plugin", source="user", path="/fake")
    loaded = LoadedPlugin(manifest=manifest, module=mock_module, enabled=True)
    manager._plugins["test_plugin"] = loaded
    manager._plugin_mtimes["test_plugin"] = 1000.0

    with patch("os.path.getmtime", return_value=2000.0), \
         patch("importlib.reload") as mock_reload:
        manager._check_reload()

    mock_reload.assert_called_once_with(mock_module)


def test_hot_reload_skips_unchanged_files():
    """Plugin module is NOT reloaded when mtime has not changed."""
    manager = PluginManager()

    mock_module = MagicMock()
    mock_module.__file__ = "/fake/plugin.py"

    manifest = PluginManifest(name="stable_plugin", source="user", path="/fake")
    loaded = LoadedPlugin(manifest=manifest, module=mock_module, enabled=True)
    manager._plugins["stable_plugin"] = loaded
    manager._plugin_mtimes["stable_plugin"] = 5000.0

    with patch("os.path.getmtime", return_value=5000.0), \
         patch("importlib.reload") as mock_reload:
        manager._check_reload()

    mock_reload.assert_not_called()


def test_hot_reload_skips_module_without_file():
    """Plugin with no __file__ does not crash _check_reload."""
    manager = PluginManager()

    mock_module = MagicMock(spec=[])  # No __file__ attribute
    manifest = PluginManifest(name="no_file_plugin", source="user", path="/fake")
    loaded = LoadedPlugin(manifest=manifest, module=mock_module, enabled=True)
    manager._plugins["no_file_plugin"] = loaded

    # Should not raise
    manager._check_reload()


def test_hot_reload_handles_getmtime_error_gracefully():
    """If getmtime raises (e.g. file deleted), _check_reload continues."""
    manager = PluginManager()

    mock_module = MagicMock()
    mock_module.__file__ = "/fake/deleted_plugin.py"

    manifest = PluginManifest(name="deleted_plugin", source="user", path="/fake")
    loaded = LoadedPlugin(manifest=manifest, module=mock_module, enabled=True)
    manager._plugins["deleted_plugin"] = loaded

    with patch("os.path.getmtime", side_effect=OSError("file not found")):
        manager._check_reload()  # must not raise


def test_check_reload_called_in_invoke_hook():
    """invoke_hook() calls _check_reload() before dispatching to callbacks."""
    manager = PluginManager()

    reload_called = []
    original_check_reload = manager._check_reload

    def spy_check_reload():
        reload_called.append(True)
        original_check_reload()

    manager._check_reload = spy_check_reload
    manager.invoke_hook("on_memory_write", content="test", target="memory")

    assert len(reload_called) == 1, "_check_reload should be called once per invoke_hook call"


def test_on_memory_write_hook_fires():
    """on_memory_write hook is valid and can be invoked."""
    emit_hook("on_memory_write", content="test memory", target="user")


def test_on_delegation_start_hook_fires():
    """on_delegation_start hook is valid and can be invoked."""
    emit_hook("on_delegation_start", goal="research X", toolsets=["web"])


def test_on_delegation_end_hook_fires():
    """on_delegation_end hook is valid and can be invoked."""
    emit_hook("on_delegation_end", goal="research X", success=True)


def test_on_tool_error_hook_fires():
    """on_tool_error hook is valid and can be invoked."""
    emit_hook("on_tool_error", tool="terminal", error="command not found")


def test_on_budget_warning_hook_fires():
    """on_budget_warning hook is valid and can be invoked."""
    emit_hook("on_budget_warning", used=80, budget=100)


def test_on_context_compress_hook_fires():
    """on_context_compress hook is valid and can be invoked."""
    emit_hook("on_context_compress", tokens_before=50000, tokens_after=20000)


def test_on_file_changed_hook_fires():
    """on_file_changed hook is valid and can be invoked."""
    emit_hook("on_file_changed", path="/tmp/test.py")


def test_plugin_callback_receives_kwargs():
    """Registered plugin callbacks receive correct kwargs from emit_hook."""
    manager = PluginManager()
    received = {}

    def my_hook(**kwargs):
        received.update(kwargs)

    manager._hooks["on_memory_write"] = [my_hook]

    with patch("hermes_cli.plugins.get_plugin_manager", return_value=manager):
        invoke_hook("on_memory_write", content="hello", target="memory")

    assert received.get("content") == "hello"
    assert received.get("target") == "memory"

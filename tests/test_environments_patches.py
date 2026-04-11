"""Tests for environments/patches.py — apply_patches no-op compatibility shim."""
from __future__ import annotations

import importlib

import pytest


class TestApplyPatches:
    def setup_method(self):
        # Reset the module state before each test
        import environments.patches as p
        p._patches_applied = False

    def test_apply_patches_runs_without_error(self):
        from environments.patches import apply_patches
        apply_patches()

    def test_apply_patches_sets_flag(self):
        import environments.patches as p
        assert p._patches_applied is False
        p.apply_patches()
        assert p._patches_applied is True

    def test_apply_patches_is_idempotent(self):
        from environments.patches import apply_patches
        apply_patches()
        apply_patches()  # Should not raise or reset state

    def test_apply_patches_stays_true_on_second_call(self):
        import environments.patches as p
        p.apply_patches()
        assert p._patches_applied is True
        p.apply_patches()
        assert p._patches_applied is True

    def test_module_importable(self):
        """environments.patches must be importable at module level."""
        import environments.patches
        assert hasattr(environments.patches, "apply_patches")

    def test_apply_patches_is_callable(self):
        from environments.patches import apply_patches
        assert callable(apply_patches)

"""Tests that the C1 system prompt engineering additions are present and correct."""

import pytest

from agent.prompt_builder import (
    DEFAULT_AGENT_IDENTITY,
    TOOL_USE_GUIDANCE,
    SELF_CORRECTION_GUIDANCE,
    CRM_INTEGRITY_GUIDANCE,
    PROACTIVE_BEHAVIORS_GUIDANCE,
)


class TestToolUseGuidance:
    def test_web_search_mentioned(self):
        assert "web_search" in TOOL_USE_GUIDANCE

    def test_memory_add_mentioned(self):
        assert 'memory' in TOOL_USE_GUIDANCE

    def test_no_duplicate_tool_calls(self):
        assert "twice" in TOOL_USE_GUIDANCE or "same information" in TOOL_USE_GUIDANCE

    def test_error_retry_mentioned(self):
        assert "error" in TOOL_USE_GUIDANCE.lower()

    def test_has_section_header(self):
        assert "## Tool Use" in TOOL_USE_GUIDANCE


class TestSelfCorrectionGuidance:
    def test_api_failure_handling(self):
        assert "fail" in SELF_CORRECTION_GUIDANCE.lower() or "retry" in SELF_CORRECTION_GUIDANCE.lower()

    def test_web_search_rephrase(self):
        assert "rephrased" in SELF_CORRECTION_GUIDANCE or "queries" in SELF_CORRECTION_GUIDANCE

    def test_irreversible_action_guidance(self):
        assert "irreversible" in SELF_CORRECTION_GUIDANCE

    def test_has_section_header(self):
        assert "## When Things Go Wrong" in SELF_CORRECTION_GUIDANCE


class TestCRMIntegrityGuidance:
    def test_anti_hallucination_rule(self):
        assert "invent" in CRM_INTEGRITY_GUIDANCE.lower() or "fabricat" in CRM_INTEGRITY_GUIDANCE.lower()

    def test_unknown_contact_guidance(self):
        assert "don't have data" in CRM_INTEGRITY_GUIDANCE or "not in memory" in CRM_INTEGRITY_GUIDANCE.lower()

    def test_source_attribution(self):
        assert "source" in CRM_INTEGRITY_GUIDANCE.lower() or "According to" in CRM_INTEGRITY_GUIDANCE

    def test_deal_stage_integrity(self):
        assert "deal" in CRM_INTEGRITY_GUIDANCE.lower()

    def test_has_section_header(self):
        assert "## CRM Data Integrity" in CRM_INTEGRITY_GUIDANCE


class TestProactiveBehaviorsGuidance:
    def test_next_step_suggestion(self):
        assert "next" in PROACTIVE_BEHAVIORS_GUIDANCE.lower()

    def test_memory_save_acknowledgment(self):
        assert "noted" in PROACTIVE_BEHAVIORS_GUIDANCE.lower() or "saved" in PROACTIVE_BEHAVIORS_GUIDANCE.lower()

    def test_pattern_flagging(self):
        assert "pattern" in PROACTIVE_BEHAVIORS_GUIDANCE.lower()

    def test_has_section_header(self):
        assert "## Proactive Behaviors" in PROACTIVE_BEHAVIORS_GUIDANCE


class TestDeepPersona:
    def test_employee_identity(self):
        assert "employee" in DEFAULT_AGENT_IDENTITY.lower()

    def test_ongoing_relationship(self):
        assert "ongoing" in DEFAULT_AGENT_IDENTITY.lower()

    def test_memory_persistence_mentioned(self):
        assert "remember" in DEFAULT_AGENT_IDENTITY.lower()

    def test_proactive_framing(self):
        assert "proactively" in DEFAULT_AGENT_IDENTITY.lower() or "proactive" in DEFAULT_AGENT_IDENTITY.lower()

    def test_not_general_assistant(self):
        # Should explicitly distinguish from generic assistant
        assert "not a general-purpose" in DEFAULT_AGENT_IDENTITY or "dedicated" in DEFAULT_AGENT_IDENTITY

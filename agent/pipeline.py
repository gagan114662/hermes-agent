# agent/pipeline.py
"""
Conversation pipeline — houses the per-turn loop logic.

TurnState holds all mutable state for the main tool-calling loop.
TurnPipeline (future) will drive the loop body as a testable unit.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Any

if TYPE_CHECKING:
    from run_agent import AIAgent

logger = logging.getLogger(__name__)


@dataclass
class TurnState:
    """Mutable state shared across iterations of the main while-loop."""
    # Core conversation state
    messages: list = field(default_factory=list)
    active_system_prompt: str = ""
    effective_task_id: str = ""
    current_turn_user_idx: int = 0
    plugin_turn_context: str = ""  # from pre_llm_call hook
    original_user_message: str = ""
    conversation_history: Optional[list] = None
    system_message: Optional[str] = None

    # Loop control
    api_call_count: int = 0
    final_response: Optional[str] = None
    interrupted: bool = False
    completed: bool = False
    finish_reason: str = "stop"

    # Retry/continuation counters
    codex_ack_continuations: int = 0
    length_continue_retries: int = 0
    truncated_response_prefix: str = ""
    compression_attempts: int = 0
    restart_with_compressed_messages: bool = False
    restart_with_length_continuation: bool = False

    # Post-loop flags
    should_review_memory: bool = False


class TurnPipeline:
    """Future: will drive one iteration of the main tool-calling loop.

    Currently a placeholder — loop body still lives in run_conversation().
    Phase e will move the loop body here.
    """

    def __init__(self, agent: "AIAgent") -> None:
        self.agent = agent

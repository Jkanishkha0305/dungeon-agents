from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class AgentEvent:
    run_id: str
    turn: int
    agent_id: str
    timestamp: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: dict[str, Any]
    tool_success: bool
    tool_duration_ms: float
    llm_input_summary: str
    llm_output_text: str
    llm_model: str
    llm_latency_ms: float
    llm_tokens_in: int
    llm_tokens_out: int
    belief_state: dict[str, Any]
    world_state_snapshot: dict[str, Any]
    diverged: bool
    divergence_reason: str | None
    game_phase: str
    agents_at_exit: list[str]
    turn_limit: int
    termination_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

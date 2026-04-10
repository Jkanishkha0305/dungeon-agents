from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tracing.schema import AgentEvent


class TraceLogger:
    def __init__(self, run_id: str, runs_dir: Path = Path("runs")) -> None:
        self.run_id = run_id
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = self.runs_dir / f"{run_id}.json"
        self.events: list[dict[str, Any]] = []
        self._langfuse = None
        self._enabled = False

        try:
            secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
            public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
            base_url = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
            if base_url and not os.environ.get("LANGFUSE_BASE_URL"):
                os.environ["LANGFUSE_BASE_URL"] = base_url

            if secret_key and public_key:
                from langfuse import get_client

                self._langfuse = get_client()
                self._enabled = True
        except Exception:
            self._langfuse = None
            self._enabled = False

    @property
    def langfuse(self) -> Any | None:
        return self._langfuse

    @property
    def enabled(self) -> bool:
        return self._enabled and self._langfuse is not None

    def log_event(self, event: AgentEvent) -> None:
        event_dict = event.to_dict()
        self.events.append(event_dict)

        if not self.enabled:
            return

        try:
            self._langfuse.update_current_span(
                output={
                    "tool_output": event.tool_output,
                    "tool_success": event.tool_success,
                    "diverged": event.diverged,
                },
                metadata={
                    "turn": event.turn,
                    "agent_id": event.agent_id,
                    "tool_name": event.tool_name,
                    "tool_input": event.tool_input,
                    "divergence_reason": event.divergence_reason,
                    "game_phase": event.game_phase,
                    "agents_at_exit": event.agents_at_exit,
                    "llm_model": event.llm_model,
                    "llm_tokens_in": event.llm_tokens_in,
                    "llm_tokens_out": event.llm_tokens_out,
                    "tool_duration_ms": event.tool_duration_ms,
                    "llm_latency_ms": event.llm_latency_ms,
                },
            )
        except Exception:
            return

    def finalize(self, run_id: str, termination_reason: str) -> None:
        if self.events:
            self.events[-1]["termination_reason"] = termination_reason

        payload = {
            "run_id": run_id,
            "termination_reason": termination_reason,
            "total_turns": len(self.events),
            "events": self.events,
        }
        with self.output_path.open("w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, indent=2, default=str)
        print(f"[trace] wrote {self.output_path} ({len(self.events)} events)")

        if self.enabled:
            try:
                self._langfuse.flush()
            except Exception:
                return

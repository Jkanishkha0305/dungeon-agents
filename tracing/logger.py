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
        self._trace = None

        try:
            from langfuse import Langfuse

            secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
            public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
            host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
            if secret_key and public_key:
                self._langfuse = Langfuse(
                    secret_key=secret_key,
                    public_key=public_key,
                    host=host,
                )
                try:
                    self._trace = self._langfuse.trace(
                        id=run_id,
                        name=f"dungeon-run-{run_id}",
                    )
                except Exception:
                    self._trace = None
        except Exception:
            self._langfuse = None
            self._trace = None

    def log_event(self, event: AgentEvent) -> None:
        event_dict = event.to_dict()
        self.events.append(event_dict)

        if self._trace is None:
            return

        try:
            span = self._trace.span(
                name=f"turn-{event.turn}",
                input={
                    "agent_id": event.agent_id,
                    "tool_name": event.tool_name,
                    "llm_input_summary": event.llm_input_summary,
                },
                output=event.tool_output,
                metadata={
                    "diverged": event.diverged,
                    "divergence_reason": event.divergence_reason,
                    "game_phase": event.game_phase,
                },
            )
            span.generation(
                name=f"llm-{event.turn}",
                model=event.llm_model,
                input=event.llm_input_summary,
                output=event.llm_output_text,
                metadata={
                    "tool_name": event.tool_name,
                    "tool_input": event.tool_input,
                    "tool_success": event.tool_success,
                    "tool_duration_ms": event.tool_duration_ms,
                    "llm_latency_ms": event.llm_latency_ms,
                    "llm_tokens_in": event.llm_tokens_in,
                    "llm_tokens_out": event.llm_tokens_out,
                },
            )
            span.end()
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

        if self._langfuse is not None:
            try:
                self._langfuse.flush()
            except Exception:
                return

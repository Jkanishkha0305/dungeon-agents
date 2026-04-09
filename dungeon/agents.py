from __future__ import annotations

import json
import time
from typing import Any


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": "Move one cell in a cardinal direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right"],
                        "description": "The direction to move.",
                    }
                },
                "required": ["direction"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pick_up",
            "description": "Pick up an item on the current cell.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "enum": ["key"],
                        "description": "The item to pick up.",
                    }
                },
                "required": ["item"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unlock_door",
            "description": "Unlock the adjacent locked door if you have the key.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to the other explorer. It arrives on their next turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_agent": {
                        "type": "string",
                        "description": "The other agent to message.",
                    },
                    "message": {
                        "type": "string",
                        "description": "A short message about what you observed or plan to do.",
                    },
                },
                "required": ["to_agent", "message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "observe",
            "description": "Observe the adjacent cells again before acting.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]


def build_system_prompt(agent_id: str, other_agent_id: str) -> str:
    return (
        f"You are {agent_id}, one of two explorers in a dungeon.\n"
        f"Your teammate is {other_agent_id}.\n"
        "Goal: both explorers must reach the exit. A locked door blocks progress and one "
        "explorer must get the key and unlock the door.\n"
        "You only know your own observable state. Fog of war is strict: you can only see "
        "adjacent cells and any queued messages delivered at the start of your turn.\n"
        "Pick exactly one tool each turn. Keep messages short and concrete. Prefer sharing "
        "facts that remain useful even if your teammate receives them one turn later.\n"
        "Do not invent map knowledge. If uncertain, observe or move conservatively."
    )


def call_llm(
    agent_id: str,
    other_agent_id: str,
    observable_state: dict[str, Any],
    conversation_history: list[dict[str, Any]],
    client: Any,
) -> dict[str, Any]:
    system_message = {
        "role": "system",
        "content": build_system_prompt(agent_id=agent_id, other_agent_id=other_agent_id),
    }
    user_message = {"role": "user", "content": json.dumps(observable_state)}
    messages = [system_message, *conversation_history[-6:], user_message]
    started_at = time.perf_counter()

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="required",
            max_tokens=512,
        )
        latency_ms = (time.perf_counter() - started_at) * 1000
        choice = response.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None) or []
        tool_call = tool_calls[0] if tool_calls else None

        tool_name = "observe"
        tool_input: dict[str, Any] = {}
        if tool_call is not None:
            tool_name = getattr(tool_call.function, "name", "observe") or "observe"
            raw_arguments = getattr(tool_call.function, "arguments", "") or ""
            try:
                parsed_arguments = json.loads(raw_arguments) if raw_arguments else {}
                if isinstance(parsed_arguments, dict):
                    tool_input = parsed_arguments
            except json.JSONDecodeError:
                tool_input = {}

        llm_output_text = message.content or f"Selected tool: {tool_name}"
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        model_name = getattr(response, "model", "gpt-4o-mini")

        return {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "llm_output_text": llm_output_text,
            "llm_model": model_name,
            "llm_latency_ms": latency_ms,
            "llm_tokens_in": prompt_tokens,
            "llm_tokens_out": completion_tokens,
            "llm_input_messages": messages,
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - started_at) * 1000
        return {
            "tool_name": "observe",
            "tool_input": {},
            "llm_output_text": f"LLM error: {exc}",
            "llm_model": "gpt-4o-mini",
            "llm_latency_ms": latency_ms,
            "llm_tokens_in": 0,
            "llm_tokens_out": 0,
            "llm_input_messages": messages,
        }

from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any

from dungeon.agents import call_llm
from dungeon.world import World
from tracing.schema import AgentEvent


def _determine_game_phase(world: World) -> str:
    if world.door_unlocked and world.agents_at_exit():
        return "exiting"
    if world.door_unlocked:
        return "door_unlocked"
    if any("key" in inventory for inventory in world.agent_inventory.values()):
        return "key_found"
    return "exploring"


def _divergence_reason(tool_name: str, tool_output: dict[str, Any]) -> str | None:
    if tool_output.get("success") is True:
        return None
    if tool_name == "move":
        return "move_blocked"
    if tool_name == "pick_up":
        return "item_missing"
    if tool_name == "unlock_door":
        return "door_locked"
    if tool_name == "send_message":
        return "message_failed"
    return None


def _execute_tool(
    world: World,
    agent_id: str,
    other_agent_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    try:
        if tool_name == "move":
            return world.move(agent_id, tool_input.get("direction", ""))
        if tool_name == "pick_up":
            return world.pick_up(agent_id, tool_input.get("item", ""))
        if tool_name == "unlock_door":
            return world.unlock_door(agent_id)
        if tool_name == "send_message":
            return world.send_message(
                agent_id,
                tool_input.get("to_agent", other_agent_id),
                tool_input.get("message", ""),
            )
        if tool_name == "observe":
            return world.observe(agent_id)
    except Exception as exc:
        return {"success": False, "message": str(exc)}

    return {"success": False, "message": f"Unknown tool '{tool_name}'."}


def run_game(
    run_id: str,
    seed: int | None = None,
    turn_limit: int = 60,
    logger: Any = None,
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    world = World(random_seed=seed)
    agent_ids = world.agent_ids
    conversation_histories: dict[str, list[dict[str, Any]]] = {agent_id: [] for agent_id in agent_ids}
    termination_reason: str | None = None
    completed_turns = 0

    for turn in range(1, turn_limit + 1):
        completed_turns = turn
        world.increment_turn()

        active_agent = agent_ids[(turn - 1) % 2]
        other_agent = agent_ids[1 - ((turn - 1) % 2)]

        delivered = world.collect_messages(active_agent)
        observable_state = world.get_observable_state(
            active_agent,
            delivered_messages=delivered,
        )
        llm_result = call_llm(
            agent_id=active_agent,
            other_agent_id=other_agent,
            observable_state=observable_state,
            conversation_history=conversation_histories[active_agent],
            client=client,
        )

        tool_started_at = time.perf_counter()
        tool_output = _execute_tool(
            world=world,
            agent_id=active_agent,
            other_agent_id=other_agent,
            tool_name=llm_result["tool_name"],
            tool_input=llm_result["tool_input"],
        )
        tool_duration_ms = (time.perf_counter() - tool_started_at) * 1000

        assistant_content = llm_result["llm_output_text"] or (
            f"{llm_result['tool_name']} {llm_result['tool_input']}"
        )
        conversation_histories[active_agent].append(
            {"role": "assistant", "content": assistant_content}
        )

        divergence_reason = _divergence_reason(llm_result["tool_name"], tool_output)
        llm_input_messages = llm_result["llm_input_messages"]
        last_user_message = next(
            (
                message.get("content", "")
                for message in reversed(llm_input_messages)
                if message.get("role") == "user"
            ),
            "",
        )
        tool_success = bool(tool_output.get("success"))

        event = AgentEvent(
            run_id=run_id,
            turn=turn,
            agent_id=active_agent,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=llm_result["tool_name"],
            tool_input=llm_result["tool_input"],
            tool_output=tool_output,
            tool_success=tool_success,
            tool_duration_ms=tool_duration_ms,
            llm_input_summary=str(last_user_message)[:200],
            llm_output_text=llm_result["llm_output_text"],
            llm_model=llm_result["llm_model"],
            llm_latency_ms=llm_result["llm_latency_ms"],
            llm_tokens_in=llm_result["llm_tokens_in"],
            llm_tokens_out=llm_result["llm_tokens_out"],
            belief_state=world.get_belief_state(active_agent),
            world_state_snapshot=world.get_world_snapshot(),
            diverged=not tool_output.get("success"),
            divergence_reason=divergence_reason,
            game_phase=_determine_game_phase(world),
            agents_at_exit=world.agents_at_exit(),
            turn_limit=turn_limit,
            termination_reason=None,
        )
        if logger is not None:
            logger.log_event(event)

        status_text = "OK" if tool_success else "FAIL"
        reason = divergence_reason or tool_output.get("message") or "-"
        print(f"T{turn:03d} {active_agent} {llm_result['tool_name']} -> {status_text} [{reason}]")

        if set(world.agents_at_exit()) == set(agent_ids):
            termination_reason = "win"
            break

    if termination_reason is None:
        termination_reason = "turn_limit"

    if logger is not None:
        logger.finalize(run_id, termination_reason)

    return {
        "run_id": run_id,
        "seed": world.random_seed,
        "turns": completed_turns,
        "termination_reason": termination_reason,
        "agents_at_exit": world.agents_at_exit(),
    }

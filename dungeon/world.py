from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import random
from typing import Any


Position = tuple[int, int]


DIRECTION_DELTAS: dict[str, Position] = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}


@dataclass(frozen=True)
class QueuedMessage:
    from_agent: str
    to_agent: str
    content: str


class World:
    """Source of truth for the dungeon state and agent tool interactions."""

    def __init__(
        self,
        size: int = 8,
        agent_ids: tuple[str, str] = ("explorer_a", "explorer_b"),
        obstacle_range: tuple[int, int] = (5, 8),
        random_seed: int | None = None,
        max_generation_attempts: int = 5000,
    ) -> None:
        if size < 8:
            raise ValueError("size must be at least 8")
        if len(agent_ids) != 2:
            raise ValueError("exactly two agent_ids are required")
        if obstacle_range[0] < 0 or obstacle_range[0] > obstacle_range[1]:
            raise ValueError("invalid obstacle_range")

        self.size = size
        self.agent_ids = agent_ids
        self.obstacle_range = obstacle_range
        self.random_seed = random_seed if random_seed is not None else random.randint(0, 10**9)
        self.rng = random.Random(self.random_seed)
        self.max_generation_attempts = max_generation_attempts

        self.turn_count = 0
        self.message_queues: dict[str, list[QueuedMessage]] = {agent_id: [] for agent_id in agent_ids}
        self.message_history: list[dict[str, Any]] = []
        self.delivered_messages_log: dict[str, list[dict[str, Any]]] = {agent_id: [] for agent_id in agent_ids}

        self.agent_positions: dict[str, Position] = {}
        self.agent_inventory: dict[str, set[str]] = {agent_id: set() for agent_id in agent_ids}
        self.agent_seen_cells: dict[str, dict[Position, dict[str, Any]]] = {
            agent_id: {} for agent_id in agent_ids
        }

        self.obstacles: set[Position] = set()
        self.key_position: Position | None = None
        self.door_position: Position | None = None
        self.exit_position: Position | None = None
        self.door_unlocked = False

        self._generate_world()

        for agent_id in self.agent_ids:
            self._update_agent_knowledge(agent_id)

    def observe(self, agent_id: str) -> dict[str, Any]:
        self._validate_agent(agent_id)
        visible_cells = self.get_visible_cells(agent_id)
        self._update_agent_knowledge(agent_id)
        return {
            "success": True,
            "message": f"{agent_id} observes adjacent cells.",
            "position": self.agent_positions[agent_id],
            "visible_cells": visible_cells,
            "inventory": sorted(self.agent_inventory[agent_id]),
            "door_unlocked": self.door_unlocked,
        }

    def move(self, agent_id: str, direction: str) -> dict[str, Any]:
        self._validate_agent(agent_id)
        if direction not in DIRECTION_DELTAS:
            return {
                "success": False,
                "message": f"Unknown direction '{direction}'.",
                "position": self.agent_positions[agent_id],
                "visible_cells": self.get_visible_cells(agent_id),
            }

        current = self.agent_positions[agent_id]
        delta = DIRECTION_DELTAS[direction]
        target = (current[0] + delta[0], current[1] + delta[1])

        if not self._in_bounds(target):
            return {
                "success": False,
                "message": "You bump into the dungeon boundary.",
                "position": current,
                "visible_cells": self.get_visible_cells(agent_id),
            }
        if target in self.obstacles:
            self._update_agent_knowledge(agent_id)
            return {
                "success": False,
                "message": "A wall blocks the way.",
                "position": current,
                "visible_cells": self.get_visible_cells(agent_id),
            }
        if target == self.door_position and not self.door_unlocked:
            self._update_agent_knowledge(agent_id)
            return {
                "success": False,
                "message": "A locked door blocks the way.",
                "position": current,
                "visible_cells": self.get_visible_cells(agent_id),
            }

        self.agent_positions[agent_id] = target
        self._update_agent_knowledge(agent_id)
        return {
            "success": True,
            "message": f"{agent_id} moved {direction}.",
            "position": target,
            "visible_cells": self.get_visible_cells(agent_id),
            "inventory": sorted(self.agent_inventory[agent_id]),
            "on_exit": target == self.exit_position,
        }

    def pick_up(self, agent_id: str, item: str) -> dict[str, Any]:
        self._validate_agent(agent_id)
        if item != "key":
            return {
                "success": False,
                "message": f"Unknown item '{item}'.",
                "position": self.agent_positions[agent_id],
            }
        if self.key_position is None:
            return {
                "success": False,
                "message": "The key has already been taken.",
                "position": self.agent_positions[agent_id],
            }
        if self.agent_positions[agent_id] != self.key_position:
            self._update_agent_knowledge(agent_id)
            return {
                "success": False,
                "message": "There is no key here.",
                "position": self.agent_positions[agent_id],
            }

        self.agent_inventory[agent_id].add("key")
        self.key_position = None
        self._update_all_agent_knowledge()
        return {
            "success": True,
            "message": f"{agent_id} picked up the key.",
            "position": self.agent_positions[agent_id],
            "inventory": sorted(self.agent_inventory[agent_id]),
        }

    def send_message(self, agent_id: str, to_agent: str, message: str) -> dict[str, Any]:
        self._validate_agent(agent_id)
        self._validate_agent(to_agent)
        if to_agent == agent_id:
            return {"success": False, "message": "Agents cannot message themselves."}
        if not message.strip():
            return {"success": False, "message": "Message cannot be empty."}

        queued = QueuedMessage(from_agent=agent_id, to_agent=to_agent, content=message.strip())
        self.message_queues[to_agent].append(queued)
        history_record = {
            "from_agent": agent_id,
            "to_agent": to_agent,
            "content": queued.content,
            "queued_for_next_activation": True,
        }
        self.message_history.append(history_record)
        return {
            "success": True,
            "message": f"Queued message from {agent_id} to {to_agent}.",
            "queued_message": history_record,
        }

    def unlock_door(self, agent_id: str) -> dict[str, Any]:
        self._validate_agent(agent_id)
        if self.door_unlocked:
            return {"success": False, "message": "The door is already unlocked."}
        if "key" not in self.agent_inventory[agent_id]:
            return {"success": False, "message": "You need the key to unlock the door."}
        if self.door_position is None:
            return {"success": False, "message": "There is no door to unlock."}
        if self.door_position not in self._adjacent_positions(self.agent_positions[agent_id]):
            self._update_agent_knowledge(agent_id)
            return {"success": False, "message": "You must stand next to the door to unlock it."}

        self.door_unlocked = True
        self._update_all_agent_knowledge()
        return {
            "success": True,
            "message": f"{agent_id} unlocked the door.",
            "door_position": self.door_position,
            "door_unlocked": True,
        }

    def collect_messages(self, agent_id: str) -> list[dict[str, Any]]:
        self._validate_agent(agent_id)
        queued = self.message_queues[agent_id]
        self.message_queues[agent_id] = []
        delivered = [
            {"from_agent": message.from_agent, "to_agent": message.to_agent, "content": message.content}
            for message in queued
        ]
        self.delivered_messages_log[agent_id].extend(delivered)
        return delivered

    def get_visible_cells(self, agent_id: str) -> list[dict[str, Any]]:
        self._validate_agent(agent_id)
        position = self.agent_positions[agent_id]
        visible = [self._describe_cell(adjacent) for adjacent in self._adjacent_positions(position)]
        visible.sort(key=lambda cell: (cell["position"][0], cell["position"][1]))
        return visible

    def peek_messages(self, agent_id: str) -> list[dict[str, Any]]:
        self._validate_agent(agent_id)
        return [
            {"from_agent": message.from_agent, "to_agent": message.to_agent, "content": message.content}
            for message in self.message_queues[agent_id]
        ]

    def get_observable_state(
        self,
        agent_id: str,
        delivered_messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._validate_agent(agent_id)
        self._update_agent_knowledge(agent_id)
        return {
            "agent_id": agent_id,
            "position": self.agent_positions[agent_id],
            "inventory": sorted(self.agent_inventory[agent_id]),
            "visible_cells": self.get_visible_cells(agent_id),
            "pending_messages": (
                list(delivered_messages)
                if delivered_messages is not None
                else self.peek_messages(agent_id)
            ),
            "door_unlocked": self.door_unlocked,
            "turn_count": self.turn_count,
        }

    def get_belief_state(self, agent_id: str) -> dict[str, Any]:
        self._validate_agent(agent_id)
        seen_cells = [
            self.agent_seen_cells[agent_id][position]
            for position in sorted(self.agent_seen_cells[agent_id])
        ]
        return {
            "position": self.agent_positions[agent_id],
            "has_key": "key" in self.agent_inventory[agent_id],
            "door_unlocked": self.door_unlocked,
            "known_cells": seen_cells,
            "messages_received": list(self.delivered_messages_log[agent_id]),
            "goal": "Both agents reach the exit after unlocking the door.",
        }

    def get_world_snapshot(self) -> dict[str, Any]:
        rows: list[list[dict[str, Any]]] = []
        for row in range(self.size):
            row_cells = []
            for col in range(self.size):
                row_cells.append(self._describe_cell((row, col)))
            rows.append(row_cells)
        return {
            "size": self.size,
            "random_seed": self.random_seed,
            "door_unlocked": self.door_unlocked,
            "grid": rows,
            "agent_positions": dict(self.agent_positions),
            "agent_inventory": {
                agent_id: sorted(inventory) for agent_id, inventory in self.agent_inventory.items()
            },
        }

    def agents_at_exit(self) -> list[str]:
        return [
            agent_id
            for agent_id, position in self.agent_positions.items()
            if position == self.exit_position
        ]

    def increment_turn(self) -> None:
        self.turn_count += 1

    def _generate_world(self) -> None:
        for _ in range(self.max_generation_attempts):
            candidate = self._build_candidate_layout()
            if self._layout_is_solvable(candidate):
                self._apply_layout(candidate)
                return
        raise RuntimeError("failed to generate a solvable dungeon layout")

    def _build_candidate_layout(self) -> dict[str, Any]:
        all_positions = [(row, col) for row in range(self.size) for col in range(self.size)]
        obstacle_count = self.rng.randint(*self.obstacle_range)
        obstacles = set(self.rng.sample(all_positions, obstacle_count))

        remaining_positions = [position for position in all_positions if position not in obstacles]
        key_position, door_position, exit_position = self.rng.sample(remaining_positions, 3)

        remaining_positions = [
            position
            for position in remaining_positions
            if position not in {key_position, door_position, exit_position}
        ]
        agent_starts = self.rng.sample(remaining_positions, len(self.agent_ids))

        return {
            "obstacles": obstacles,
            "key_position": key_position,
            "door_position": door_position,
            "exit_position": exit_position,
            "agent_positions": dict(zip(self.agent_ids, agent_starts, strict=True)),
        }

    def _layout_is_solvable(self, candidate: dict[str, Any]) -> bool:
        obstacles: set[Position] = candidate["obstacles"]
        key_position: Position = candidate["key_position"]
        door_position: Position = candidate["door_position"]
        exit_position: Position = candidate["exit_position"]
        agent_positions: dict[str, Position] = candidate["agent_positions"]

        if any(
            self._adjacent_positions(position) == []
            for position in (key_position, door_position, exit_position, *agent_positions.values())
        ):
            return False

        unlockers: list[str] = []
        for agent_id, start in agent_positions.items():
            can_reach_key = self._path_exists(
                start=start,
                goals={key_position},
                obstacles=obstacles,
                door_position=door_position,
                door_open=False,
            )
            can_reach_door_adjacent = self._path_exists(
                start=key_position,
                goals=set(self._adjacent_positions(door_position)),
                obstacles=obstacles,
                door_position=door_position,
                door_open=False,
            )
            if can_reach_key and can_reach_door_adjacent:
                unlockers.append(agent_id)

        if not unlockers:
            return False

        if not all(
            self._path_exists(
                start=agent_positions[agent_id],
                goals={exit_position},
                obstacles=obstacles,
                door_position=door_position,
                door_open=True,
            )
            for agent_id in self.agent_ids
        ):
            return False

        locked_exit_access = [
            self._path_exists(
                start=agent_positions[agent_id],
                goals={exit_position},
                obstacles=obstacles,
                door_position=door_position,
                door_open=False,
            )
            for agent_id in self.agent_ids
        ]
        return not all(locked_exit_access)

    def _apply_layout(self, layout: dict[str, Any]) -> None:
        self.obstacles = set(layout["obstacles"])
        self.key_position = layout["key_position"]
        self.door_position = layout["door_position"]
        self.exit_position = layout["exit_position"]
        self.agent_positions = dict(layout["agent_positions"])
        self.door_unlocked = False

    def _path_exists(
        self,
        start: Position,
        goals: set[Position],
        obstacles: set[Position],
        door_position: Position,
        door_open: bool,
    ) -> bool:
        if start in goals:
            return True

        queue: deque[Position] = deque([start])
        visited = {start}

        while queue:
            current = queue.popleft()
            for neighbor in self._adjacent_positions(current):
                if neighbor in visited:
                    continue
                if neighbor in obstacles:
                    continue
                if neighbor == door_position and not door_open:
                    continue
                if neighbor in goals:
                    return True
                visited.add(neighbor)
                queue.append(neighbor)
        return False

    def _update_all_agent_knowledge(self) -> None:
        for agent_id in self.agent_ids:
            self._update_agent_knowledge(agent_id)

    def _update_agent_knowledge(self, agent_id: str) -> None:
        position = self.agent_positions[agent_id]
        self.agent_seen_cells[agent_id][position] = self._describe_cell(position)
        for adjacent in self._adjacent_positions(position):
            self.agent_seen_cells[agent_id][adjacent] = self._describe_cell(adjacent)

    def _describe_cell(self, position: Position) -> dict[str, Any]:
        occupants = [
            agent_id
            for agent_id, agent_position in self.agent_positions.items()
            if agent_position == position
        ]
        terrain = "floor"
        if position in self.obstacles:
            terrain = "wall"
        elif position == self.door_position:
            terrain = "door_unlocked" if self.door_unlocked else "door_locked"
        elif position == self.exit_position:
            terrain = "exit"

        item = "key" if position == self.key_position else None
        return {
            "position": position,
            "terrain": terrain,
            "item": item,
            "occupants": occupants,
        }

    def _adjacent_positions(self, position: Position) -> list[Position]:
        candidates = [
            (position[0] - 1, position[1]),
            (position[0] + 1, position[1]),
            (position[0], position[1] - 1),
            (position[0], position[1] + 1),
        ]
        return [candidate for candidate in candidates if self._in_bounds(candidate)]

    def _in_bounds(self, position: Position) -> bool:
        return 0 <= position[0] < self.size and 0 <= position[1] < self.size

    def _validate_agent(self, agent_id: str) -> None:
        if agent_id not in self.agent_ids:
            raise ValueError(f"unknown agent_id '{agent_id}'")

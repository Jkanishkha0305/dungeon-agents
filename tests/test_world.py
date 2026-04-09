from __future__ import annotations

from dungeon.world import DIRECTION_DELTAS, World


def _free_adjacent_to_door(world: World) -> tuple[int, int]:
    for position in world._adjacent_positions(world.door_position):  # noqa: SLF001
        if position not in world.obstacles:
            return position
    raise AssertionError("expected at least one reachable cell adjacent to the door")


def test_world_generates_with_solvable_layout() -> None:
    for seed in range(20):
        world = World(random_seed=seed)
        assert world.key_position is not None
        assert world.door_position is not None
        assert world.exit_position is not None


def test_agent_starts_on_valid_non_obstacle_position() -> None:
    world = World(random_seed=1)
    for agent_id in world.agent_ids:
        assert world.agent_positions[agent_id] not in world.obstacles


def test_move_valid_direction_succeeds_for_at_least_one_direction_from_start() -> None:
    world = World(random_seed=7)
    agent_id = world.agent_ids[0]

    results = [world.move(agent_id, direction) for direction in DIRECTION_DELTAS]
    assert any(result["success"] for result in results)


def test_move_invalid_direction_returns_failure() -> None:
    world = World(random_seed=2)
    result = world.move(world.agent_ids[0], "northwest")
    assert result["success"] is False


def test_pick_up_at_wrong_position_returns_failure() -> None:
    world = World(random_seed=3)
    agent_id = world.agent_ids[0]
    world.agent_positions[agent_id] = (0, 0)
    world._update_agent_knowledge(agent_id)  # noqa: SLF001

    result = world.pick_up(agent_id, "key")
    assert result["success"] is False


def test_pick_up_at_key_position_returns_success_and_key_disappears() -> None:
    world = World(random_seed=4)
    agent_id = world.agent_ids[0]
    world.agent_positions[agent_id] = world.key_position
    world._update_agent_knowledge(agent_id)  # noqa: SLF001

    result = world.pick_up(agent_id, "key")
    assert result["success"] is True
    assert world.key_position is None
    assert "key" in world.agent_inventory[agent_id]


def test_unlock_door_without_key_returns_failure() -> None:
    world = World(random_seed=5)
    agent_id = world.agent_ids[0]
    world.agent_positions[agent_id] = _free_adjacent_to_door(world)
    world._update_agent_knowledge(agent_id)  # noqa: SLF001

    result = world.unlock_door(agent_id)
    assert result["success"] is False
    assert world.door_unlocked is False


def test_unlock_door_with_key_adjacent_to_door_returns_success() -> None:
    world = World(random_seed=6)
    agent_id = world.agent_ids[0]
    world.agent_inventory[agent_id].add("key")
    world.agent_positions[agent_id] = _free_adjacent_to_door(world)
    world._update_agent_knowledge(agent_id)  # noqa: SLF001

    result = world.unlock_door(agent_id)
    assert result["success"] is True
    assert world.door_unlocked is True


def test_send_message_and_collect_messages_round_trip() -> None:
    world = World(random_seed=7)
    sender, recipient = world.agent_ids

    result = world.send_message(sender, recipient, "found key soon")
    delivered = world.collect_messages(recipient)

    assert result["success"] is True
    assert delivered == [
        {"from_agent": sender, "to_agent": recipient, "content": "found key soon"}
    ]


def test_agents_at_exit_returns_correct_agents() -> None:
    world = World(random_seed=8)
    first_agent, second_agent = world.agent_ids
    world.agent_positions[first_agent] = world.exit_position
    world.agent_positions[second_agent] = (0, 0)
    world._update_agent_knowledge(first_agent)  # noqa: SLF001
    world._update_agent_knowledge(second_agent)  # noqa: SLF001

    assert world.agents_at_exit() == [first_agent]


def test_get_belief_state_has_required_keys() -> None:
    world = World(random_seed=9)
    belief_state = world.get_belief_state(world.agent_ids[0])

    assert set(belief_state) == {
        "position",
        "has_key",
        "door_unlocked",
        "known_cells",
        "messages_received",
        "goal",
    }


def test_get_world_snapshot_returns_eight_by_eight_grid_structure() -> None:
    world = World(random_seed=10)
    snapshot = world.get_world_snapshot()

    assert snapshot["size"] == 8
    assert len(snapshot["grid"]) == 8
    assert all(len(row) == 8 for row in snapshot["grid"])
    first_cell = snapshot["grid"][0][0]
    assert set(first_cell) == {"position", "terrain", "item", "occupants"}

# Dungeon Agents

Two `gpt-4o-mini` agents explore a small dungeon, emit structured per-turn traces, and can be inspected in a lightweight legibility viewer. The simulation is intentionally simple; the main deliverable is diagnosable multi-agent behavior rather than agent skill.

## What It Includes

- `dungeon/world.py`: source-of-truth dungeon state, fog of war, solvable map generation, and tool methods
- `dungeon/agents.py`: OpenAI function-calling wrapper with five tools
- `dungeon/game.py`: custom alternating turn loop with message-delay semantics
- `tracing/schema.py`: structured `AgentEvent` model
- `tracing/logger.py`: local JSON trace writer with best-effort Langfuse export
- `legibility/viewer.html`: single-file trace viewer for replay and diagnosis
- `runs/`: generated JSON traces from real game runs

## Running

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# add OPENAI_API_KEY to .env
.venv/bin/python scripts/run_game.py --runs 5 --seed 10
```

To run tests:

```bash
.venv/bin/python -m pytest tests/ -v
```

## Viewer

Open `legibility/viewer.html` in a browser and load one of the files from `runs/`.

The viewer is designed to answer:

1. What happened?
2. Why did it happen?
3. What should change next?

It shows:

- a left-hand timeline of turns with divergence highlights
- an 8x8 dungeon replay grid
- a toggle between ground truth and the active agent’s belief state
- tool input/output for the selected turn
- the recorded LLM output text
- per-turn metadata such as latency, phase, and exit state

## Notes

- Langfuse is optional. If the keys are absent, local JSON traces still write to `runs/`.
- Current traces include interesting failures and coordination issues; they do not require the agents to be good at the game.

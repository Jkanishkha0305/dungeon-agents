# Dungeon Agents

Two LLM agents (`gpt-4o-mini`) explore an 8x8 dungeon, produce structured traces, rendered in a legibility viewer.

## Running

```bash
pip install -r requirements.txt
cp .env.example .env  # add OPENAI_API_KEY
python scripts/run_game.py --runs 5 --turn-limit 60
```

## Structure

- `dungeon/world.py` — grid, fog-of-war, BFS solvability, tool methods
- `dungeon/agents.py` — OpenAI function calling wrapper
- `dungeon/game.py` — turn loop, message delivery, termination
- `tracing/schema.py` — AgentEvent dataclass (23 fields)
- `tracing/logger.py` — JSON file writer + Langfuse (best-effort)
- `legibility/viewer.html` — single-file trace viewer
- `runs/` — JSON trace files (gitignored except `.gitkeep`)
- `scripts/run_game.py` — CLI entry point

## Key decisions

- No LangGraph — custom loop for full trace control
- `diverged = not tool_output["success"]` — deterministic, never manufactured
- World enforces fog-of-war server-side (agents never get ground truth)
- JSON files are the real deliverable; Langfuse is best-effort

# Submission Runs

Curated trace files for reviewer walkthroughs.

## Recommended Order

1. `failure_repeated_pickup_seed42.json`
   Repeated `pick_up` failures after the agent gets stuck on a bad local belief.

2. `coordination_message_heavy_seed12.json`
   Lower-divergence run with heavy use of delayed messaging between agents.

3. `navigation_wander_seed42.json`
   Cleaner movement-heavy run that shows exploration without obvious catastrophic looping.

4. `observation_heavy_failure_seed21.json`
   A longer failure mode with frequent observation and messaging but no successful coordination.

## Notes

- All files in this folder are real OpenAI-backed traces.
- No file in this curated set contains `LLM error` fallback output.
- I did not get a winning run despite searching multiple seeded batches, so this set focuses on diagnosable failure modes instead.

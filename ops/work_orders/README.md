# Work Orders Logbook

Purpose: add an accountability layer for multi-agent work.

## Rules
- Every work order has a log file: `ops/work_orders/<WORK_ORDER>.log.md`
- Workers must write:
  - Start time (UTC) when beginning work
  - End time (UTC) when done
  - Work order number
  - Expected work (from WO)
  - What was actually done
  - Files changed
  - Commands run (verification only)
  - Results / proof
  - Blockers / risks
  - Next handoff notes

## Format
- Keep entries chronological.
- Use UTC timestamps.
- No secrets/tokens in logs.

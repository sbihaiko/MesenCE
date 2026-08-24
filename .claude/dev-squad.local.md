---
# dev-squad per-project config — committed & shared across the team.
# Edit with /squad-config; see /config-help for every setting.
# schema: v2.0.90
# Auto-materialized on config read: every option is written explicitly (even
# defaults), your values are preserved, and removed keys are dropped.
# Model tiering below is HONORED: dev-squad neutralizes any global
# CLAUDE_CODE_SUBAGENT_MODEL pin per-project (.claude/settings.json env="")
# so per-role model: dispatch takes effect (Workflow + Task both honor it).

# Execution strategy
parallelMode: true        # run independent tasks in a batch concurrently (worktrees)
strictBatch: false         # true = one failed task aborts the whole batch
autoCommit: true          # commit the verified result to the project's main branch
decisionMode: autonomous   # fixed in V1 (workflows don't pause mid-run)

# Phase control (per-run override via /scout, /spec, /plan; null = full run)
stopAfter: null             # null | scout | spec | plan | execute
fastPath: auto             # auto (scale pipeline to task size) | off (always full)

# Execution tuning
dox: true                   # maintain a DOX AGENTS.md hierarchy
proxyRevisionCap: 2        # spec/decompose proxy revision rounds
maxRetries: 3             # actor-critic cycles per task before stagnation

# Model tiering by work nature (MECHANICAL vs INTERPRETIVE)
models:
  mechanical: haiku
  execution: sonnet
  review: sonnet
  review_critical: opus

# Per-role overrides (empty = use tier defaults from 'models' above).
# Honored per-role once the global subagent pin is neutralized (see header NOTE).
model_overrides:

# Scope guard: project-specific generated files (UNIONED with lock-file built-ins)
allowed_generated: []

# Frontend visual verification (runs on web-app projects when frontend files changed)
visualVerify: auto          # auto | true | false
visualDepth: 3             # 1 smoke | 2 +interaction | 3 +screenshots
visualTimeoutSec: 120        # server-readiness + per-phase wall-clock cap
visualTier: auto            # auto | 1 | 2 | 3
visual_tier3_mode: advisory    # advisory | hard
---

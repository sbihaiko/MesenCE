# ADR-0092: Every existing script in scripts/ (mep_lint.py, mep_compare.py, mep_render_audio.py, validate-specs.py) is invoked via `python3 scripts/<name>.py` and none carry the executable bit; this spec's two new scripts are the first to require `chmod +x` and direct `./scripts/<name>.py` invocation (AC-2, AC-3), a minor convention divergence for the actor to be aware of, not a defect.

- Status: superseded (consolidated 2026-08-27)
- Date: 2026-08-26
- Superseded by: ADR-0137

## Context
Raised during spec

## Decision
Either keep the new scripts consistent with the rest of scripts/ (python3 scripts/mep_build.py ..., adjust AC-2/AC-3 to drop the -x check and the leading ./), or, if a shebang+chmod convention is intentionally being introduced here, note it once so future scripts/*.py additions follow the same choice consistently.

## Consequences


## Alternatives


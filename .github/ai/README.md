# Community-pack validation prompt family

Versioned Claude prompts for the community HD/MEP pack validation pipeline.
Each file is the single source for one LLM step — both invokers render the
same file, so a pack triaged locally and one triaged by the CI workflow are
judged against identical instructions.

## Family

| File | Step | Active |
|---|---|---|
| `validate-classify.md` | Verdict / assets / author / comment / recipe fragment | Yes |
| `validate-autofix.md` | mep_lint.py drift autofix (live-core cross-check) | Dormant (`LIVE_VALIDATION_ENABLED: 'false'`) |

`validate-autofix.md` is the single source for the autofix step, same as
`validate-classify.md` is for classify: the workflow's "Prepare autofix
prompt" step renders it (fills `{{DRIFT_LINES}}`/`{{GAME}}`) and the
"Autofix mep_lint.py drift" step consumes the rendered prompt. The
live-core subsystem it belongs to is off by default, and the local script
does not run the autofix step at all.

## Flow (deterministic + one LLM step)

```
issue ──> fetch_pack.py ──> mep_lint.py ──> sha256 ──> [classify: validate-classify.md]
     ──> mep_recipe.py assemble-sources ──> validate + dry-run ──> apply (comment/label/Project/mep-meta)
```

The deterministic steps (download, lint, hashes, recipe assembly, gate,
comment/label/Project writes, mep-meta upsert) live in the repo scripts and in
`scripts/validate_pack_local.sh` (local) / `community-pack-validate.yml` (CI).
Only the classify step is an LLM prompt.

## Invoking

**Local** — `scripts/validate_pack_local.sh <issue-number> [--llm claude|session]`:

1. downloads the pack (`fetch_pack.py`, allow-list + 300MB cap),
2. lints it (`mep_lint.py`),
3. renders `validate-classify.md` (fills `{{ISSUE_NUMBER}}`,
   `{{EXTERNAL_ASSETS_SUFFIX}}`, and `{{PACK_BRIEF}}` from
   `scripts/classify_pack_brief.py`),
4. runs Claude on the rendered prompt (headless, or supervised in
   `--llm session` mode),
5. assembles/validates the recipe when external assets are declared,
6. records state on the issue: verdict comment, labels, Project
   Status/Category/Pack Hash, and the `<!-- mep-meta -->` comment.

**CI** — `community-pack-validate.yml`, "Prepare classify prompt" fills the
same three placeholders and "Classify pack (Claude Code Action)" runs the
rendered prompt (`--disallowedTools Bash,Read`). The deterministic steps
are the same scripts.

## Rendering contract

A prompt file is a Markdown document; the invoker extracts:

- the prompt text between `<!-- PROMPT -->` and `<!-- SCHEMA -->`,
- the JSON schema after `<!-- SCHEMA -->` to end of file,
- and substitutes `{{PLACEHOLDER}}` tokens in the prompt text before invoking
  Claude.

Files must stay portable: no runner-specific env, no GitHub Actions
expressions. Anything dynamic is a `{{PLACEHOLDER}}` filled by the invoker.

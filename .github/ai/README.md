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

`validate-autofix.md` is extracted from the CI workflow for completeness but
the live-core subsystem it belongs to is off by default; it is not invoked by
the local script.

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
3. renders `validate-classify.md` (fills `{{ISSUE_NUMBER}}` and
   `{{EXTERNAL_ASSETS_SUFFIX}}` from the issue body),
4. runs Claude on the rendered prompt (headless, or supervised in
   `--llm session` mode),
5. assembles/validates the recipe when external assets are declared,
6. records state on the issue: verdict comment, labels, Project
   Status/Category/Pack Hash, and the `<!-- mep-meta -->` comment.

**CI** — `community-pack-validate.yml`, "Prepare classify prompt" fills the
same two placeholders and "Classify pack (Claude Code Action)" runs the
rendered prompt. The deterministic steps are the same scripts.

## Rendering contract

A prompt file is a Markdown document; the invoker extracts:

- the prompt text between `<!-- PROMPT -->` and `<!-- SCHEMA -->`,
- the JSON schema after `<!-- SCHEMA -->` to end of file,
- and substitutes `{{PLACEHOLDER}}` tokens in the prompt text before invoking
  Claude.

Files must stay portable: no runner-specific env, no GitHub Actions
expressions. Anything dynamic is a `{{PLACEHOLDER}}` filled by the invoker.

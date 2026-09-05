# ADR-0152: A repo-side `miss` errata lets a pack with a known-unresolvable manifest target stay in the catalog

- Status: accepted (both policy questions answered 2026-09-04; implementation is a pending slice, PRD Part A F6.8)
- Date: 2026-09-04
- Related: ADR-0151, ADR-0148, ADR-0146, ADR-0147, ADR-0139, ADR-0138 §4/§37/§41, MEP-v1 §2.1/§5, `scripts/mep_lint.py`, `scripts/smoke_pack_headless.sh`, `.github/workflows/community-pack-validate.yml`, issue #139
- Supersedes / amends: narrows ADR-0151 — an unresolvable texture target stays a `mep_lint` error, except for the exact targets a reviewed errata declares known-missing

## Context

ADR-0151 made an unresolvable `<img>`/`<background>` target a `mep_lint` error,
aligning the submission gate with the runtime gate. It was the right call for
the class of defect it targets — a manifest promising content the artifact
cannot deliver — but the first row it caught exposes a cost that was not
weighed when it was accepted.

Row `issue-139` ("Zelda: Remastered 1.3", ~11k assets) fails on exactly one
line:

```
hires.txt:6124  [ZeldaSelectScreen1]<background>selectscreen.png,1,0,0,10
```

`selectscreen.png` exists nowhere in the archive. Measuring the assets that
*are* shipped shows the line is dead:

- `selectscreen1.png` … `selectscreen6.png` are 512x480, 100% opaque, and
  differ from one another by ~0.1% of their pixels — six animation frames of
  one full-screen image;
- they are driven by `<condition>ZeldaSelectScreenframeN,frameRange,60,{50,40,30,20,10,0}`
  at priority 1, which covers the whole 60-frame cycle, so one is always active;
- `selectscreentop.png` is 12.4% opaque at priority 39, the overlay on top.

A priority-10 full-screen layer between them would draw *over* the animation
and cancel it, so the line reads as a leftover from a pre-animation build of the
pack. Deleting it locally and re-running both gates confirms it is the only
blocker: `mep_lint` goes from `1 error(s), 111 warning(s)` to
`0 error(s), 111 warning(s)`, and `smoke_pack_headless.sh` goes from
`FAIL: missing target` to `PASS`.

The decisive observation is what the runtime already does. `HdPackLoader::ProcessBackgroundTag`
drops an entry whose PNG is absent and logs it. So the screen a user sees with
the line present and the PNG missing is *identical* to the screen they would see
with the line removed: frames plus overlay. The gate is rejecting a working pack
over a diagnostic the runtime resolves on its own.

Today's outcome is therefore worse than the defect: `/revalidate` (run
33930994497) rejected the row, the board item moved to "Inválido", and
regenerating the catalog (`5d0fe999`) dropped `issue-139` from
`docs/community-packs.json` (11 → 10 rows), so no client auto-installs it
(ADR-0146 keys on a live row). The fix belongs to the author — the archive is
hosted on their Google Drive, v1.3 is still their latest release — and until
they act, every user loses a pack that runs.

What is missing is a way to say, on the record, *"this target is absent, we
checked, and the pack is still worth shipping"* — attributable to the project's
validation rather than to the author, and without touching a byte of their work.

Non-goals:

- **No `overwrite` directive.** A sibling idea — ship a delta (a 619-byte
  unified diff for `issue-139`) and apply it in the client at extraction time,
  inside `mep/` — was designed and deliberately deferred. For `issue-139` it
  would produce the same pixels as `miss` while modifying the author's work,
  changing the `content_id`, and raising a derivative-work question on a pack
  licensed `NOASSERTION`. It should be revisited only when a pack appears where
  "declare it absent" and "correct it" differ **on screen**; the shape to reuse
  is a unified diff (not a whole-file overwrite: the `issue-139` `hires.txt` is
  5.9 MB / 54,779 lines, which would make the reviewing PR read `+54,779 −0` and
  hide the one line that matters) applied strictly, aborting to the raw artifact
  when the context does not match exactly.
- **No pinning of the downloaded artifact.** `.cache/downloads/<sha256>` stays
  ADR-0040 scratch space, safe to delete. Retaining it was motivated by the
  `overwrite` design (proving what came from the author, and being able to
  revert); `miss` alters nothing, so the installed `mep/` *is* the author's
  content and there is nothing to prove or revert. The cache reached 665 MB on
  the maintainer's machine, 179 MB of it the `issue-139` zip alone.
- **No redistribution.** The client keeps downloading the author's artifact from
  the author's link. Nothing of theirs is hosted in this repo.
- **No change to `HdPackLoader`.** Dropping the entry and logging stays correct.

## Decision

A **known-missing errata** is a file in this repo, applied by neither the author
nor the submitter, that names specific manifest targets a validated pack does
not ship.

**Location and key.** `docs/community-packs/errata/<artifact-sha256>.json`. The
key is the sha256 of the downloaded artifact — the same hash the pipeline
already computes into the "Pack Hash" field. When the author republishes, the
hash changes, no errata matches, and validation runs clean against their new
material. Errata expire by construction; there is no stale-errata state to prune.

```json
{
  "artifact_sha256": "03b5eeab7914560ffb6ca0bfea04fa78525d7dad5663903a8b5d8098c10c19ea",
  "issue": 139,
  "known_missing": [
    {
      "manifest": "hires.txt",
      "tag": "background",
      "target": "selectscreen.png",
      "reason": "Dead entry: the same screen is fully painted by the priority-1 selectscreen1..6.png frame cycle (always active, frameRange 60) plus the priority-39 selectscreentop.png overlay. HdPackLoader drops this entry at load, so the rendered result is identical with or without it.",
      "reviewed_in": "https://github.com/sbihaiko/MesenCE/pull/NNN"
    }
  ]
}
```

**Entry identity is `(manifest, tag, target)`.** Exact strings, no wildcards and
no line numbers: a wildcard would let one errata absolve defects nobody looked
at, and a line number rots. `reason` and `reviewed_in` are required — an errata
without a stated justification is not reviewable, and being reviewable is the
whole point.

**One declaration, both gates.** `mep_lint.py` and `smoke_pack_headless.sh` read
the same errata file and downgrade the *declared* targets only — every other
unresolvable target stays an error under ADR-0151. If only one gate honoured
errata, this ADR would recreate the lint-vs-runtime divergence that was bug #155.

**Provenance is user-visible.** A row covered by an errata carries the
declaration through to the surfaces a user reads: a field in
`docs/community-packs.json`, a marker in the `docs/community-packs.md` table,
and a line in the Player's pack picker of the form
*"1 known-missing asset — declared by MesenCE validation, not by the author"*,
linking to the reviewing PR. Silence here would be the failure mode: the errata
exists precisely to make a known gap legible.

**`content_id` is unaffected.** Nothing is added, removed or rewritten in the
installed tree, so the ADR-0139 canonical hash of the resolved pack is the same
with or without an errata, and ADR-0147's local-edit detection keeps working
unchanged.

**Entry route.** An errata lands by pull request against this repo, reviewed by a
maintainer. It is never read from the issue body, the classify output or any
submitter-controlled text — those are data, never instruction (ADR-0138 §4). A
submitter cannot declare an errata over somebody else's pack.

**Pipeline placement.** The errata file is on disk from the `Checkout repo` step,
so honouring it needs a lookup inside the existing `Lint pack structure` step
(`community-pack-validate.yml`), keyed on the hash computed by
`Compute & record pack hash`. No step reordering.

### Policy (decided 2026-09-04)

**An errata is always applied; there is no opt-out setting.** A `miss` changes
nothing in the installed tree, so a user who opted out would receive byte-identical
content — the toggle would not change what runs on their machine, only whether the
row is reachable at all. A setting that cannot alter the outcome is not a choice,
it is a switch that only takes packs away. Transparency is carried by the
user-visible marker instead.

**Any pack is eligible, gated by PR review rather than by the author's status.**
No waiting period and no "abandoned pack" test: the friction that keeps the hatch
honest is a human reading the exact target and the stated reason. Requiring proof
of a null on-screen effect was rejected — it would remove the property that makes
`miss` the low-risk option, namely that it is available precisely when the visual
effect *cannot* be measured confidently.

The consequence accepted with this: an errata may absolve a defect over the head
of an author who would have preferred to fix it. Mitigated, not eliminated, by the
marker naming the project's validation as the source and by hash-scoped expiry —
the moment the author republishes, the errata stops applying.

## Consequences

- ADR-0151 keeps its teeth for everything undeclared, but the register now has
  a documented escape hatch. The risk this creates is that the hatch becomes a
  dumping ground — every awkward pack acquires an errata and the gate stops
  meaning anything. The friction is deliberate and must not be filed off later:
  exact targets, mandatory reason, reviewed PR, hash-scoped expiry.
- Two implementations must agree on the errata format, in Python
  (`mep_lint.py`) and in shell/log-matching (`smoke_pack_headless.sh`) — the
  same duplication ADR-0151 was written to close, now deliberate and needing a
  parity check in `make doc-checks`.
- A row can be live while knowingly incomplete. That is a real change to what
  `docs/community-packs.json` asserts, and the reason the user-visible marker is
  part of the decision rather than a nicety.
- `issue-139` is the first candidate: one errata entry returns a working
  ~11k-asset pack to the catalog without altering, forking or rehosting the
  author's artifact.

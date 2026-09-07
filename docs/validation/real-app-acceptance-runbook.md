# Real-app acceptance runbook — the residue that stays on the human side

After waves 1–4 of `docs/validation/manual-validation-automation-plan.md`,
every item that was a *structural code gap* is closed — the last one, "the
OSD toast appearing", by ADR-0167's HUD-only capture seam (wave 4). What is
left on this runbook is **genuinely human, hardware or pixel**: each item
carries its reason, and none can be driven headless — a headless assertion
for any of them would assert a fake (a faked file picker, a faked pad, a
recorded judgement).

This consolidates that residue into one pass a human runs on a real machine
with a display, a physical pad and speakers. It accepts product behaviour;
it does not re-run what the suites already assert. A reproducible failure
here is a bug (or, if it reveals a decision, an ADR) — see "Where a failure
goes".

## Prerequisites

- The built app on the machine (`scripts/build_app_macos.sh`, or run the
  IDE build) — no headless shell.
- A No-Intro ROM for the NES checks (e.g. `Zelda.nes`, `Mega Man 3`).
- A physical USB controller (XInput / DirectInput / libevdev /
  extendedGamepad — whatever the host exposes).
- Speakers or headphones.
- ~20 minutes. Nothing on this list gates the roadmap — all code is shipped;
  this runbook clears acceptance debt.

## 1. Composition editor GUI (F9.18 — ADR-0164 / ADR-0165 / ADR-0166)

**Why it stays human:** the engine (`scripts/compose_engine.py`) is host-free
and its two ADR-0164 acceptance tests run headless; the *view*
(`scripts/compose_editor.py`, a tkinter layered canvas) is a thin controller
over it and is judged by the human panel, not asserted.

**Artifact:** a scene an artist actually composes on a real recorded pack —
seed → rank → lock → recompute over the background adjacency (object layer)
and inside a sprite Y band (floor-sharing shapes) — exported as a composed
`usrNNN` sheet, then promoted from `auto/` to `mep/`.

**How to run:**
1. Produce a compose-ready pack: record a real game through the F9 pipeline
   and run the bootstrap so the pack carries `textures/sheets/adjacency.json`
   (F9.17+; the bootstrap prints `no adjacency.json — re-run the bootstrap`
   on an older pack instead of silently recomputing).
2. `python3 scripts/compose_editor.py <pack folder>`
3. Exercise the human gestures: seed a cell the `objNNN` grouping supports
   and lock its strongest neighbour on the object layer; compose a floor band
   of the sprite layer; **export** a kept `usrNNN` sheet; save (the save
   dialog promotes an edited sheet from `auto/` to `mep/textures/sheets/`
   per ADR-0164 §4 and says so rather than writing derived `auto/` data).

**Pass:**
- No crash; selection, lock, recompute and export respond as the ADR
  describes.
- An exported composed sheet re-slices headless without error and its painted
  crops reproduce the composed cells (the same reproducibility the engine
  acceptance already verified on the Mega Man 3 recording).
- An edit saved lands in `mep/` and survives a re-run of the bootstrap.

## 2. F6.5 — the native OS file-picker step

**Why it stays human:** the prompt for a `user_supplied` dependency is the
OS's own `IStorageProvider` dialog — headless Avalonia has no picker to
drive, and a faked provider would assert the fake (recorded in the
automation plan's rejected suggestions).

**How to run:** follow **Part B** of
`docs/validation/f65-install-acceptance-checklist.md` (the user-supplied
dependency, seeded catalog). The specific residue that runbook covers is the
real dialog: a pending dep must open the native file picker, accept a file
dropped into `.cache/downloads`, verify it by sha256, and install the audio.

**Pass:** the OS picker opens; a dropped file validates and installs
(`mep/audio/` present, `InstallMepRecipe returned success`); a wrong-named
but hash-correct file is accepted (sha256 match, not name).

## 3. ExtractAudio button (ADR-0135 point 7 — wiring shipped 2026-08-29)

**Why it stays human:** the headless end-to-end already passes (shortcut →
detached spawn with the `SaveFolder` passed through); the only residue is a
click on a real display.

**How to run:** open the HD Pack builder on a NES game and click the
**Audio.png** button (`btnExtractAudio`, NES-gated via `IsExtractAudioEnabled`).

**Pass:** the button responds; the log shows the `ExtractAudioHdPack`
shortcut handled; the detached tool writes the extracted audio and its log
to the pack's `auto/audio/` (relocation happens after the recorder's
destructor, so check after the run, not at `Stop()`).

## 4. Input tester with a physical pad (I.0–I.3)

**Why it stays human:** the host-free logic is unit-tested
(`GamepadDiagnosticsTests`, `PerDeviceDeadzoneTests`); the enumeration,
rumble, live highlight and feel need a real controller the machine exposes.

**How to run:** connect a pad, open **Settings → Input → Test** and check,
per pad: name / backend / `PadN` / VID:PID, live buttons and axes under the
mapping key names, the **Rumble** pulse (300 ms), the deadzone ring + drift
warning, the **circularity** readout (Excellent/Good/Fair/Poor over ≥48
samples), and the per-device deadzone toggle (0–4). Then open the mapping
window and confirm the bound button **highlights live** as you press (I.2).

**Pass:** the pad enumerates with its backend; presses move the right
bindings; rumble fires; a clean stick circle reads Excellent; the highlight
follows presses.

**Known hardware-only leftovers** (not code gaps, no action unless you have
the hardware): per-device VID:PID binding, MBC7 / GBA tilt, Linux
`UpdateDevices`, macOS `extendedGamepad`.

## 5. Subjective audio pass (human ears)

**Why it stays human:** timbre and "is the SFX audible over the replaced
track" are judgements; the *regression* halves are already Blocos I, K, L.

**How to run:** with a pack whose audio is replaced and a game that plays
SFX over it, listen for:
- F5.4g Block B — timbre quality of the replaced track;
- Block C item 9 — SFX during an OGG remains audible end-to-end;
- P.5 — the "Applied …" toast is not a noise (the toast's *presence* is
  asserted by ADR-0167; its pleasantness is not).

**Pass:** subjective — record a per-pack verdict.

## Sign-off

| Item | Verdict (PASS / FAIL / note) | Date |
|---|---|---|
| 1. Composition editor GUI (F9.18) | | |
| 2. F6.5 native file-picker step | | |
| 3. ExtractAudio button click | | |
| 4. Input tester with physical pad (I.0–I.3) | | |
| 5. Subjective audio pass | | |

## Where a failure goes

- A **reproducible bug** (crash, wrong pixels, wrong pad mapping, audio not
  relocated) → open a bug with `scripts/report-bug.sh` and record the
  repro here.
- A **product decision** surfaced by the panel (compose UX, audio policy,
  a pad behaviour) → an ADR, not a bug.
- A compose *engine* defect → reproduce it headless first
  (`test_compose_engine.py`); the GUI is a thin controller and should never
  be the only place a defect shows.

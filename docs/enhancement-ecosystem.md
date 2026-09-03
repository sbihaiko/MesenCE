# MesenCE Community Enhancement Ecosystem

*Status: maintained front-door narrative. The consolidated, binding roadmap
(Part A: pack/core; Part B: player GUI) and its shipped record live in
[docs/roadmap/PRD-mesence-enhancement-ecosystem.md](roadmap/PRD-mesence-enhancement-ecosystem.md);
the open specs live in [docs/specs/](specs/). This page is the short
why/vision — where it drifts from the PRD or a spec, the PRD and the spec win.*

MesenCE is a platform for **extracting, authoring and consuming community
enhancement packs** — textures, music and synth presets — while keeping the
emulator itself legally clean. The thesis is proven: the relaunched
[SUPER ZSNES](https://www.zsnes.com/) built its whole product around per-game
curated enhancements (hand-drawn hi-res art, audio replacement, overclock),
each individually toggleable, with enhancement data kept free of copyrighted
content. MesenCE already ships the three foundations needed to do the same as
an open ecosystem:

| Foundation | Where | What it provides |
|---|---|---|
| NES HD Packs (HDNes format) | `Core/NES/HdPacks/` | Tile + OGG audio replacement, per-context conditions, and the **HD Pack Builder** (in-emulator tile recorder) |
| MSU-1 | not on `main` — `Core/SNES/` is an empty skeleton (no tracked files) | The open SNES streaming-audio standard, kept here as a design reference only (out of product scope, ADR-0041) |
| Enhanced Synth Engine | `Core/Shared/Audio/EnhancedSynthEngine.*` | A live tap that converts chip register state into note/voice abstractions — most of a MIDI exporter |

## Principles

1. **Ship the tool, never the content.** Extractors are legal (interoperability);
   their outputs stay on the user's machine. Extracted tiles and transcribed music are
   still copyrighted works (a MIDI of a game tune is a transcription of the
   composition, like sheet music — changing format never clears the musical work).
2. **The official channel carries only clean data:** synth presets, ROM-hash mappings,
   index manifests, tools, and original compositions with explicit licenses. One
   deliberate exception: short before/after demonstration excerpts and gameplay
   screenshots in `docs/media/` — the same de facto practice every emulator's
   documentation relies on — kept brief, credited where a community author is
   involved, and never full tracks or complete asset sets.
3. **Derivative content lives in the existing community hubs** (Zeldix for SNES audio
   packs, VGMusic for MIDI, romhack.ing / individual GitHub repos for texture packs) —
   the same separation bsnes keeps from the MSU-1 pack sites.
4. **The emulator is content-agnostic.** It consumes user-configurable index URLs; it
   never bundles, hosts, endorses, or embeds any P2P distribution of derivative
   content (inducement liability — *MGM v. Grokster*, 2005; the 2024 Yuzu settlement).

## Where the detail lives

- **Standards** (adopted + proposed), product consoles in scope, roadmap phases,
  and the shipped record: the PRD — Part A §1–§3. Don't maintain a second
  enumeration here.
- **Open specs** (CC0, RFC 2119, golden files): [`docs/specs/`](specs/) —
  `ESP-v1`, `MEP-v1`, `MEI-v1`, `MEP-recipe-v1`, `hires-gbsms-v1` (draft); see
  [`docs/specs/README.md`](specs/README.md) for the index.
- **Authoring a pack for submission:** [`docs/hd-pack-authoring.md`](hd-pack-authoring.md).
- **Community catalog:** [`docs/community-packs.md`](community-packs.md) (+ `.json`).

## Non-goals

- Hosting or distributing derivative content (extracted MIDIs, covers, redrawn
  third-party textures) in any project repository.
- Any embedded P2P/torrent sharing mechanism.
- Monetizing packs or the distribution channel.
- Compatibility with the closed SUPER ZSNES enhancement data format.

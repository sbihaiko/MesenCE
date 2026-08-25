# ADR-0040: MEP storage folder, zip handling and deterministic precedence

- Status: accepted
- Date: 2026-08-24
- Phase: F3.0 (MEP v1 host)
- Refines ADR-0005 (loose HD pack wins) and the storage note in
  `docs/roadmap/PRD` (memory: "pasta central por ROM, aceitar zip e diretório").

## Context
MEP-v1 §2 requires hosts to accept a `.zip` and a directory with identical
semantics; §5.1 requires a documented, deterministic order between multiple
matching packs and states that a loose `HdPacks/<rom>/` pack overrides any MEP
`textures` section. The existing loaders differ in zip support: NES
`HdPackLoader::LoadHdNesPack(string)` and `HdTilePack::LoadFromFolder` both
take a *directory*; only the NES `HdPacks/<rom>.zip` path reads zips directly.

## Decision
1. **Location.** `<home>/EnhancementPacks/`. Each pack is either a
   sub-directory `<name>/pack.json` or a loose `<name>.zip` in that folder.
   Nothing else is scanned (no recursion, no per-ROM sub-folders — packs are
   located by hash, not by ROM name).
2. **Zips are extracted, not streamed.** On scan, `<name>.zip` is extracted
   to `<home>/EnhancementPacks/.cache/<name>/` (re-extracted when the zip's
   size or mtime stamp stored in `.cache/<name>/.mep-source` differs). From
   then on a zip pack and a directory pack are the *same* thing for every
   consumer — one code path in the section loaders, and the NES/GB/SMS
   texture loaders keep their directory-only signatures. Zip entries are
   validated before extraction (spec §6): any entry whose normalised path
   contains `..`, starts with `/` or `\`, or contains a drive prefix aborts
   the whole pack ("zip-slip"); directory entries are created, everything
   else written verbatim.
3. **Matching.** A container is a candidate when its `pack.json` parses and
   validates (MepPack) and any `targets[].sha1` equals the ROM's No-Intro
   SHA-1 (ADR-0039), case-insensitive.
4. **Precedence.** Candidates are ordered by container name
   (directory name / zip base name), case-insensitive lexicographic, using
   the byte values of the lower-cased UTF-8 name. For each section, the
   **first** pack in that order providing the section wins; the others are
   kept in the list (for the F3.3 UI) but not applied. Users can force
   priority with a name prefix (`00-…`). This deliberately differs from the
   spec's *reference* suggestion ("installation order, newest wins"): mtime
   is not reproducible across machines/backups and cannot be shown in the UI
   without confusing users.
5. **Loose HD pack wins** (ADR-0005/§5.1): when `HdPacks/<rom>/hires.txt`
   (or `HdPacks/<rom>.zip`) exists, the MEP `textures` section is skipped
   with a log line saying so.

## Consequences
- Extraction costs disk (a copy of every zip) and a one-off delay on first
  scan; in exchange, no loader grows a second I/O backend and PNG/OGG files
  are served by the same `ifstream` paths already validated in F2.
- Deleting `EnhancementPacks/.cache/` is always safe (rebuilt on next scan).
- Precedence is stable and inspectable by looking at the folder.

## Alternatives
- Stream from zip via ZipReader in every section loader: three loaders to
  teach (NES/HdTilePack/OggMixer), plus MSU-1 later. Rejected for v1.
- "Newest wins" by mtime: non-deterministic across copies. Rejected.
- Per-ROM sub-folders like HdPacks/: contradicts hash-based identity.

# ADR-0038: Minimal strict JSON reader in Utilities/ (no third-party dependency)

- Status: accepted
- Date: 2026-08-24
- Phase: F3.0 (MEP v1 host)

## Context
`pack.json` (MEP-v1 §3) is the first JSON the C++ core has to parse; there is
no JSON parser anywhere in Core/ or Utilities/. The file is tiny (a handful of
strings, one array of targets, one object of sections) and the spec demands
strict JSON (MEP-v1 §2 rule 2) plus "unknown fields MUST be ignored" (§3.2).

## Decision
Add `Utilities/JsonReader.{h,cpp}`: a self-contained, strict RFC 8259 parser
(~250 lines) producing a `JsonValue` tree (null/bool/number/string/array/
object, object keys kept in document order). Any syntax error, trailing
garbage, control character in a string or unsupported escape makes the whole
document invalid (the pack is then rejected with a log line). No serializer,
no comments, no trailing commas, no NaN/Infinity. `\uXXXX` escapes (including
surrogate pairs) are decoded to UTF-8.

## Consequences
- Zero new dependencies; same compile model as the rest of Utilities/ (the
  repo already vendors miniz/kissfft but avoids large header-only libraries).
- The golden `docs/specs/golden/mep/pack.json` doubles as the parser's
  smoke test through the MEP loader.
- Numbers are parsed as `double`; MEP has no numeric fields today, so this is
  not a precision concern.

## Alternatives
- nlohmann/json (~25k lines header-only): far more than the use case needs,
  slows every TU that includes it, and adds a licence/upgrade surface.
- Hand-rolled ad-hoc scanning inside MepPack: brittle and not reusable;
  MEI (docs/specs/MEI-v1.md) is also JSON and will want the same reader.

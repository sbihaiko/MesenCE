# `audio` section of the example pack

This golden's target is a Game Boy game (`F1 Test Tone`). The `audio`
section for GB/SMS depends on the freeze of the
[`hires-gbsms-v1-draft.md`](../../../hires-gbsms-v1-draft.md) extension and
**is not yet applied by the MesenCE host** (ADR-0041 — in v1 only `nes`
receives audio, via a `hires.txt` with `<bgm>`/`<sfx>` tags pointing to OGG
files in this folder). The folder exists so the golden pack.json points to
a real path; when the extension freezes, content will go here without
changing the `pack.json`.

`hires.txt` here is a header-only placeholder (`<ver>`, `<system>gb`,
`<scale>`, no tags): `mep_lint.py` requires every declared `sections.*`
layer to resolve to a `hires.txt`, and the C++ golden test asserts all three
sections are declared, so the file keeps the canonical pack lint-green
without pretending GB audio is hosted (ADR-0136 Clarifications §3).

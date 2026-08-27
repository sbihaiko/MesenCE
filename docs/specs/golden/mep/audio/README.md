# `audio` section of the example pack

This golden's target is a Game Boy game (`F1 Test Tone`). The `audio`
section for GB/SMS depends on the freeze of the
[`hires-gbsms-v1-draft.md`](../../../hires-gbsms-v1-draft.md) extension and
**is not yet applied by the MesenCE host** (ADR-0041 — in v1 only `nes`
receives audio, via a `hires.txt` with `<bgm>`/`<sfx>` tags pointing to OGG
files in this folder). The folder exists so the golden pack.json points to
a real path; when the extension freezes, content will go here without
changing the `pack.json`.

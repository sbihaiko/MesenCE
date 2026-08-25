# Specs abertas do Ecossistema de Enhancement (MesenCE)

Specs previstas no PRD ([`docs/roadmap/PRD-ecossistema-enhancement-comunitario.md`](../roadmap/PRD-ecossistema-enhancement-comunitario.md), §4.2).
Todas licenciadas **CC0-1.0** — qualquer emulador ou ferramenta pode
implementá-las sem depender do MesenCE. Linguagem normativa RFC 2119,
versionamento semver, golden files canônicos em [`golden/`](golden/) e
validação automatizada via `python3 scripts/validate-specs.py` (raiz do repo).

| Spec | Arquivo | Status | O que define |
|---|---|---|---|
| **ESP v1** | [`ESP-v1.md`](ESP-v1.md) | estável | gramática e campos do preset do Enhanced Audio (`EnhancedAudioPresets.cfg`) |
| **MEP v1** | [`MEP-v1.md`](MEP-v1.md) | estável | envelope de pack (`pack.json` + hash No-Intro + seções textures/audio/synth) |
| **MEI v1** | [`MEI-v1.md`](MEI-v1.md) | estável | manifest federado de descoberta de packs + modelo de confiança |
| **hires.txt GB/SMS** | [`hires-gbsms-v1-draft.md`](hires-gbsms-v1-draft.md) | **draft** | extensão retrocompatível do formato HDNes para GB/SMS (pendente de revisão da comunidade — ADR-0004) |

**Limitações da implementação de referência (MesenCE, host MEP v1 — F3):**
a seção `audio` só é aplicada a `nes` (OGG via `hires.txt`); GB/SMS aguardam o
freeze da extensão hires-gbsms e SNES/MSU-1 está fora das fases do PRD
(ADR-0041). Packs `.zip` são extraídos para `EnhancementPacks/.cache/` na
primeira leitura; a precedência entre packs é a ordem lexicográfica
(case-insensitive) do nome do contêiner, o primeiro vence (ADR-0040) — um
HD Pack solto em `HdPacks/<rom>/` sempre vence a seção `textures` (§5.1).

Mudanças via issue/PR neste repositório; breaking change = bump de versão
maior da spec afetada.

Ferramentas relacionadas em `scripts/`: `headless_record.cpp` (captura
MIDI/VGM sem GUI, `make capture-tool`), `make_gb_test_rom.py` (ROM homebrew
determinística usada pelos goldens de hash), `gen_mep_test_pack.py` (packs
MEP de teste — dir/zip/negativos — para uma ROM) e `validate-specs.py`.

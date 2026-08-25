# Specs abertas do Ecossistema de Enhancement (MesenCE)

Specs previstas no PRD ([`docs/roadmap/PRD-ecossistema-enhancement-comunitario.md`](../roadmap/PRD-ecossistema-enhancement-comunitario.md), §4.2).
Todas licenciadas **CC0-1.0** — qualquer emulador ou ferramenta pode
implementá-las sem depender do MesenCE. Linguagem normativa RFC 2119,
versionamento semver, golden files canônicos em [`golden/`](golden/) e
validação automatizada via `python3 scripts/validate-specs.py` (raiz do repo).

| Spec | Arquivo | Status | O que define |
|---|---|---|---|
| **ESP v1** | [`ESP-v1.md`](ESP-v1.md) | estável | gramática e campos do preset do Enhanced Audio (`EnhancedAudioPresets.cfg`) |
| **MEP v1.1** | [`MEP-v1.md`](MEP-v1.md) | estável | envelope de pack (`pack.json` + hash No-Intro + seções textures/audio/synth); 1.1: `patches[]`, forma-pasta/pasta irmã sem `pack.json`, camada `auto/` |
| **MEI v1** | [`MEI-v1.md`](MEI-v1.md) | estável | manifest federado de descoberta de packs + modelo de confiança |
| **hires.txt GB/SMS** | [`hires-gbsms-v1-draft.md`](hires-gbsms-v1-draft.md) | **draft** | extensão retrocompatível do formato HDNes para GB/SMS (pendente de revisão da comunidade — ADR-0004) |

**Limitações da implementação de referência (MesenCE, host MEP v1 — F3):**
a seção `audio` só é aplicada a `nes` (OGG via `hires.txt`); GB/SMS aguardam o
freeze da extensão hires-gbsms e SNES/MSU-1 está fora das fases do PRD
(ADR-0041). Packs `.zip` são extraídos para `EnhancementPacks/.cache/` na
primeira leitura; a precedência entre packs é a ordem lexicográfica
(case-insensitive) do nome do contêiner, o primeiro vence (ADR-0040) — um
HD Pack solto em `HdPacks/<rom>/` vence a seção `textures` (§5.1), salvo a
pasta irmã da ROM (`<dir>/<Game>/`, §2.1 — F5.1/ADR-0049), que vence tudo.
`patches[]` e o hash normalizado ao tamanho do header iNES (ADR-0044) estão
implementados; o override "aplicar patch com hash divergente" fica em
*Enhancement Packs*. Linter offline: `python3 scripts/mep_lint.py <pasta|zip>`. Bootstrap (F5.2, comportamento de host, não da spec): com a opção ligada e nenhum pack de texturas aplicável, jogar grava os tiles em `<Game>/auto/textures/` (xBRZ 4×) ao lado da ROM e, no NES, a música em `<Game>/auto/audio/` (`fingerprints.json` + `midi/`; F5.3/ADR-0047 — `scripts/mep_render_audio.py` gera os `bgm/<id>.ogg`, tocados por reconhecimento das notas, sem patch). Telas estáticas viram `auto/textures/backgrounds/screenNNN.png` + `<background>` com âncoras `tileAtPosition` (F5.4a/ADR-0050); sob uma camada humana só os tiles do `auto/` são mesclados.

Mudanças via issue/PR neste repositório; breaking change = bump de versão
maior da spec afetada.

Ferramentas relacionadas em `scripts/`: `headless_record.cpp` (captura
MIDI/VGM sem GUI, `make capture-tool`), `make_gb_test_rom.py` (ROM homebrew
determinística usada pelos goldens de hash), `gen_mep_test_pack.py` (packs
MEP de teste — dir/zip/negativos — para uma ROM), `mep_lint.py` (validação offline de packs/hires.txt) e `validate-specs.py`.

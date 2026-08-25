# Plano de execução — Fase 3: Formato de pack unificado (MEP v1)

**Status:** em execução — F3.0 ✅ (ADR-0038…0042 em `.dev-squad/adr/`), F3.1 ✅ (núcleo validado headless em 2026-08-24: dir+zip casam em NES/GB, badhash ignorado, badjson/major/zip-slip rejeitados), F3.2 a seguir ·
**PRD:** [PRD-ecossistema-enhancement-comunitario.md](PRD-ecossistema-enhancement-comunitario.md) §Fase 3 ·
**Spec:** [MEP-v1.md](../specs/MEP-v1.md) (publicada) ·
**Processo:** resolver os ADRs da fase (F3.0) antes de qualquer código, como nas fases 1 e 2.

## Critério de sucesso (PRD)

> Um único `.zip` liga texturas + trilha OGG + preset de synth para um jogo,
> com cada peça desligável separadamente.

Alvo de validação: um jogo NES (ex.: Mega Man 3) — texturas hires.txt + BGM
OGG (via tags `<bgm>` do próprio hires.txt, já suportadas pelo `HdPackLoader`)
+ preset ESP, num só pack MEP, com toggles independentes por seção. OGG para
GB/SMS depende do freeze da extensão hires-gbsms (§3.4 do draft, em review na
issue #1) e fica explicitamente **fora** desta fase (ver ADR-0041 proposto).

## Estado do terreno (verificado no código em 2026-08-24)

| Ponto de integração | Situação |
|---|---|
| Parse de JSON no core C++ | **Não existe** parser JSON em Core/Utilities — decisão necessária (ADR-0038) |
| Hash No-Intro | **Não existe**: `Emulator::GetHash(Sha1)` hasheia o arquivo inteiro; `NesConsole::GetHash(Sha1Cheat)` só PRG. NES No-Intro = arquivo menos header iNES (16B) e menos trainer (512B, flags6 bit 2) — calculável direto do arquivo, sem console montado |
| Texturas NES | `HdPackLoader::LoadHdNesPack(string definitionFile, ...)` já aceita path arbitrário de hires.txt e lê de **zip** (ZipReader) — delegação trivial |
| Texturas GB/SMS | `HdTilePack::LoadFromFolder(folder, ...)` já existe (criado na consolidação pós-F2) — só diretório, sem zip |
| Áudio OGG NES | tags `<bgm>`/`<sfx>` no hires.txt via `OggMixer` — já funciona |
| Áudio OGG GB/SMS | loader v1 ignora as tags (log "not supported yet") — fora da F3 |
| MSU-1 | existe só no SNES (`Core/SNES/Coprocessors/MSU1`) — fora da F3 (SNES não é alvo das fases) |
| Preset ESP | `EnhancedSynthPreset` lê `EnhancedAudioPresets.cfg` do home no reset/load — precisa de camada de override intermediária (defaults < pack < arquivo do usuário, spec MEP §5.3) |
| Zip | `Utilities/ZipReader` (miniz) disponível |
| Validação de spec | `scripts/validate-specs.py` já valida o golden `pack.json` |

## F3.0 — ADRs da fase (bloqueia o resto) ✅

1. **ADR-0038 — Parser JSON do core.** Não há parser no core. Opções:
   (a) parser mínimo próprio em `Utilities/` (~200 linhas, JSON estrito,
   objetos/arrays/strings/números/bool/null, erro = pack inválido);
   (b) lib header-only (nlohmann, ~25k linhas). Recomendação: (a) — o repo
   evita dependências, o pack.json é pequeno e o golden file vira teste.
2. **ADR-0039 — Hash No-Intro por console.** Novo `HashType::Sha1NoIntro`
   resolvido pelo host a partir do *arquivo* (tabela da spec MEP §4): NES
   pula header/trainer; GB/GBC/SMS/GG/SG/Coleco = arquivo inteiro; SNES pula
   copier header. Onde vive: função estática no manager MEP (não exige
   console montado — o matching roda antes do `console->LoadRom`).
3. **ADR-0040 — Armazenamento, descoberta e precedência.** Pasta central
   `EnhancementPacks/` no home; cada pack = subdiretório `<nome>/pack.json`
   **ou** `<nome>.zip` solto. Matching por `targets[].sha1` (case-insensitive).
   Precedência (spec §5.1): HD Pack solto em `HdPacks/<rom>/` **vence** a seção
   textures de qualquer MEP; entre MEPs, definir e documentar a ordem
   determinística (proposta: ordem lexicográfica case-insensitive do nome do
   contêiner — reprodutível entre máquinas, diferente da sugestão "ordem de
   instalação" da spec, que depende de mtime). Zip para GB/SMS: leitura direta
   via ZipReader no `HdTilePack` **ou** extração transparente para cache na
   instalação — decidir aqui.
4. **ADR-0041 — Escopo de áudio do v1.** Seção `audio` no v1 = OGG por
   hires.txt (NES). GB/SMS adiado até o freeze da extensão draft; MSU-1
   adiado (SNES fora das fases). Documentar no README/spec como limitação de
   host (a spec MEP permanece como está — a limitação é da implementação).
5. **ADR-0042 — Camada de override ESP.** Ordem de aplicação: defaults
   embutidos → preset do pack (seção `synth`) → `EnhancedAudioPresets.cfg`
   do usuário (usuário sempre ganha, spec §5.3). Mecanismo: passo extra em
   `EnhancedSynthPreset::LoadOverrides` com path/conteúdo vindos do manager.

## F3.1 — Núcleo: parse, matching e carregamento por hash ✅

**Entrega:** abrir uma ROM carrega automaticamente os packs MEP aplicáveis.

- `Utilities/JsonReader.{h,cpp}` (novo, conforme ADR-0038) + uso no golden.
- `Core/Shared/EnhancementPacks/MepPack.{h,cpp}`: parse/validação do
  `pack.json` (campos MUST, semver, formatos de hash, rejeição de `..`/path
  absoluto — zip-slip, spec §2.3/§6; campos desconhecidos ignorados §3.2;
  major desconhecido de `mep` recusado §3.1).
- `Core/Shared/EnhancementPacks/MepPackManager.{h,cpp}`: scan da pasta
  central (diretórios + zips), matching por sha1 No-Intro (ADR-0039),
  lista ordenada por precedência (ADR-0040), API para os consoles:
  `GetTexturesPath(system)`, `GetSynthPreset()`, flags de seção.
- `Emulator::LoadRom`: instanciar/rescanear o manager **antes** de
  `console->LoadRom` (os consoles carregam HD packs dentro do LoadRom deles).
- vcxproj/filters + **limpar todos os `.o`** (SettingTypes.h e headers novos —
  makefile sem header deps; sintoma de esquecimento: heap corruption).
- **Validação:** teste headless com pack de diretório e pack zip (gerados por
  script python novo `scripts/gen_mep_test_pack.py`), matching por hash
  correto (NES com/sem header iNES), pack inválido rejeitado com log.
  **Feito:** `scripts/headless_record <rom> 1 <prefixo> screenshot log` com os
  packs gerados em `<prefixo-dir>/mesen-home/EnhancementPacks/` — o log do
  core (`[MEP] ...`, novo flag `log` do harness) mostra matches e rejeições.
  Nota: o export `GetLog` já existia; F3.3 adiciona `GetMepPackList`.

## F3.2 — Delegação de seções (textures + synth + audio-NES)

**Entrega:** o conteúdo do pack chega aos subsistemas existentes.

- **textures/NES:** em `NesConsole::LoadRom` (linha ~256), quando não houver
  `HdPacks/<rom>/hires.txt` solto (precedência!), pedir ao manager o path e
  chamar `HdPackLoader::LoadHdNesPack(definitionFile, ...)`.
- **textures/GB/SMS:** idem em `Gameboy::LoadRom` / `SmsConsole::LoadRom`,
  via `HdTilePack::LoadFromFolder` (com a resposta do ADR-0040 para zip).
- **synth:** aplicar ADR-0042 nos três engines (NES/GB/SMS EnhancedSynth).
- **audio/NES:** OGG entra pelas tags do hires.txt da seção textures (ou de
  um hires.txt de áudio-somente na seção audio — forma final no ADR-0041).
- **Validação headless:** pack MEP com hires GB neutro → screenshot 1:1
  (reusa o harness `screenshot`); pack com preset ESP → capturar MIDI e
  verificar mudança de programa GM vs default; precedência: HdPacks solto +
  MEP simultâneos → o solto vence.

## F3.3 — Toggles granulares + UI (F3.2 do PRD)

**Entrega:** cada seção desligável na UI; packs visíveis e gerenciáveis.

- `SettingTypes.h`: `EnhancementPackConfig` (EnableMepPacks global +
  EnableTextures/EnableAudio/EnableSynth por seção; desabilitar pack
  individual por nome persiste em config). Campos novos **no fim** das
  structs + espelho C# interop (`[MarshalAs(I1)]`, append no fim).
- UI: janela "Enhancement Packs" (lista packs aplicáveis à ROM aberta,
  checkbox por pack e por seção, botão Install que extrai zip para a pasta
  central — reusar o fluxo do `InstallHdPack`); item de menu visível para
  NES/GB/SMS. Mudança de toggle = reload do subsistema afetado
  (`ForceFilterUpdate` para texturas; reset para synth).
- InteropDLL: exports `GetMepPackList`/`SetMepPackEnabled` (ou equivalente).
- **Validação:** dotnet build 0 warnings; toggles refletidos headless via
  config (harness pode setar EnhancementPackConfig pelo struct real).

## F3.4 — Fecho da fase

- Golden/exemplo: pack MEP de demonstração em `docs/specs/golden/mep/`
  completo (já existe o pack.json; adicionar árvore de exemplo mínima).
- E2E do critério de sucesso: um zip com textures + `<bgm>` OGG + preset ESP
  para um jogo NES, cada seção desligável — validado headless + GUI manual.
- Regressões F1/F2 (suite headless existente), clang-format, DOX pass,
  README (Fase 3 ✅), atualização da memória de projeto.

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Ordem de init no `Emulator::LoadRom` (manager precisa do hash antes do console) | hash No-Intro calculado do arquivo (ADR-0039), sem depender do console montado |
| `.o` velho após mudar SettingTypes.h/headers novos | limpar `Core/`, `Utilities/`, `InteropDLL/` antes de todo `make core` da fase |
| Interop C#↔C++ desalinhado (structs de config) | campos sempre apendados no fim; harness inclui `SettingTypes.h` real (drift quebra em compile) |
| Zip-slip / pack malicioso | validação central no MepPack (spec §6), teste negativo dedicado |
| Toggle em runtime destabilizar console | v1: toggles aplicam no próximo load/reset (igual ao EnableHdPacks atual), exceto texturas (ForceFilterUpdate é seguro) |

## Sequência sugerida de sessões

1. **Sessão A:** F3.0 (ADRs 0038–0042) + F3.1 (núcleo headless-validado).
2. **Sessão B:** F3.2 (delegações + validação de precedência).
3. **Sessão C:** F3.3 (config/interop/UI) + F3.4 (fecho, E2E, README).

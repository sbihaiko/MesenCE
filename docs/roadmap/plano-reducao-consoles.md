# Plano — produto do fork: `main` + consoles reduzidos

**Status:** concluída (2026-08-26) — `main` é a default; NES, GB/GBC/GBS, SMS/GG/SG-1000 e GBA restam. SNES (incl. SGB), PC Engine, WonderSwan e ColecoVision estão fora. ·
**PRD:** [PRD-ecossistema-enhancement-comunitario.md](PRD-ecossistema-enhancement-comunitario.md) (SNES já estava fora das fases) ·
**Fora de spec:** corte de emulação, não de formato de pack.

Este fork não tem fluxo de PR para [nesdev-org/MesenCE](https://github.com/nesdev-org/MesenCE) (`CONTRIBUTING.md`). Depois de cortar SNES / PC Engine / WonderSwan / ColecoVision, um `git merge upstream/master` (ou o botão **Sync fork** do GitHub) reintroduz os consoles. Por isso a troca da branch principal vem **antes** de apagar código.

## Critério de sucesso

O default do `sbihaiko/MesenCE` é `main`. Nela o emulador carrega só:

- NES (iNES / UNIF / FDS / NSF / VS)
- Game Boy / GBC / GBS (handheld; **sem** Super Game Boy)
- Master System / Game Gear / SG-1000
- GBA

ColecoVision, SNES (emulação: SGB, MSU-1, coprocessors), PC Engine (incl. CD) e WonderSwan não carregam ROM, não aparecem no file dialog e não têm tela de settings de sistema. CI (clang-format, unit tests, Run tests, Build) verde em `main`. Badges e nightly.link apontam para `main`.

**Input SNES fica.** Pad, mouse e NTT Data Keypad (`ControllerType::SnesController` e afins) continuam como dispositivos de porta nos corconsoleses vivos — no NES o dropdown já os lista; um USB/Bluetooth com layout SNES mapeia no host como qualquer outro pad. Não voltar o core, o Super Scope, Multitap, rumble/BlueRetro (dependiam de `SnesConsole`), nem `.sfc`/`.spc`.

## Decisão de branch — sim, mudar a default

| Branch | Papel |
|---|---|
| **`main`** | Default do GitHub. Produto. Todo o trabalho novo. Cortes de core acontecem aqui. |
| **`master`** | Congelada no último snapshot *full-console* (estado atual). Histórico + ponto de comparação. Sem commits novos. |
| **`upstream`** (opcional, origin) | Fast-forward **somente** de `nesdev-org/MesenCE/master`. Nunca mergear de uma vez em `main`. Cherry-pick de bugfix, arquivo a arquivo. |

Não chamar o produto de `master`: o hábito `merge upstream/master` e o **Sync fork** do GitHub (sincroniza a default do fork com a default do parent) recolocam SNES/PCE/WS no tree.

Nome `main` (não `community`): é o default que o GitHub, o `nightly.link` e o `actions/checkout` esperam; o README já explica que isto é o fork de enhancement.

**Não desforkar agora.** O parent continua visível. Documentar em `CONTRIBUTING.md`: nunca usar Sync fork. Desforkar (sair da fork network) fica como follow-up se o Sync fork virar acidente real.

### Passos (F0) — branch, sem apagar core

1. A partir do `master` atual: `git branch main && git push -u origin main`.
2. GitHub: default branch → `main` (`gh repo edit sbihaiko/MesenCE --default-branch main`).
3. CI: `clang-format-check.yml` hoje dispara só em `push` para `master` — passar a `main`. Os outros workflows já são `on: [push, pull_request]`.
4. README: badges `branch%3Amaster` e URLs `nightly.link/.../master/` → `main`.
5. Proteger `master` contra push (settings do GitHub) ou simplesmente parar de commitar nela.
6. Feature branches abertas (`feature/enhanced-audio-*`, `feature/hdpack-*`, etc.): históricas; trabalho novo sai de `main`.

## O que fica / o que sai

Fica o host (`Core/Shared/`, debugger shell, netplay, MEP, HD packs, Enhanced Synth) e os quatro cores acima. SMS **não** é Coleco: `SmsConsole` tem `SmsModel::{Sms, GameGear, Sg, ColecoVision}` — Coleco é uma fatia (BIOS + portas + controller). SG-1000 fica.

SNES é o único acoplamento com um core que fica: Super Game Boy (`BaseCartridge` instancia `Gameboy(..., true)`; `GbPpu` / `GbControlManager` incluem `SuperGameboy.h`). Cortar SNES exige limpar esses ganchos no GB, não apagar o GB.

### Enums — não renumerar

`ConsoleType` já tem valores explícitos (`Snes=0`, `Gameboy=1`, `Nes=2`, `PcEngine=3`, `Sms=4`, `Gba=5`, `Ws=6`). Apagar nomes sem os números explícitos nos que restam quebra settings/savestate dos cores vivos.

`CpuType` hoje é sequencial (`Gameboy=7`, `Nes=8`, `Sms=10`, `Gba=11`). **Atribuir valores explícitos iguais aos atuais** nos que restam. Buracos (0–6 SNES/coprocessors, 9 PCE, 12 WS) não se reutilizam. O mesmo para `MemoryType` / `DebuggerFlags` / `RomFormat` / `FirmwareType`: ou enumerant morto com comentário, ou valor explícito estável. Nunca compactar.

## Cortes — um PR por fatia, nesta ordem

Cada PR na `main`. Verde: compile (pelo menos uma plataforma), `clang-format`, `dotnet test UI.Tests`, `make unit-tests` / `core-unit-tests` se existirem no tree. Não misturar fatias.

### F1 — ColecoVision (barato)

Não muda `ConsoleType`. `SmsModel::ColecoVision` some; `.col` deixa de carregar.

- Core: `SMS/Input/ColecoVisionController.h`, ramo `.col` em `SmsConsole::LoadRom`, `FirmwareHelper::LoadColecoVisionBios`, `RomFormat::ColecoVision`.
- Interop: `SetCvConfig`.
- UI: `CvConfig*`, `CvConfigView*`, `CvInputConfigViewModel`.
- Scripts: `SetCvConfig` em `headless_record.cpp`.
- Docs: README (Enhanced Audio “SMS-family” deixa de citar Coleco).

SMS / GG / SG-1000 e o synth SMS continuam.

### F2 — WonderSwan

Pasta isolada. Fora de `Core/WS/` só `Emulator.cpp`, `Debugger.cpp` e `ExpressionEvaluator.Ws.cpp`.

- Apagar `Core/WS/` (~23 cpp, 55 entradas no `Core.vcxproj`).
- Debugger: includes/switches `CpuType::Ws` em `Debugger.cpp`, `DebugUtilities.h`, `Disassembler.cpp`, `MemoryDumper.cpp`, `ExpressionEvaluator.Ws.cpp`.
- Interop: `SetWsConfig`, `WsState`.
- UI: `WsConfig*`, `Ws*View*`, `WsDebuggerConfig`, `WsEventViewer*`, `WsStatusView*`, `WsRegisterViewer`, `WsDocumentation.json`, `WsIcon.png`.
- File dialog: `*.ws` / `*.wsc`.

### F3 — PC Engine

Core próprio (HuC6280, VDC/VCE, CD em `PCE/CdRom/`). Não compartilha CPU de runtime com o NES; só `Base6502Assembler<PceAddrMode>` no debugger.

- Apagar `Core/PCE/` (~27 cpp, 61 entradas no vcxproj).
- Debugger: `PceDebugger`, `ExpressionEvaluator.Pce.cpp`, `Base6502Assembler` template PCE (o de NES fica).
- Interop: `SetPcEngineConfig`, `PceState`.
- UI: `Pce*` / `PcEngine*` (config, input Avenue Pad, debugger, `Pceas*` importers, `CheatDb` se houver PCE).
- File dialog: `*.pce` / CD.

### F4 — SNES + SGB (o grande)

- Apagar emulação SNES (`SnesConsole`, PPU/APU, coprocessors SA-1, GSU, CX4, DSP, MSU-1, BS-X, ST018, SGB, SPC7110, SDD1, OBC1, Sufami). **Não** apagar o pad SNES: `SnesController` / `SnesMouse` / `SnesNttDataKeypad` passam a `Core/Shared/Input/` para o NES e o `ControllerHub`.
- `Emulator.cpp`: tirar `TryLoadRom<SnesConsole>` e o include.
- Debugger: `SnesDebugger` e os `CpuType::{Snes,Spc,NecDsp,Sa1,Gsu,Cx4,St018}` nos switches de `Debugger.cpp` / `DebugUtilities.h` / disassembler / memory dumper / `ExpressionEvaluator.Snes.cpp` (e Cx4/Gsu/Spc/St018 se existirem).
- **GB:** remover `SuperGameboy.h`, `IsSgb()` / `GetSgb()` / `RunSgb` / `GameboyModel::SuperGameboy` / `AutoFavorSgb` / firmware SGB. GB handheld permanece.
- Interop: `SetSnesConfig`, `SnesState`, Save SPC.
- UI de sistema: settings SNES, debugger SPC/GSU/SA-1, `SaveSpcFile*`, `CheatDb.Snes.json`, ícone de console. **Fica** `SnesControllerView` / `SnesNttDataKeypadControllerView` (mapping do pad).
- File dialog: `*.sfc` / `*.smc` / `*.spc`.

### F5 — docs e contrato do fork

- `CONTRIBUTING.md`: deixar de prometer “merges stay cheap” no sentido de merge wholesale; estilo clang-format/dotnet format **continua** (cherry-picks). Proibir Sync fork.
- README: lista de sistemas = os quatro que restam; Enhanced Audio sem Coleco/SGB.
- Este plano → `Status: concluída` quando o F4 estiver verde na `main`.
- DOX: `docs/AGENTS.md` já aponta para este arquivo; se o corte mudar ownership de `Core/`, atualizar o índice raiz.

## Superfície compartilhada (todo PR mexe nisto, no pedaço da fatia)

Não é “apagar a pasta e pronto”:

| Lugar | O que cortar por fatia |
|---|---|
| `Emulator.cpp` `TryLoadRom<T>` | Snes / Pce / Ws (Coleco não) |
| `Core.vcxproj` + `.filters` | entradas `SNES\` `PCE\` `WS\` + Coleco header |
| `InteropDLL/*ApiWrapper.cpp` | `SetSnesConfig` / `SetPcEngineConfig` / `SetWsConfig` / `SetCvConfig` |
| `UI/Interop/ConfigApi.cs` + `ConsoleTypeExtensions.cs` + `CpuTypeExtensions.cs` + `FirmwareTypeExtensions.cs` | cases mortos |
| `FileDialogHelper.cs` | extensões |
| `EmuSettings` / `SettingTypes.h` | structs `SnesConfig`, `PcEngineConfig`, `WsConfig`, `CvConfig` — podem ficar vazias uma versão se o serialize exigir; preferível tombstone estável |
| `Debugger.cpp` | o switch gigante por `CpuType` |

## Fora de escopo

- Não cortar GBA (core isolado, fora do synth/HD pack, mas barato comparado a SNES).
- Não cortar SG-1000.
- Não compactar enums.
- Não mergear `upstream` em `main`.
- Não reformatar o tree inteiro “já que estamos aqui”.

## Verificação por fatia

```
# depois de cada PR, do root:
grep -R "ColecoVision\|ConsoleType::Snes\|ConsoleType::PcEngine\|ConsoleType::Ws\|TryLoadRom<Snes\|TryLoadRom<Pce\|TryLoadRom<Ws" --include='*.cpp' --include='*.h' --include='*.cs' Core UI InteropDLL
# F1: ColecoVision deve zerar; os ConsoleType dos outros só zeram na fatia correspondente.
```

Mais: file dialog não lista a extensão cortada; um ROM NES + um GB + um SMS + um GBA ainda carregam; clang-format + unit tests + Run tests na `main`.

# Plano de execução — Testes unitários (sem reescrever MVVM)

**Status:** em execução (2026-08-25, revisado 2026-08-25) — Fase 0, Fase 1 e Fase 2 concluídas · próxima: Fase 3 ·
**Origem:** avaliação da UI Avalonia (já MVVM) vs. o bloqueio real (estáticos `EmuApi`/`ConfigManager`, RID `win-x64`, zero `*Test*.csproj`) ·
**Não substitui:** goldens headless (`headless_record`, `mep_lint.py`, `validate-specs.py`, `roles_probe`) nem o CI de ROM (`.github/workflows/tests.yml`).

## Contexto

A UI Avalonia **já é MVVM** (`CommunityToolkit.Mvvm`, `ViewModelBase`, ~93 arquivos `*ViewModel*.cs` / ~100 classes derivadas, Views/Windows com `DataContext`). O bloqueio não é o padrão — é o acoplamento:

- ViewModels chamam `EmuApi` / `DebugApi` / `ConfigManager` estáticos (P/Invoke para `MesenCore`).
- Construtores disparam I/O nativo (`EnhancementPacksViewModel()` chama `EmuApi.GetMepRomSha1()`).
- Tipos Avalonia (`Window`, `Dispatcher`) vazam para os VMs.
- `UI.csproj` é `WinExe` com `RuntimeIdentifier` default `win-x64` — um `ProjectReference` dele em testes quebra no macOS/Linux.
- Zero projeto de teste .NET. O CI atual (`.github/workflows/tests.yml`) só roda ROMs via `PGOHelper.exe` + repo `nesdev-org/MesenTests`.
- A validação de zip da janela **diverge do core**: `InstallPack` só proba `hires.txt`/`preset.cfg`; `MepPack::DetectConventionLayout` (`MepPack.cpp:58-65`) também aceita `audio/fingerprints.json` (ADR-0047). A extração da Fase 1 corrige isso em vez de congelar.
- O Core já tem o padrão certo: `ChannelRoleClassifier` é “console-agnostic and free of any emulator dependency so the headless validation harness can compile this same file”.

**Não** vamos colocar DI, Autofac, Avalonia.Headless, nem reescrever os 82 ViewModels.

## Objetivo

Fazer `dotnet test` (e um binário C++ pequeno) rodarem **sem emulador, sem Avalonia, sem ROM**, cobrindo a lógica que hoje vive presa em ViewModels / parsers.

## Fora de escopo

- Container de DI / interfaces para todo `EmuApi`.
- Testes de ViewModel que mockam o core nativo.
- Avalonia.Headless / testes de clique.
- Substituir goldens headless (`headless_record`, `mep_lint.py`, `validate-specs.py`, `roles_probe`, CI de ROM).
- Extração de `CheatManager` C++ (métodos privados que exigem `Emulator*`).

## Estratégia

Copiar o padrão do `ChannelRoleClassifier`: **módulo livre de host, compilado duas vezes**.

```
UI/Logic/*.cs  ──compila──►  UI.csproj (app)
               ──compila──►  UI.Tests.csproj (xunit)
```

`UI.Tests` **não** referencia `UI.csproj`. Só inclui `UI/Logic/**/*.cs`. Se alguém meter `using Avalonia` ou `EmuApi` em `Logic/`, o `dotnet test` deixa de compilar. Isso é o firewall.

Mesma ideia no C++ (fase 4): `ChannelRoleClassifier.cpp` compila sozinho com `-I . -I Core` (verificado); `MepPack.cpp` compila sozinho mas precisa linkar `Utilities/JsonReader.cpp`, `Utilities/FolderUtilities.cpp` e `Utilities/UTF8Util.cpp`. Um `scripts/core_unit_tests.cpp` liga só esses .cpp. **Não** usar `roles_probe` como modelo de link: `roles-probe: core` linka `MesenCore.dylib` porque roda o emulador.

Novo assembly `Mesen.Logic.dll` fica de reserva: só vale se `UI/Logic` crescer demais. Evita `TrimmerRootAssembly` + AOT + mais um projeto no sln híbrido.

## Contrato de `UI/Logic/`

Arquivos neste folder só podem usar BCL (e `System.IO.Compression`). Proibido:

- `Avalonia*`
- `EmuApi`, `ConfigApi`, `DebugApi`, `InputApi`, `RecordApi`
- `ConfigManager`
- `Window`, `Dispatcher`, `MainWindowViewModel.Instance`

Retornos de erro da UI: **IDs de mensagem** já existentes (`"InstallMepPackInvalidPack"`), não strings localizadas.

## Inventário (o que extraímos)

| Lógica | Onde está hoje | Extração | Tamanho | Prioridade |
|---|---|---|---|---|
| Validação zip MEP (camada + zip-slip) | `EnhancementPacksViewModel.InstallPack` L122–138 | `MepZipValidator.Validate(ZipArchive)` | ~25 LOC | P0 — único gate C# antes do `File.Copy`; corrige a camada `audio/fingerprints.json` |
| Parse TSV de `GetMepPackList` | `EnhancementPacksViewModel.Refresh` L45–68 | `MepPackListParser.Parse(string)` | ~40 LOC | P0 — formato documentado em `MepPackManager::GetPackListText` |
| Tipo de cheat NES/SNES | `CheatListWindowViewModel.GetCheatType` L129–141 | `CheatTypeDetector.FromCode(console, code)` | ~12 LOC | P1 — precisa mover enums para arquivo sem Avalonia |
| Lista `DisabledPacks` | `EnhancementPackConfig.SetPackEnabled` L42–49 | `DisabledPackList.Set(list, name, enabled)` | ~8 LOC | P2 — 3 linhas; vale mais documentar que `ApplyConfig` só desliga (nunca reabilita explicitamente, depende do default do core) |
| Path zip-slip C++ | `MepPack::NormalizeRelativePath` | sem extração; só ligar num binário de teste | ~40 LOC | P2 |
| Parse `pack.json` C++ | `MepPack::Parse` | idem; goldens em `docs/specs/golden/` | parser existente | P2 |
| Classificador lead/harmony/bass/SFX | `ChannelRoleClassifier` | já isolado; self-test sintético | já existe | P2 |
| Render synth | `EnhancedSynthEngine::Render` | fixture `Input` → samples finitos / silêncio em vol=0 | pesa `tsf.h` + `pch.h` | P3, depois do classificador |

**Não extrair:** `ConfigViewModel.IsDirty` (depende de `ConfigManager` + 12 configs), `JsonHelper.Clone` (precisa `MesenSerializerContext` + grafo de tipos da UI), `KeyCombination` (`InputApi.GetKeyName`), `ShortcutHandler`, debugger ViewModels.

O Core **já revalida** zip-slip na extração (`MepPackManager.cpp:406`, ADR-0040). O validador C# é o preflight da janela; os testes C# cobrem a UI, os testes C++ cobrem o host. Não unificar os dois parsers nesta leva — mas as regras **já divergem** (`NormalizeRelativePath` rejeita chars de controle `< 0x20` e ignora segmentos `.`; o C# não). Duas suítes com fixtures independentes não pegam divergência: os dois testes lêem o **mesmo arquivo de casos** `docs/specs/golden/mep/path-cases.txt` (uma linha por `path<TAB>ok|bad`). É uma fixture, não uma spec nova.

## Fases (PRs)

Cada fase é mergeável sozinha e deixa `dotnet format` / `make` verdes.

### Fase 0 — Harness C# (desbloqueia o resto)

**Arquivos**

- `UI.Tests/UI.Tests.csproj` — `net10.0`, xunit, `Microsoft.NET.Test.Sdk`, **sem** `RuntimeIdentifier`, **sem** `ProjectReference` à UI. `Nullable`/`LangVersion`/`ImplicitUsings` espelham `UI.csproj` (hoje só `Nullable enable`), senão `Logic/` compila com avisos diferentes nos dois lados.

  ```xml
  <Compile Include="..\UI\Logic\**\*.cs" Link="Logic\%(RecursiveDir)%(Filename)%(Extension)" />
  ```

- `UI.Tests/SanityTests.cs` — um `Fact` trivial para provar o pipeline.
- `UI/Logic/.gitkeep` (ou o primeiro helper vazio).
- `Mesen.sln` — **decidir antes de codar**, não depois: `build.yml`/`tests.yml` fazem `dotnet restore -r win-x64 -p:PublishAot=…` e `dotnet-format-check.yml` faz `dotnet restore` + `dotnet format --verify-no-changes`, todos no nível da solution, em Windows. Verificar localmente que um csproj sem RID sobrevive a `dotnet restore -r win-x64 -p:PublishAot=true Mesen.sln`. Se não sobreviver, **não** incluir no sln (o `unit-tests.yml` chama o csproj direto) ou incluir com `Build.0` desligado em `Release|x64`. Se incluir, o código de teste passa pelo `dotnet format` → obedecer o `.editorconfig` (tabs).
- `makefile` — alvo `unit-tests` que **não** depende de `core`; `DOTNET ?= dotnet` (no macOS o SDK pode estar em `~/.dotnet`):

  ```
  unit-tests:
  	$(DOTNET) test UI.Tests/UI.Tests.csproj --nologo
  ```

- `.github/workflows/unit-tests.yml` — job `ubuntu-latest` + `setup-dotnet 10.x` + `dotnet test`. Barato, em todo PR. **Não** mexer em `tests.yml` (ROM/PGOHelper).
- DOX: criar `UI/AGENTS.md`, `UI.Tests/AGENTS.md` e `.github/AGENTS.md` (o workflow novo mora lá); indexar no `AGENTS.md` raiz.

`UI.csproj` não precisa listar `Logic/` — o SDK já compila `**/*.cs`.

**Verificação:** `dotnet test UI.Tests/UI.Tests.csproj` em macOS/Linux/Windows sem SDL, sem `MesenCore`.

### Fase 1 — Extração MEP C# + testes (o gap F3.3)

**Novos tipos em `UI/Logic/`**

- `MepZipValidator`
  - `Validate(ZipArchive zip) -> string?` (`null` = ok; senão ID de mensagem)
  - Camada: `pack.json` **ou** `textures/hires.txt` / `audio/hires.txt` / **`audio/fingerprints.json`** / `synth/preset.cfg` **ou** os mesmos sob `auto/`. O `fingerprints.json` é a correção da divergência com o core (Contexto) — única mudança de comportamento da fase.
  - Zip-slip: path absoluto, `..`, `:`, e (alinhando ao C++) chars `< 0x20`; segmentos vazios/`.` ignorados. Casos vêm de `docs/specs/golden/mep/path-cases.txt`.
- `MepPackListParser`
  - Parse do TSV de `GetPackListText`: 8 colunas (`container, name, version, author, license, sections, enabled, origin`); linhas `!` → rejeitados; origin `2`/`1`/`0` → `sibling`/`zip`/`folder`.
  - Records imutáveis (`MepPackList`, `MepPackRow`). **Não** `ViewModelBase`. `Sections` sai como `string[]` bruto; o `Replace(",", ", ")` de exibição fica no VM.

**Rewire (comportamento idêntico)**

- `EnhancementPacksViewModel.Refresh` — `EmuApi.GetMepPackList()` continua no VM; o parse vai para o parser; o VM só copia rows → `MepPackEntry`.
- `InstallPack` — dialog + `File.Copy` ficam no VM; o bloco zip vai para o validador. Assinatura pode passar a `InstallPack(Window, Stream/path)` internamente chamando `Validate`.

**Testes (`UI.Tests/Mep/`)**

- Zip em `MemoryStream`: pack.json ok; só `auto/textures/hires.txt` ok; só `audio/fingerprints.json` ok; zip vazio / sem camada → `InstallMepPackInvalidPack`.
- Zip-slip: todos os casos de `path-cases.txt` (`../x`, `/abs`, `C:foo`, `a/../../b`, `a/\x01`, `./a/b` ok, `a//b` ok).
- Parser: linha válida; linha `!rejected`; linha curta ignorada; origin 0/1/2; enabled 0/1; várias seções `textures,audio`.

**Verificação:** os casos acima + janela Enhancement Packs ainda instala um zip válido (smoke manual ou o harness `mep-*` que já existe).

### Fase 2 — Cheats + lista de packs desligados

**Enums sem Avalonia**

- `ConsoleType` e `CheatType` hoje estão em `UI/Interop/EmuApi.cs`, que começa com `using Avalonia.Media.Imaging`. Mover os dois enums para `UI/Interop/InteropEnums.cs` (sem Avalonia, sem DllImport). `EmuApi.cs` e o resto da UI passam a usar o arquivo novo.
- `UI.Tests` também inclui `UI/Interop/InteropEnums.cs` (além de `Logic/`).

**Helpers**

- `CheatTypeDetector.FromCode(ConsoleType, string) -> CheatType` — NES `:` → custom, senão GameGenie; SNES `-` → GameGenie, senão PAR; outro console → mesmo `Exception` de hoje.
- `DisabledPackList.Set(List<string>, string container, bool enabled)` — remove case-insensitive; adiciona se `enabled == false`. `EnhancementPackConfig.SetPackEnabled` chama isso **e depois** `EmuApi.SetMepPackEnabled`.

**Testes:** códigos GG/PAR/custom NES e SNES; console não suportado (inclui `Gameboy`: o enum tem `GbGameGenie`/`GbGameShark`, mas o detector lança — caso documentado como comportamento atual, não como verdade); toggle da lista (duplicata, case, reabilitar).

### Fase 3 — Regra para ViewModels novos (sem retrofit)

Não reescrever VMs antigos. Documentar em `UI/AGENTS.md` e aplicar só no código que tocarmos:

1. Construtor não chama `EmuApi` / `ConfigManager` I/O. Dados entram por parâmetro (`Refresh(string packListText, string sha1, string sibling)`). Isso é injeção de dados, não mock de `EmuApi` — coerente com “Fora de escopo”.
2. Dialogos (`FileDialogHelper`, `MesenMsgBox`) ficam no `*.axaml.cs` — `EnhancementPacksWindow` já faz isso no OK/Install.
3. Lógica ramificada (parse, validar, classificar) nasce em `UI/Logic/` com teste no mesmo PR.
4. Sem `RelayCommand` obrigatório; code-behind fino + método no VM continua ok.

Opcional, só se um teste de orquestração se justificar: `EnhancementPacksViewModel` ganha ctor `(EnhancementPackConfig config)` + `Refresh` público alimentado pelo Window. Ainda **não** mockar `EmuApi`.

### Fase 4 — Testes C++ sem emulador (trilha paralela)

Depois do harness C#, não misturar no mesmo PR.

**Binário:** `scripts/core_unit_tests.cpp`, alvo `make core-unit-tests` **sem** pré-requisito `core`, fontes explícitas:

```
core-unit-tests:
	$(CXX) -std=c++17 -O2 -w -I . -I Core scripts/core_unit_tests.cpp \
	  Core/Shared/Audio/ChannelRoleClassifier.cpp \
	  Core/Shared/EnhancementPacks/MepPack.cpp \
	  Utilities/JsonReader.cpp Utilities/FolderUtilities.cpp Utilities/UTF8Util.cpp \
	  -o scripts/core_unit_tests && scripts/core_unit_tests
```

(Símbolos indefinidos de `MepPack.o` sozinho: `JsonReader::Parse`, `FolderUtilities::CombinePath` — verificado.)

**Bloco A — `ChannelRoleClassifier`** (já compilado por `roles_probe`):

- Canal silencioso → não SFX.
- Sweep rápido + amplitude → `CueSweep` / `IsSfx`.
- Porta lenta de 2 semitons (comentário Zelda no header) → música.
- Lead vs bass pela altura média após `kDecisionPeriodS`.

**Bloco B — `MepPack::NormalizeRelativePath` + `MepPack::Parse`:**

- Paths: ler `docs/specs/golden/mep/path-cases.txt` — o mesmo arquivo da Fase 1. Divergência C#/C++ aparece como falha em uma das suítes.
- `Parse` nos goldens de `docs/specs/golden/` (já usados por `validate-specs.py`). Falha controlada: JSON quebrado, root não-objeto.

`EnhancedSynthEngine::Render` fica para um PR seguinte: puxa `pch.h`, `MessageManager`, TinySoundFont. Primeiro teste útil seria “vol=0 → samples ~0, sem NaN”, mas o link é mais sujo.

**Não** extrair `CheatManager::ConvertFrom*` agora (privados, precisam `Emulator*`).

## CI e comandos

| Comando | O que cobre | Precisa core? |
|---|---|---|
| `make unit-tests` / `dotnet test UI.Tests` | lógica C# extraída | não |
| `make core-unit-tests` | classificador + path/parse MEP | não (`.cpp` isolados + 3 de `Utilities/`) |
| `python3 scripts/validate-specs.py` | specs/goldens | não |
| `python3 scripts/mep_lint.py` | pack no disco | não |
| `make capture-tool` + goldens | comportamento do host | sim |
| `.github/workflows/tests.yml` | ROMs upstream | sim, Windows |

O job novo `unit-tests.yml` é o que falta hoje: feedback em ~1 min em todo PR, inclusive macOS local.

## DOX

Hoje, dos 14 filhos listados no Child DOX Index raiz, **só `docs/AGENTS.md` existe** — o índice aponta para arquivos inexistentes (`Core/`, `UI/`, `.github/`, `scripts/`, …). O contrato DOX manda remover texto stale: ao criar os docs abaixo, marcar no índice raiz quais filhos ainda não têm AGENTS.md (ou removê-los até existirem).

- Criar `UI/AGENTS.md`: contrato de `Logic/`, regra de ViewModels (Fase 3), verificação `dotnet test` + `dotnet format`.
- Criar `UI.Tests/AGENTS.md`: propósito, “não referenciar UI.csproj”, como adicionar um teste.
- Criar `.github/AGENTS.md`: quais workflows existem e o que cada um cobre (`unit-tests.yml` vs `tests.yml`).
- Atualizar `AGENTS.md` raiz — Child DOX Index: `UI.Tests/`.
- Fase 4: `scripts/AGENTS.md` com o binário `core_unit_tests` (o índice raiz já aponta `scripts/`).

## Riscos

- **Dual-compile e tipos:** se um helper de `Logic/` precisar de um tipo da UI, o tipo tem de migrar para arquivo sem Avalonia (como os enums na Fase 2). Não “só dessa vez” incluir um `.cs` sujo no teste.
- **Duplicação C#/C++ do zip-slip:** aceitável; as regras ficam iguais via a fixture `path-cases.txt` compartilhada (Fases 1 e 4B). Sem ela, as suítes não detectam divergência.
- **AOT:** `Logic/` entra no assembly `Mesen` já listado em `TrimmerRootAssembly`. Sem DLL nova, sem mudança de trim.
- **sln + CI Windows:** ver Fase 0 — incluir no sln expõe o csproj a `dotnet restore -r win-x64 -p:PublishAot` e ao `dotnet format`. Verificar antes, não presumir.

## Ordem de execução sugerida

1. Fase 0 (meio dia) — harness verde.
2. Fase 1 (um dia) — o valor visível: MEP install/parse com testes.
3. Fase 2 (meio dia) — cheats + disabled list.
4. Fase 3 (junto com o próximo VM que tocarmos) — só documentação + o ctor de `EnhancementPacksViewModel` se estivermos no arquivo.
5. Fase 4 (um dia) — `core_unit_tests` classificador + path; synth depois.

Começar pela Fase 0 + Fase 1. É o desbloqueio real: a partir daí, lógica nova da UI nasce testada.

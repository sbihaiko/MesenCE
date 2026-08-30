# UI/

## Purpose

.NET (Avalonia) desktop UI application — windows, ViewModels, config, and
the native interop bridge to Core via `EmuApi`. `UI/Logic/` is a carved-out,
host-free subset consumed by `UI.Tests` (delivered in Phase 0/1 of the
now-completed unit-test plan — see git history for
`docs/roadmap/plano-testes-unitarios.md`). `UI/Services/` (F6.4b-2,
ADR-0138) is the opposite: host-aware orchestrators (network/File
I/O/`EmuApi` all allowed) that drive `UI/Logic/`'s host-free decision
types instead of reimplementing them.

## Ownership

The main UI/ViewModel codebase is owned by the application as a whole.
`UI/Logic/` specifically is owned by the completed unit-test
test-infrastructure effort: it exists so ViewModel parsing/validation logic
can be exercised by real xunit tests without Avalonia or the native
`MesenCore` library.

## Local Contracts

- **`UI/Logic/` is the host-free boundary** (ADR-0123): every file under
  `UI/Logic/*.cs`, and the dual-compiled `UI/Interop/InteropEnums.cs`, must
  stay free of `Avalonia` and `EmuApi` references — BCL (plus
  `System.IO.Compression` where needed) only. This is what lets
  `UI.Tests/UI.Tests.csproj` dual-compile the same files (via
  `<Compile Include>`, no `ProjectReference` to `UI.csproj`), so any
  accidental UI/native dependency breaks `dotnet test` immediately rather
  than only being caught in review (see `UI.Tests/AGENTS.md`). Since
  ADR-0123 aligned the test csproj with `UI/UI.csproj`'s compile strictness
  (no `ImplicitUsings`, `TreatWarningsAsErrors`), the dual-compile is the
  authoritative contract; `scripts/verify-ui-logic-firewall.sh` is the fast
  pre-check that names the offending file and dependency with a readable
  diagnostic before `dotnet test` fails opaquely (run by `make unit-tests`
  and the `ui-tests` CI job, and by `make doc-checks`).
- `UI/Services/*.cs` (ADR-0138 §37/§41, F6.4b-2) is the host-aware layer
  that drives the host-free `UI/Logic/Community*` decision classes -
  `HttpClient`/`Avalonia`/`EmuApi` are all allowed there, and
  `scripts/verify-ui-logic-firewall.sh` enforces the three-layer rule
  (ADR-0138 §53) in both directions: `UI/Logic/*.cs` must stay free of
  `Avalonia`/`EmuApi`/`HttpClient`/`Mesen.Services`, and `HttpClient` under
  `UI/` is confined to `UI/Services/*.cs` (plus the pre-existing
  `UpdatePromptViewModel`) — never Windows code-behind or ViewModels. Every
  community-pack GET goes through `CommunityPackDownloader` (§50).
- `UI/Logic/*.cs` types return plain, host-free records/DTOs — never
  `ViewModelBase`/`ObservableObject` subtypes. The owning ViewModel maps
  the result into its UI-facing type (e.g. `MepPackListEntry` →
  `MepPackEntry`).
- `MepPackListParser.Parse(string)` mirrors `EmuApi.GetMepPackList()`'s TSV
  contract exactly: newline-separated rows; a `!`-prefixed row is a
  rejection message (leading `!` stripped, accumulated into
  `MepPackListResult.RejectedInfo`); a tab-separated row maps to a
  `MepPackListEntry` (origin `2`/`1`/other → `sibling`/`zip`/`folder`);
  any row with fewer than 8 columns is silently ignored. Columns 9–10
  (P.3: `pack_id`/`content_id` from the container's `.mep-install.json`,
  empty for a stamp-less container) are optional — an 8-column row from an
  older core still parses. The `Sections` field is passed through raw — the
  `","` → `", "` display formatting stays in the ViewModel, not in this parser.
- `PackPreferenceResolver` (P.3, PRD Part B §5, ADR-0140/0141) is the
  host-free per-ROM choice resolver: `DerivePackId` (a candidate's
  `.mep-install.json` pack_id, else the `local:<container>` rule-4 fallback)
  and `Resolve` (the §5 content_id merge — a container duplicating another's
  content_id is the same pack, not a second entry — plus preference →
  winning container; lexicographic default when no preference or a stale
  one). It never touches `Avalonia`/`EmuApi`/config; the owning ViewModel
  reads the stored preference from `EnhancementPackConfig.RomPackPreference`
  (romSha1 → pack_id) and maps the result to its UI type. The core enforces
  the same decision per ROM via `MepPackManager::FindPreferredPack` (the
  preference is pushed at config-apply through `SetPreferredMepPack`/
  `ClearPreferredMepPacks`).
- `UiModeDefaultRule` (P.4, PRD Part B §6) is the host-free one-shot
  default for `PreferencesConfig.UiMode`: no settings.json at startup (the
  `Configuration.CreateConfig` path) → `Player`; an existing keyless
  settings.json (a pre-Player upgrade) keeps `Advanced` — which is also the
  property initializer value, so a missing key never degrades to Player. The
  key is written on first save. `UiMode` (enum: `Advanced`, `Player`) lives
  here too so both the UI project and UI.Tests share it.
- `UiModeShortcutPrecedence` (P.4, §6) resolves the Esc collision inside the
  shortcut config: the core fires every pressed shortcut, so in Player mode
  the `ToggleOverlay` shortcut owns its key(s) — `PreferencesConfig.ApplyConfig`
  suppresses any Pause/other binding on the same combination before pushing
  the shortcut list to the core. Advanced mode filters nothing; the overlay
  press is ignored by `ShortcutHandler` there. The enum `ToggleOverlay` is
  mirrored in the core (`Core/Shared/SettingTypes.h`) because the shortcut id
  crosses the interop boundary by value; the core also exempts it from the
  keyboard-block in `ShortcutKeyHandler::IsKeyPressed` so it stays reachable
  in keyboard games.
- `PlayerPackPicker` (P.5, §5) is the host-free decision for the Player pack
  picker: it opens only when 2+ distinct pack_ids exist (after the §5
  content_id merge — feed it `PackPreferenceResolver.Resolve`'s `Candidates`,
  never the raw entry list, or a dropped copy of an installed pack would
  count as a second choice), with no sibling-folder pack (that pack always
  wins, §4) and no effective stored per-ROM preference (silent apply).
  `DistinctPackIdCount` uses `DerivePackId` (ADR-0140 id, else
  `local:<container>`). The owning VM (`MainWindowViewModel`) injects the pack
  list + ROM sha1 (data-injected from the code-behind), builds the choices
  from the core's `GetPackListText` columns (name/author/version/licence/
  sections/origin already there), and `PickPlayerPack` stores the P.3
  preference then power-cycles (applied on the reload); `DismissPlayerPackPicker`
  stores nothing so the next launch asks again. The picker's order is
  community 👍 first (`CommunityPackInstallService.GetVotes(pack_id)`, from
  the last catalog fetch's MEI `votes`), then name — local-only packs (no
  catalog row, votes 0) fall back to name order.
- `CommunityCatalogUpdateDecision` (P.6, PRD Part B §3.6) is the
  host-free verdict for the F6.4b reinstall gate, replacing the old
  source.sha256 trigger (ADR-0138 §37) with the §3.6 content_id rule: an
  installed content_id differing from the catalog slot's → `Updated`
  (reinstall, unless the installed semver is newer → `NoDowngrade`, and
  hd-legacy has no semver so any diff updates); unchanged content_id →
  `UpToDate` or `WrapperOnly` (source sha256 changed, content same — no
  reinstall); fetch-returns-null (removed slot) → `RemovedFromCatalog`
  (keep the install, silent). `ReadStampFields` reads the `.mep-install.json`
  `content_id`/`source.sha256`; `CompareSemver` is numeric (no prerelease
  parsing). The coordinator (`CommunityPackInstallCoordinator.EvaluateGates`)
  feeds it the stamp + the installed version from `GetMepPackList` column 3
  (the stamp carries no version). The container name is unchanged by an
  update, so `DisabledPacks` and the per-section flags survive a reinstall.
  The catalog DTO's additive P.2 fields (`pack_id`/`content_id`/`votes`) are
  what carry the slot identity and 👍 into these decisions.

- **New ViewModels** (Phase 3 of the plan — applied opportunistically, "in
  the code we touch", not as a retrofit of existing VMs): a *new*
  ViewModel's constructor must not call `EmuApi`/`ConfigManager` I/O
  directly — data comes in via a method parameter (e.g.
  `Refresh(string packListText, string sha1, string sibling)`). This is
  data injection, not mocking `EmuApi` — no DI container, no
  `Avalonia.Headless`, no ViewModel/UI-click testing (all explicitly out of
  scope). Dialogs (`FileDialogHelper`, `MesenMsgBox`) stay in the
  `*.axaml.cs` code-behind, as `EnhancementPacksWindow` already does for
  OK/Install. Branching logic (parse, validate, classify) is born in
  `UI/Logic/` with a test in the same PR — never inlined in the VM. A
  `RelayCommand` is not required; a thin code-behind calling a plain VM
  method stays acceptable. `EnhancementPacksViewModel` itself is NOT
  retrofitted to this shape (it still calls `EmuApi`/`ConfigManager` from
  its constructor/`Refresh`) — only its parse/validate logic was extracted
  (Phase 1); a ctor taking `EnhancementPackConfig` + a Window-fed `Refresh`
  is optional future work, only if an orchestration test justifies it.

- **`UI.Tests.csproj` is NOT a member of `Mesen.sln`.** Including it would
  expose the project to the solution-level flows in
  `.github/workflows/build.yml`/`tests.yml`
  (`dotnet restore -r win-x64 -p:PublishAot=true Mesen.sln`, Windows-only)
  and `dotnet-format-check.yml`
  (`dotnet format --verify-no-changes` against the whole `.sln`). This
  actor's environment is macOS/Linux, so the plan's own risk item —
  verifying locally that a RID-less `UI.Tests.csproj` survives that
  win-x64/AOT restore — cannot be executed here; per the plan
  ("Phase 0 — Mesen.sln"), the fallback when that can't be confirmed is to
  keep the project OUT of the `.sln` and let `.github/workflows/unit-tests.yml`
  invoke `UI.Tests/UI.Tests.csproj` directly instead. That is the choice
  recorded here. Consequence: `UI.Tests` code is not gated by
  `dotnet-format-check.yml` — if it later joins the `.sln`, either confirm
  the win-x64/AOT restore survives first, or add it with `Build.0` disabled
  under `Release|x64`, and its code must then also satisfy the repo's
  `.editorconfig` (tabs) under `dotnet format`. See `.github/AGENTS.md` for
  how the CI split reflects this.

- **`UI/Services/*.cs`** (ADR-0138 §37/§38/§43/§45-§47, F6.4b-2) is
  deliberately outside the `UI/Logic` firewall: `scripts/verify-ui-logic-firewall.sh`
  only greps `UI/Logic/*.cs`, so `Avalonia`/`EmuApi`/`HttpClient`/`File` I/O
  are all fine in `UI/Services/`. Each class there is a thin, host-aware
  orchestrator over the host-free `UI/Logic/Community*` decision types —
  the network fetch, dep resolution/reinstall-gating/consent-gating and the
  `EmuApi.InstallMepRecipe` call itself all live here, never in
  `UI/Logic/`. `CommunityPackInstallCoordinator.Install()` is the seam: it
  takes the fetcher's already-verified output (matched catalog entry,
  primary artifact path, dep-id → path map) and is the only call site of
  `EmuApi.InstallMepRecipe` for this feature.

## Work Guidance

- New host-free helpers extracted from ViewModels go under `UI/Logic/`,
  paired with tests under the matching `UI.Tests/<Area>/` subfolder.
- **Public test-facing helpers** (ADR-0125, H6): `UI/Logic/` types may
  expose pure helpers publicly when a test needs to drive them directly
  (e.g. `MepZipValidator.IsSafePath` over `path-cases.txt`). Keep the
  production entry point the documented one; a `//` header line on the
  helper must name it as test-facing / reusable, so its public status reads
  as intentional. (Under the dual-compile, `internal` buys the tests no
  encapsulation — they compile the sources — so "public is fine if the
  header says why" is the cheapest consistent rule.)
- Never add an `Avalonia` or `EmuApi` reference to a file under
  `UI/Logic/` — if a helper needs a UI-side type (an enum, etc.), move
  that type out of its Avalonia-tainted file first (see Phase 2 of the plan
  for the `ConsoleType`/`CheatType` precedent).
- Apply the Phase 3 VM rule above (Local Contracts) when authoring a new
  ViewModel; do not retrofit it onto existing ones outside of files already
  being touched for another reason.

## Verification

- `dotnet test UI.Tests/UI.Tests.csproj --nologo`
- `./scripts/verify-ui-logic-firewall.sh`

## Child DOX Index

(none — `Logic/` and `Services/` are convention-only subfolders, not
separately governed subtrees)

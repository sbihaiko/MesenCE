#Welcome to what must be the most terrible makefile ever (but hey, it works)
#Both clang & gcc work fine - clang seems to output faster code
#.NET 10 (and its dev tools) must be installed to compile the UI.
#The emulation core also requires SDL2.
#Run "make" to build, "make run" to run

UNAME_S := $(shell uname -s)

MESENFLAGS=

#Use ccache when the developer has it installed. `build.yml` already gets it on
#every Linux and macOS job, by putting ccache's shims on PATH - a local build
#gets nothing unless the developer does that PATH surgery themselves, and pays
#the full ~150 s on every clean `make core` (ADR-0158 measured it). This closes
#that gap without requiring anything: when ccache is absent the variable is
#empty and the command lines are byte-for-byte what they were. `make CCACHE=`
#opts out; overriding CXX on the command line still wins, as it always did.
CCACHE := $(shell command -v ccache 2>/dev/null)

ifeq ($(USE_GCC),true)
	CXX := $(strip $(CCACHE) g++)
	CC := $(strip $(CCACHE) gcc)
	PROFILE_GEN_FLAG := -fprofile-generate
	PROFILE_USE_FLAG := -fprofile-use
else
	CXX := $(strip $(CCACHE) clang++)
	CC := $(strip $(CCACHE) clang)
	ifeq ($(UNAME_S),Linux)
		MESENFLAGS += -Werror -Wno-undefined-inline -Wno-return-type-c-linkage
	endif
	PROFILE_GEN_FLAG := -fprofile-instr-generate=$(CURDIR)/PGOHelper/pgo.profraw
	PROFILE_USE_FLAG := -fprofile-instr-use=$(CURDIR)/PGOHelper/pgo.profdata
endif

SDL2LIB := $(shell sdl2-config --libs)
SDL2INC := $(shell sdl2-config --cflags)

LINKCHECKUNRESOLVED := -Wl,-z,defs

LINKOPTIONS :=
MESENOS :=

ifeq ($(UNAME_S),Linux)
	MESENOS := linux
	SHAREDLIB := MesenCore.so
endif

ifeq ($(UNAME_S),Darwin)
	MESENOS := osx
	SHAREDLIB := MesenCore.dylib
	LTO := false
	STATICLINK := false
	LINKCHECKUNRESOLVED :=
endif

#Post-link fixup for the C++ harness binaries (roles-probe, capture-tool,
#spike-sound-driver): they link against InteropDLL/$(OBJFOLDER)/$(SHAREDLIB),
#whose install name is the bare file name, so the path has to be rewritten or
#the tool aborts at startup with a dyld "Library not loaded" error.
#
#Issue #268: the /usr/bin copies of install_name_tool and codesign are xcrun
#shims that fail the Xcode-licence check on a machine that only has the Command
#Line Tools, and the recipes used to swallow that with `2>/dev/null || true` -
#a green `make capture-tool` shipping a binary that crashes at load. Prefer the
#real CLT binaries, same as scripts/release_macos.sh already does, and let a
#failed rewrite fail the target. codesign stays best-effort (an ad-hoc
#signature is not required for the tool to run).
ifeq ($(UNAME_S),Darwin)
CLT_BIN := /Library/Developer/CommandLineTools/usr/bin
INSTALL_NAME_TOOL := $(shell test -x $(CLT_BIN)/install_name_tool && echo $(CLT_BIN)/install_name_tool || echo install_name_tool)
CODESIGN_ALLOCATE := $(shell test -x $(CLT_BIN)/codesign_allocate && echo $(CLT_BIN)/codesign_allocate)
ifneq ($(CODESIGN_ALLOCATE),)
export CODESIGN_ALLOCATE
endif

#$(call fixup_install_name,<binary>) - macOS only; a no-op everywhere else.
define fixup_install_name
	$(INSTALL_NAME_TOOL) -change $(SHAREDLIB) $(CURDIR)/InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) $(1)
	codesign -f -s - $(1) 2>/dev/null || true
endef
else
define fixup_install_name
	@:
endef
endif

MESENFLAGS += -m64

MACHINE := $(shell uname -m)
ifeq ($(MACHINE),x86_64)
	MESENPLATFORM := $(MESENOS)-x64
endif
ifneq ($(filter %86,$(MACHINE)),)
	MESENPLATFORM := $(MESENOS)-x64
endif
# TODO: this returns `aarch64` on one of my machines...
ifneq ($(filter arm%,$(MACHINE)),)
	MESENPLATFORM := $(MESENOS)-arm64
endif
ifeq ($(MACHINE),aarch64)
	MESENPLATFORM := $(MESENOS)-arm64
	ifeq ($(USE_GCC),true)
		#don't set -m64 on arm64 for gcc (unrecognized option)
		MESENFLAGS=
	endif
endif

DEBUG ?= 0

ifeq ($(DEBUG),0)
	MESENFLAGS += -O3
	ifneq ($(LTO),false)
		MESENFLAGS += -DHAVE_LTO
		ifneq ($(USE_GCC),true)
			MESENFLAGS += -flto=thin
		else
			MESENFLAGS += -flto=auto
		endif
	endif
else
	MESENFLAGS += -O0 -g
	# Note: if compiling with a sanitizer, you will likely need to `LD_PRELOAD` the library `libMesenCore.so` will be linked against.
	ifneq ($(SANITIZER),)
		ifeq ($(SANITIZER),address)
			# Currently, `-fsanitize=address` is not supported together with `-fsanitize=thread`
			MESENFLAGS += -fsanitize=address
		else ifeq ($(SANITIZER),thread)
			# Currently, `-fsanitize=address` is not supported together with `-fsanitize=thread`
			MESENFLAGS += -fsanitize=thread
		else
$(warning Unrecognised $$(SANITIZER) value: $(SANITIZER))
		endif
		# `-Wl,-z,defs` is incompatible with the sanitizers in a shared lib, unless the sanitizer libs are linked dynamically; hence `-shared-libsan` (not the default for Clang).
		# It seems impossible to link dynamically against two sanitizers at the same time, but that might be a Clang limitation.
		ifneq ($(USE_GCC),true)
			MESENFLAGS += -shared-libsan
		endif
	endif
endif

ifeq ($(PGO),profile)
	MESENFLAGS += ${PROFILE_GEN_FLAG}
endif

ifeq ($(PGO),optimize)
	MESENFLAGS += ${PROFILE_USE_FLAG}
endif

ifneq ($(STATICLINK),false)
	LINKOPTIONS += -static-libgcc -static-libstdc++ -Wl,--export-dynamic,--exclude-libs=libstdc++.a
endif

ifeq ($(MESENOS),osx)
	LINKOPTIONS += -framework Foundation -framework Cocoa -framework GameController -framework CoreHaptics -Wl,-rpath,/opt/local/lib
endif

CXXFLAGS = -fPIC -Wall --std=c++17 -MMD -MP $(MESENFLAGS) $(SDL2INC) -I $(realpath ./) -I $(realpath ./Core) -I $(realpath ./Utilities) -I $(realpath ./Sdl) -I $(realpath ./Linux) -I $(realpath ./MacOS)
OBJCXXFLAGS = $(CXXFLAGS)
CFLAGS = -fPIC -Wall -MMD -MP $(MESENFLAGS)

OBJFOLDER := obj.$(MESENPLATFORM)
DEBUGFOLDER := bin/$(MESENPLATFORM)/Debug
RELEASEFOLDER := bin/$(MESENPLATFORM)/Release
ifeq ($(DEBUG), 0)
	OUTFOLDER = $(RELEASEFOLDER)
	BUILD_TYPE := Release
	OPTIMIZEUI := -p:OptimizeUi=true
else
	OUTFOLDER = $(DEBUGFOLDER)
	BUILD_TYPE := Debug
	OPTIMIZEUI :=
endif


ifeq ($(USE_AOT),true)
	PUBLISHFLAGS ?=  -r $(MESENPLATFORM) -p:PublishSingleFile=false -p:PublishAot=true -p:SelfContained=true
else
	PUBLISHFLAGS ?=  -r $(MESENPLATFORM) --no-self-contained -p:PublishSingleFile=true
endif


CORESRC := $(shell find Core -name '*.cpp')
COREOBJ := $(CORESRC:.cpp=.o)

UTILSRC := $(shell find Utilities -name '*.cpp' -o -name '*.c')
UTILOBJ := $(addsuffix .o,$(basename $(UTILSRC)))

SDLSRC := $(shell find Sdl -name '*.cpp')
SDLOBJ := $(SDLSRC:.cpp=.o)

SEVENZIPSRC := $(shell find SevenZip -name '*.c')
SEVENZIPOBJ := $(SEVENZIPSRC:.c=.o)

LUASRC := $(shell find Lua -name '*.c')
LUAOBJ := $(LUASRC:.c=.o)

ifeq ($(MESENOS),linux)
	LINUXSRC := $(shell find Linux -name '*.cpp')
else
	LINUXSRC :=
endif
LINUXOBJ := $(LINUXSRC:.cpp=.o)

ifeq ($(MESENOS),osx)
	MACOSSRC := $(shell find MacOS -name '*.mm')
else
	MACOSSRC :=
endif
MACOSOBJ := $(MACOSSRC:.mm=.o)

DLLSRC := $(shell find InteropDLL -name '*.cpp')
DLLOBJ := $(DLLSRC:.cpp=.o)

ifeq ($(SYSTEM_LIBEVDEV), true)
	LIBEVDEVLIB := $(shell pkg-config --libs libevdev)
	LIBEVDEVINC := $(shell pkg-config --cflags libevdev)
else
	LIBEVDEVSRC := $(shell find Linux/libevdev -name '*.c')
	LIBEVDEVOBJ := $(LIBEVDEVSRC:.c=.o)
	LIBEVDEVINC := -I../
endif

ifeq ($(MESENOS),linux)
	X11LIB := -lX11
else
	X11LIB :=
endif

FSLIB := -lstdc++fs

ifeq ($(MESENOS),osx)
	LIBEVDEVOBJ := 
	LIBEVDEVINC := 
	LIBEVDEVSRC := 
	FSLIB := 
	ifeq ($(USE_AOT),true)
		PUBLISHFLAGS := -t:BundleApp -p:UseAppHost=true -p:RuntimeIdentifier=$(MESENPLATFORM) -p:PublishSingleFile=false -p:PublishAot=true -p:SelfContained=true
	else
		PUBLISHFLAGS := -t:BundleApp -p:UseAppHost=true -p:RuntimeIdentifier=$(MESENPLATFORM) -p:SelfContained=true -p:PublishSingleFile=false -p:PublishReadyToRun=false
	endif
endif

DOTNET ?= dotnet

all: ui

#Fase 0 of the now-completed unit-test plan (see git history for
#docs/roadmap/plano-testes-unitarios.md): host-free C# unit tests.
#Deliberately has no dependency on the `core`/`ui` targets - runs on any OS
#without SDL2 or the native MesenCore library.
#ADR-0123 (H5): the UI/Logic host-free firewall script runs first as a fast
#pre-check (names the offending file/dependency readably); the dual-compile
#is still the authoritative gate.
unit-tests:
	./scripts/verify-ui-logic-firewall.sh
	$(DOTNET) test UI.Tests/UI.Tests.csproj --nologo

#ADR-0150 (accepted 2026-09-03): headless Avalonia XAML-wiring tests, in a
#SEPARATE project that references UI/UI.csproj. UI.Tests stays host-free
#(ADR-0123); this is the opposite project and must never be merged into it.
#UI/UI.csproj hardcodes <RuntimeIdentifier>win-x64</RuntimeIdentifier>, so the
#test run must pass -p:RuntimeIdentifier=$(MESENPLATFORM) (a global property
#wins over the csproj assignment) and DefineConstants=TRACE (DEBUG off avoids
#App.Initialize() re-attaching Avalonia developer tools per test - the csproj's
#ProjectReference already adds it, but it is spelled out here too).
#The MainWindow-backed cases self-skip with an explicit reason when the native
#MesenCore is not built (NativeCore), which is always the case on CI (ADR-0131);
#run `make core` first to exercise all of them.
headless-ui-tests:
	$(DOTNET) test UI.HeadlessTests/UI.HeadlessTests.csproj -p:RuntimeIdentifier=$(MESENPLATFORM) --nologo

check-manifest:
	./scripts/check-core-manifest.sh

#ADR-0204: fetch every download link the README publishes and fail if one does
#not answer 200. Deliberately NOT part of doc-checks - doc-checks is hermetic
#and runs on every pull request, and this needs the network and a published
#release, so a GitHub outage would redden the gate for reasons the change did
#not cause. Run it after publishing the rolling pre-release.
check-download-links:
	./scripts/checks/verify_download_links.sh

#ADR-0137: repo-hygiene guardrails wired into one make target so CI fails
#the PR instead of relying on someone running these checks by hand.
#Depends on check-manifest (kept separate, not duplicated) then runs the
#orphaned shell checks in order, failing on the first non-zero exit.
#ADR-0138 §41: the three F6.4b-2 guardrails (host allow-list embed parity,
#Core stays HTTP-client-free, the fetcher never loads the allow-list from
#the filesystem) join the same target.
doc-checks: check-manifest
	./scripts/verify-fase0-1-dox.sh
	./scripts/verify-ui-logic-firewall.sh
	./scripts/check-file-loc.sh Core/Shared/Audio/MidiExporter.cpp 200
	./scripts/check-file-loc.sh scripts/gameplay_probe.py 200
	./scripts/check-file-loc.sh scripts/gameplay_screen_metrics.py 200
	./scripts/check-file-loc.sh scripts/sheet_report.py 200
	./scripts/check-file-loc.sh scripts/bootstrap_auto_packs.sh 200
	# Phase 11 C.7: ceilings = line count at the C.7 commit (shrink ok, grow fails).
	# Amends ADR-0137's guarded-file list. PRD named five files with counts
	# (said "six"); those five are the contract.
	# Amended 2026-09-19 (ADR-0137, fifth amendment; ADR-0209 Q4(k)): the
	# HdPackBuilder.cpp ceiling rose from 2246 to 2265 for F12.8's remainder
	# sheet. The sheet itself is host-free in SheetRender (no ceiling, unit
	# tested); what landed here is the part that cannot be: accumulating each
	# written sheet's shapes in the one funnel they all pass through, and the
	# call that writes the complement. A ratchet again from 2265.
	# Amended 2026-09-19 (ADR-0137, eighth amendment; ADR-0197 §3, F12.6b):
	# 2265 -> 2282 for the recorder's retention of the $0000-$07FF window. The
	# `M` line's encoder is host-free and inline in TileSheetTypes.h (and unit
	# tested there); what is here is the OnFrameEnd/RecordGridFrame parameter,
	# the per-retained-frame copy, and the line WriteGridDump emits. A ratchet
	# again from 2282.
	./scripts/check-file-loc.sh Core/NES/HdPacks/HdPackBuilder.cpp 2282
	# Amended 2026-09-16 (ADR-0137, third amendment): the artist_chr_kit.py
	# ceiling rose from the C.7 count of 1762 to 1802 for #275's `--also`
	# dedup, which added a function and the prose that explains it. The other
	# three implementation ceilings are untouched, and this one is a ratchet
	# again from 1802. Amended 2026-09-19 (ADR-0137, sixth amendment; ADR-0213,
	# F12.4): 1802 -> 1803 for the `import asset_names as N` the F12.4 surface-name
	# guard needs. The guard itself folds into the existing write_png call; an
	# import cannot. No headroom added -- it is a ratchet again from 1803.
	./scripts/check-file-loc.sh scripts/artist_chr_kit.py 1803
	# Amended 2026-09-19 (ADR-0137, fifth amendment; ADR-0209 Q4(k)): 1932 ->
	# 1936 for the "unsorted" entry in _SHEET_RANK and the comment saying why
	# its rank never decides anything.
	./scripts/check-file-loc.sh scripts/mep_build.py 1945
	./scripts/check-file-loc.sh scripts/sheet_repaint.py 1591
	# Amended 2026-09-17 (ADR-0137, fourth amendment; ADR-0207): the ceiling on
	# scripts/core_unit_tests.cpp is GONE, not raised. C.7 ratcheted it at 7342
	# on 2026-09-15; ADR-0195 hit it with zero headroom the next day and the
	# second amendment raised it to 7600; the #302 fix landed at 7565 the day
	# after that. Twice in three days, both times from work already decided,
	# and each hit cost an amendment here and in ADR-0137's Status line. The
	# ratchet exists to stop implementation creeping, and a test file grows
	# whenever a decision does - so the guarded list is the four implementation
	# files above, and nothing else. Review, not wc -l, is what catches a
	# duplicated test case.
	./scripts/checks/verify_pack_host_allowlist_embed.sh
	# Phase 11 C.8 / ADR-0187: kind handlers and the validate gate stay in step
	# with scripts/pack_host_allowlist.json (CI vs client drift).
	python3 scripts/checks/verify_pack_host_allowlist_drift.py
	./scripts/checks/verify_core_no_http_client.sh
	./scripts/checks/verify_fetcher_no_filesystem_allowlist_load.sh
	./scripts/checks/verify_no_ptbr_usage_strings.sh
	./scripts/checks/verify_smoke_pack_headless.sh
	#F6.0–F6.5 structural guards for the community-pack pipeline: the
	#workflow/issue-form/catalog verifiers (AC-1..AC-7, F6.x) are stdlib+PyYAML
	#structural checks over the repo's own files — no network, no PAT, no ROM —
	#so they run in doc-checks and the CI build job fails on any drift.
	python3 scripts/checks/verify_community_pack_issue_template.py
	python3 scripts/checks/verify_community_pack_submitted_workflow.py
	python3 scripts/checks/verify_community_pack_drift_check_workflow.py
	python3 scripts/checks/verify_community_pack_catalog.py
	python3 scripts/checks/verify_community_pack_validate_workflow.py
	python3 scripts/checks/verify_gh_project_provenance_catalog.py
	python3 scripts/checks/verify_gh_project_provenance_drift.py
	python3 scripts/checks/verify_mei_catalog_generator.py
	python3 scripts/checks/verify_mei_catalog_split.py
	./scripts/checks/verify_community_pack_labels_script.sh
	./scripts/checks/verify_agents_md_recipe_handoff.sh
	./scripts/checks/verify_claude_md_section.sh
	./scripts/checks/verify_community_packs_catalog_doc.sh
	./scripts/checks/verify_hd_pack_authoring_doc.sh
	#The artist-facing docs (docs/remastering-a-game.md, ai-kit-review.md,
	#hd-pack-authoring.md): their links resolve, the scripts they name exist, and
	#every --flag they print is one the script it is printed for accepts. A guide
	#whose commands rotted is the discoverability failure it was written to fix.
	python3 scripts/checks/verify_artist_docs.py
	#Phase 11 C.4: the release tools zip is built from an explicit file list
	#(scripts/tools-zip-manifest.txt). `make release-macos` runs this too, but a
	#release is cut rarely, so the manifest would rot between releases and the
	#rot would only show up as a ModuleNotFoundError on a pack author's machine.
	python3 scripts/check_tools_zip_closure.py
	./scripts/checks/verify_mep_fallback_adr_provenance.sh
	./scripts/checks/verify_mep_fallback_adr.sh
	./scripts/checks/verify_mep_fallback_authoring_doc.sh
	./scripts/checks/verify_mep_fallback_by_name_underscore.sh
	./scripts/checks/verify_mep_fallback_constant_parity.sh
	./scripts/checks/verify_mep_fallback_lint_fixture.sh
	./scripts/checks/verify_mep_fallback_spec_doc.sh
	./scripts/checks/verify_mep_nested_zip_fallback.sh
	./scripts/checks/verify_status_kind_parity.sh
	./scripts/checks/verify_synthetic_nrom.sh
	#ADR-0191 (checks.yml compiles Linux only) + ADR-0203 (build.yml restores
	#a Windows job and an Apple-Silicon-only macOS job). Both were accepted
	#and implemented in the same change as their code, so this grep suite is
	#their unit test.
	./scripts/checks/verify_ci_platform_matrix.sh
	#ADR-0202: the release artifacts are named after the product (MesenAI) and
	#not after the tag (mesence-v0.1.0), the two are kept apart on purpose, and
	#SHA256SUMS stays derived from the zip basenames. Same-turn ADR, so this
	#grep suite is its unit test.
	./scripts/checks/verify_release_asset_names.sh
	#ADR-0204: the README's download links are fixed-name assets of the
	#`ci-latest` pre-release, published by build.yml's `publish` job. Same-turn
	#ADR, so this grep suite is its unit test. It asserts the two files agree on
	#the six names; it does NOT touch the network - `make check-download-links`
	#is the target that actually fetches them.
	./scripts/checks/verify_download_channel.sh
	#ADR reference integrity (PRD slice D1): every ADR-NNNN cited in docs/ADRs/
	#AGENTS.md/CLAUDE.md must resolve to docs/adr/NNNN-*.md.
	python3 scripts/checks/verify_adr_refs.py
	#Roadmap freshness (PRD slice C.2): a slice that has shipped loses its row
	#in the PRD's live tables and gains one line in the shipped record, so a
	#live row whose Decision cell opens with "shipped" is a contract breach.
	python3 scripts/checks/verify_prd_live_rows.py
	python3 scripts/test_verify_prd_live_rows.py
	#Unit tests for the community-pack pipeline's leaf modules (stdlib-only,
	#no network/PAT/ROM): the MEI/recipe/content-id/identity/meta/rules
	#interpreters and dispatch keep their own golden/PASS-style checks.
	python3 scripts/test_mei_rules.py
	python3 scripts/test_rom_target.py
	python3 scripts/test_mep_compare_render_dispatch.py
	python3 scripts/test_mep_content_id.py
	python3 scripts/test_mep_identity_check.py
	python3 scripts/test_mep_meta_parser.py
	python3 scripts/test_mep_recipe_fence.py
	python3 scripts/test_pack_id_rules.py
	python3 scripts/test_classify_pack_brief.py
	#ADR-0199: the classify step's API call — body shape (no `tools`), the
	#Interactions-API response walk, and the exit codes. No network.
	python3 scripts/test_gemini_classify.py
	python3 scripts/test_mep_build.py
	python3 scripts/test_mep_lint_border.py
	#ADR-0196 (F12.5): the `<addition>` tag's synthetic target key — the rule
	#itself, then the lint that gates a pack carrying one.
	python3 scripts/test_mep_addition.py
	python3 scripts/test_mep_lint_addition.py
	python3 scripts/test_mep_errata.py
	python3 scripts/test_mep_audio_patch_resolution.py
	#Downloader hop/shape rules and the lint decompression cap (review pass 2026-09-06).
	python3 scripts/test_fetch_pack.py
	python3 scripts/test_mep_lint_caps.py
	#F9.6 (ADR-0154): the external repaint's own suite -- stdlib-only Python,
	#no model, no weights, no network (its diffusion backend is exercised only
	#against a loopback stub and through its unavailable paths).
	python3 scripts/test_sheet_repaint.py
	#F9.13: the "did this recording reach gameplay?" criterion, on synthetic
	#packs written to a temp dir -- no emulator, no ROM, no recorded library.
	python3 scripts/test_gameplay_probe.py
	#Issue #183: sheet cells must name (key, palette) pairs the pack's own
	#hires.txt emits; the audit tool's test runs on synthetic packs.
	python3 scripts/test_sheet_keys_audit.py
	#The CDL reader: the CDLv2 header, the PRG/CHR split taken from the iNES
	#header, the union's CRC gate, region coalescing and both strip
	#directions. Fixtures built in memory; no emulator, no ROM.
	python3 scripts/test_cdl_tool.py
	#F12.4 (ADR-0213): the painting-surface name contract -- what Photoshop's
	#Generate Image Assets grammar, a Windows file system and the kit's own
	#manifest all have to accept. Pure string rules; no kit, no pack, no ROM.
	python3 scripts/test_asset_names.py
	#F12.6a (ADR-0197): hand-authored conditions -- the syntax a sheet may
	#carry, and the evaluation of one against a recorded route, written from
	#HdPackConditions.h. Synthetic grid streams; no emulator, no ROM.
	python3 scripts/test_mep_conditions.py
	#F12.10: the unattended recording job's resolver and report -- which
	#driver a ROM gets, which minted state a stage starts from, and a ROM
	#that failed reading as a row. Synthetic iNES files in a temp dir.
	python3 scripts/test_library_job.py
	#F9.24 (ADR-0183): the artist kit's assembler -- the page an artist reads
	#first. Synthetic manifest fragments in a temp dir; no pack, no ROM.
	python3 scripts/test_artist_kit_assemble.py
	#F9.24 (ADR-0183 §2.1): the kit's sprite half -- cycle phase order, a
	#variant beside its base, fusions excluded, one baseline per row, and a
	#legal composed sheet. Synthetic pack in a temp dir; no emulator, no ROM.
	python3 scripts/test_artist_kit.py
	#F9.24 (ADR-0183 §2.2): the kit's scenery half -- inkless groups dropped
	#with their count, an element recovered from adjacency.json across its
	#animation phases, and a round-trip that loses no (tileData, palette)
	#key. Synthetic pack in a temp dir; no emulator, no ROM.
	python3 scripts/test_artist_bg_kit.py
	#F9.24 (ADR-0183 §2.3): the kit's stage half -- the camera position
	#recovered from the recorded grid stream, de-duplication by world position,
	#the cut rule, the HUD band, and a panorama that slices back into a pack
	#sheet. Synthetic recording in a temp dir; no emulator, no ROM.
	python3 scripts/test_artist_map.py
	#F9.24 (ADR-0183 §2.4): the kit's pattern-page half -- a CHR ROM bank
	#completed to all 256 tiles, a CHR RAM bank filled only where a PRG block
	#explains it, evidence never repainted, and hires.txt left untouched.
	#Synthetic iNES image and pack in a temp dir; no emulator, no ROM library.
	python3 scripts/test_artist_chr_kit.py
	#Issue #225: the coverage measurement is a set intersection, so it must
	#refuse a reference pack keyed in a namespace the recording cannot hold
	#(a <patch> that turns CHR RAM into CHR ROM) instead of printing 0%.
	#Issue #231: a <patch> whose keys share the recording's shape measures, but
	#the patch and its header writes are named in a caveat above the tables.
	#Synthetic packs and IPS files in a temp dir; no emulator, no ROM.
	python3 scripts/test_artist_cover.py
	#F5.5 golden refresh: the MEP/MEI goldens under docs/specs/golden/ must stay
	#in sync with the emit code and the specs, or these gates fail.
	python3 scripts/validate-specs.py
	python3 scripts/test_mep_content_id_golden.py
	python3 scripts/test_mep_recipe.py
	python3 scripts/test_mep_compare_auto_palettes.py
	python3 scripts/test_gen_mep_recipe_fixture.py

ui: check-manifest InteropDLL/$(OBJFOLDER)/$(SHAREDLIB)
	mkdir -p $(OUTFOLDER)/Dependencies
	rm -fr $(OUTFOLDER)/Dependencies/*
	cp InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) $(OUTFOLDER)/$(SHAREDLIB)
	#Called twice because the first call copies native libraries to the bin folder which need to be included in Dependencies.zip
	#Don't run with AOT flags the first time to reduce build duration
	cd UI && dotnet publish -c $(BUILD_TYPE) $(OPTIMIZEUI) -r $(MESENPLATFORM)
	cd UI && dotnet publish -c $(BUILD_TYPE) $(OPTIMIZEUI) $(PUBLISHFLAGS)

core: check-manifest InteropDLL/$(OBJFOLDER)/$(SHAREDLIB)

#Fase 4 of the now-completed unit-test plan (see git history for
#docs/roadmap/plano-testes-unitarios.md): framework-free C++ unit
#tests for ChannelRoleClassifier + MepPack + BorderLayout (ADR-0149) +
#FrameCapture (F9.15) + the
#artist-legible sheet pipeline (ADR-0153). No `core` prerequisite - links
#only the listed .cpp files, not MesenCore/SDL - runs on any OS. Builds and
#then runs the binary; a failing case exits non-zero.
#Compiled as one object per translation unit so `make -j` can use every core
#(the single-command form was serial, and no -j could help it), and so a one-file
#edit relinks instead of recompiling all of them. Header deps come from -MMD -MP,
#the same mechanism ADR-0155 put on the core build.
#Warnings are errors here (Phase 11 C.1). Until 2026-09-14 this target built
#with -w: the fourteen binary builds of build.yml were the only thing that
#compiled Core/ on a PR, and /W4 /WX + -Werror there caught the tileNearby bug
#twice on the very day those builds were switched to workflow_dispatch (#230).
#With them off, this target is the PR gate's only compile of Core/ sources, so
#it carries the diagnostics. -Wno-deprecated-declarations is the one blanket
#exception, for inherited upstream code: Utilities/UTF8Util.cpp uses
#std::wstring_convert/std::codecvt_utf8_utf16, deprecated in C++17 with no
#standard replacement. Measured 2026-09-14: those are the only two warnings
#-Wall produces across the whole CUTSRC list.
CUTFLAGS := -std=c++17 -O2 -Wall -Werror -Wno-deprecated-declarations -I . -I Core -I Utilities
CUTSRC := \
  scripts/core_unit_tests.cpp \
  Core/Shared/Audio/ChannelRoleClassifier.cpp \
  Core/Shared/Audio/EnhancedSynthEngine.cpp \
  Core/Shared/Audio/EnhancedSynthPreset.cpp \
  Core/Shared/Audio/SmfWriter.cpp \
  Core/Shared/EnhancementPacks/AudioFingerprint.cpp \
  Core/Shared/EnhancementPacks/MepPack.cpp \
  Core/Shared/EnhancementPacks/MepRecipeInstaller.cpp \
  Core/Shared/EnhancementPacks/MepRecipeOps.cpp \
  Core/Shared/EnhancementPacks/MepContentId.cpp \
  Core/Shared/EnhancementPacks/MepLocalIdentityCache.cpp \
  Core/Shared/HeadlessInputScript.cpp \
  Core/Shared/HeadlessInputEngine.cpp \
  Core/Shared/MessageManager.cpp \
  Core/Shared/MovieSyncGate.cpp \
  Core/Shared/Video/BorderLayout.cpp \
  Core/Shared/Video/FrameCapture.cpp \
  Core/NES/HdPacks/OggMixer.cpp \
  Core/NES/HdPacks/MetatileVocabulary.cpp \
  Core/NES/HdPacks/ScreenStitcher.cpp \
  Core/NES/HdPacks/SheetGrouping.cpp \
  Core/NES/HdPacks/SheetRender.cpp \
  Core/NES/HdPacks/SpriteGrouping.cpp \
  Utilities/JsonReader.cpp \
  Utilities/FolderUtilities.cpp \
  Utilities/UTF8Util.cpp \
  Utilities/sha256.cpp \
  Utilities/SimpleLock.cpp \
  Utilities/Timer.cpp \
  Utilities/miniz.cpp
CUTOBJ := $(CUTSRC:.cpp=.cut.o)

%.cut.o: %.cpp
	$(CXX) $(CUTFLAGS) -MMD -MP -c $< -o $@

-include $(CUTOBJ:.o=.d)

scripts/core_unit_tests: $(CUTOBJ)
	$(CXX) $(CUTOBJ) -o $@

core-unit-tests: scripts/core_unit_tests
	scripts/core_unit_tests

#Phase 11 C.1: every scripts/test_*.py, one process per file. `doc-checks`
#above names a hand-picked subset file by file (it predates this target and
#stays as it is, so a doc-checks run keeps its own explicit list); this target
#is the whole suite and picks up a new test file with no edit anywhere.
python-tests:
	./scripts/checks/run_python_tests.sh

#F5.4g level-2 validation harness (channel roles / SFX classifier) - see scripts/roles_probe.cpp
roles-probe: core
	$(CXX) -std=c++17 -O2 -w -I . -I Core -Wl,-headerpad_max_install_names scripts/roles_probe.cpp Core/Shared/Audio/ChannelRoleClassifier.cpp InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) -o scripts/roles_probe
	$(call fixup_install_name,scripts/roles_probe)

#Headless MIDI/VGM capture harness (F1 regression tool) - see scripts/headless_record.cpp
capture-tool: core
	$(CXX) -std=c++17 -O2 -I . -I Core -Wl,-headerpad_max_install_names scripts/headless_record.cpp Core/Shared/Video/FrameCapture.cpp Core/Shared/MovieSyncGate.cpp InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) -o scripts/headless_record
	$(call fixup_install_name,scripts/headless_record)

#F5.4g Block D item 11 (ADR-0135/0051): productised extract-audio tool - discover the NES sound
#driver and enumerate music/SFX without playing. Full runtime contract: per-id frame budget +
#whole-run wall-clock budget, SIGINT abort, no-op on unsupported ROMs, enumeration.log.
#Run: scripts/spike_sound_driver <rom.nes> <workdir> <output-folder> [maxIds=40] [secondsPerId=4] [startAt=3.0] [wallClockBudget=300]
spike-sound-driver: core
	$(CXX) -std=c++17 -O2 -w -I . -I Core -Wl,-headerpad_max_install_names scripts/spike_sound_driver.cpp InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) -o scripts/spike_sound_driver
	$(call fixup_install_name,scripts/spike_sound_driver)

pgohelper: InteropDLL/$(OBJFOLDER)/$(SHAREDLIB)
	mkdir -p PGOHelper/$(OBJFOLDER) && cd PGOHelper/$(OBJFOLDER) && $(CXX) $(CXXFLAGS) $(LINKCHECKUNRESOLVED) -o pgohelper ../PGOHelper.cpp ../../bin/pgohelperlib.so -pthread $(FSLIB) $(SDL2LIB) $(LIBEVDEVLIB) $(X11LIB)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@
	
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

%.o: %.mm
	$(CXX) $(OBJCXXFLAGS) -c $< -o $@

#ADR-0155: -MMD writes a .d beside every object listing the headers it read;
#-include feeds them back, so editing a header rebuilds exactly the translation
#units that include it. Without this a header change rebuilds nothing and two
#objects can disagree on a struct layout - see the ADR for the crash that cost.
ALLOBJ = $(SEVENZIPOBJ) $(LUAOBJ) $(UTILOBJ) $(COREOBJ) $(SDLOBJ) $(LIBEVDEVOBJ) $(LINUXOBJ) $(DLLOBJ) $(MACOSOBJ)
-include $(ALLOBJ:.o=.d)

InteropDLL/$(OBJFOLDER)/$(SHAREDLIB): $(SEVENZIPOBJ) $(LUAOBJ) $(UTILOBJ) $(COREOBJ) $(SDLOBJ) $(LIBEVDEVOBJ) $(LINUXOBJ) $(DLLOBJ) $(MACOSOBJ)
	mkdir -p bin
	mkdir -p InteropDLL/$(OBJFOLDER)
	$(CXX) $(CXXFLAGS) $(LINKOPTIONS) $(LINKCHECKUNRESOLVED) -shared -o $(SHAREDLIB) $(DLLOBJ) $(SEVENZIPOBJ) $(LUAOBJ) $(LINUXOBJ) $(MACOSOBJ) $(LIBEVDEVOBJ) $(UTILOBJ) $(SDLOBJ) $(COREOBJ) $(SDL2INC) -pthread $(FSLIB) $(SDL2LIB) $(LIBEVDEVLIB) $(X11LIB)
	cp $(SHAREDLIB) bin/pgohelperlib.so
	mv $(SHAREDLIB) InteropDLL/$(OBJFOLDER)

pgo:
	./buildPGO.sh

run:
	$(OUTFOLDER)/$(MESENPLATFORM)/publish/Mesen

#Phase 11 C.4: cut the macOS Apple Silicon release from this working tree into
#out/release/ - the .app with the freshly built core injected and ad-hoc signed
#(BundleApp does not refresh it on its own), headless_record relocated to run
#from a download, the Python tools the remastering guide uses, and SHA256SUMS.
#The whole thing is one command on purpose: a release nobody can rebuild is a
#release nobody can check. Override the version with VERSION=vX.Y.Z.
VERSION ?= v0.1.0
release-macos:
	VERSION=$(VERSION) MAKE_BIN=$(MAKE) scripts/release_macos.sh

clean:
	rm -r -f $(ALLOBJ:.o=.d)
	rm -r -f $(COREOBJ)
	rm -r -f $(UTILOBJ)
	rm -r -f $(LINUXOBJ) $(LIBEVDEVOBJ)
	rm -r -f $(SDLOBJ)
	rm -r -f $(SEVENZIPOBJ)
	rm -r -f $(LUAOBJ)
	rm -r -f $(MACOSOBJ)
	rm -r -f $(DLLOBJ)
	rm -r -f $(CUTOBJ) $(CUTOBJ:.o=.d) scripts/core_unit_tests

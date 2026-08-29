#Welcome to what must be the most terrible makefile ever (but hey, it works)
#Both clang & gcc work fine - clang seems to output faster code
#.NET 10 (and its dev tools) must be installed to compile the UI.
#The emulation core also requires SDL2.
#Run "make" to build, "make run" to run

UNAME_S := $(shell uname -s)

MESENFLAGS=

ifeq ($(USE_GCC),true)
	CXX := g++
	CC := gcc
	PROFILE_GEN_FLAG := -fprofile-generate
	PROFILE_USE_FLAG := -fprofile-use
else
	CXX := clang++
	CC := clang
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

CXXFLAGS = -fPIC -Wall --std=c++17 $(MESENFLAGS) $(SDL2INC) -I $(realpath ./) -I $(realpath ./Core) -I $(realpath ./Utilities) -I $(realpath ./Sdl) -I $(realpath ./Linux) -I $(realpath ./MacOS)
OBJCXXFLAGS = $(CXXFLAGS)
CFLAGS = -fPIC -Wall $(MESENFLAGS)

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
unit-tests:
	$(DOTNET) test UI.Tests/UI.Tests.csproj --nologo

check-manifest:
	./scripts/check-core-manifest.sh

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
	./scripts/checks/verify_pack_host_allowlist_embed.sh
	./scripts/checks/verify_core_no_http_client.sh
	./scripts/checks/verify_fetcher_no_filesystem_allowlist_load.sh
	./scripts/checks/verify_smoke_pack_headless.sh
	python3 scripts/test_mep_build.py
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
#tests for ChannelRoleClassifier + MepPack. No `core` prerequisite - links
#only the listed .cpp files, not MesenCore/SDL - runs on any OS. Builds and
#then runs the binary; a failing case exits non-zero.
core-unit-tests:
	$(CXX) -std=c++17 -O2 -w -I . -I Core -I Utilities scripts/core_unit_tests.cpp \
	  Core/Shared/Audio/ChannelRoleClassifier.cpp \
	  Core/Shared/Audio/EnhancedSynthEngine.cpp \
	  Core/Shared/Audio/EnhancedSynthPreset.cpp \
	  Core/Shared/Audio/SmfWriter.cpp \
	  Core/Shared/EnhancementPacks/AudioFingerprint.cpp \
	  Core/Shared/EnhancementPacks/MepPack.cpp \
	  Core/Shared/EnhancementPacks/MepRecipeInstaller.cpp \
	  Core/Shared/EnhancementPacks/MepRecipeOps.cpp \
	  Core/Shared/EnhancementPacks/MepContentId.cpp \
	  Core/Shared/MessageManager.cpp \
	  Utilities/JsonReader.cpp Utilities/FolderUtilities.cpp Utilities/UTF8Util.cpp \
	  Utilities/sha256.cpp Utilities/SimpleLock.cpp Utilities/Timer.cpp Utilities/miniz.cpp \
	  -o scripts/core_unit_tests
	scripts/core_unit_tests

#F5.4g level-2 validation harness (channel roles / SFX classifier) - see scripts/roles_probe.cpp
roles-probe: core
	$(CXX) -std=c++17 -O2 -w -I . -I Core -Wl,-headerpad_max_install_names scripts/roles_probe.cpp Core/Shared/Audio/ChannelRoleClassifier.cpp InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) -o scripts/roles_probe
	install_name_tool -change $(SHAREDLIB) $(CURDIR)/InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) scripts/roles_probe 2>/dev/null || true
	codesign -f -s - scripts/roles_probe 2>/dev/null || true

#Headless MIDI/VGM capture harness (F1 regression tool) - see scripts/headless_record.cpp
capture-tool: core
	$(CXX) -std=c++17 -O2 -I . -I Core -Wl,-headerpad_max_install_names scripts/headless_record.cpp InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) -o scripts/headless_record
	install_name_tool -change $(SHAREDLIB) $(CURDIR)/InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) scripts/headless_record 2>/dev/null || true
	codesign -f -s - scripts/headless_record 2>/dev/null || true

#F5.4g Block D item 11 (ADR-0135/0051): productised extract-audio tool - discover the NES sound
#driver and enumerate music/SFX without playing. Full runtime contract: per-id frame budget +
#whole-run wall-clock budget, SIGINT abort, no-op on unsupported ROMs, enumeration.log.
#Run: scripts/spike_sound_driver <rom.nes> <workdir> <output-folder> [maxIds=40] [secondsPerId=4] [startAt=3.0] [wallClockBudget=300]
spike-sound-driver: core
	$(CXX) -std=c++17 -O2 -w -I . -I Core -Wl,-headerpad_max_install_names scripts/spike_sound_driver.cpp InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) -o scripts/spike_sound_driver
	install_name_tool -change $(SHAREDLIB) $(CURDIR)/InteropDLL/$(OBJFOLDER)/$(SHAREDLIB) scripts/spike_sound_driver 2>/dev/null || true
	codesign -f -s - scripts/spike_sound_driver 2>/dev/null || true

pgohelper: InteropDLL/$(OBJFOLDER)/$(SHAREDLIB)
	mkdir -p PGOHelper/$(OBJFOLDER) && cd PGOHelper/$(OBJFOLDER) && $(CXX) $(CXXFLAGS) $(LINKCHECKUNRESOLVED) -o pgohelper ../PGOHelper.cpp ../../bin/pgohelperlib.so -pthread $(FSLIB) $(SDL2LIB) $(LIBEVDEVLIB) $(X11LIB)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@
	
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

%.o: %.mm
	$(CXX) $(OBJCXXFLAGS) -c $< -o $@

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

clean:
	rm -r -f $(COREOBJ)
	rm -r -f $(UTILOBJ)
	rm -r -f $(LINUXOBJ) $(LIBEVDEVOBJ)
	rm -r -f $(SDLOBJ)
	rm -r -f $(SEVENZIPOBJ)
	rm -r -f $(LUAOBJ)
	rm -r -f $(MACOSOBJ)
	rm -r -f $(DLLOBJ)

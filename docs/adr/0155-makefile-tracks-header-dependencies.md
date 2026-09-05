# ADR-0155: The makefile tracks header dependencies (`-MMD -MP`) instead of relying on a manual clean rebuild

- Status: accepted
- Date: 2026-09-05
- Related: ADR-0007 (Core source-manifest drift guard), ADR-0126/ADR-0131 (unit-test wiring), ADR-0153 (artist-legible sheets)

## Context

The makefile compiles with a bare pattern rule:

```make
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@
```

`.o` files therefore depend on their `.cpp` and on nothing else. Changing a
header rebuilds nothing, so translation units that include it keep the layout
they were compiled against. The project has known this for a while — the
standing workaround is to `rm -f $(find Core InteropDLL -name '*.o')` by hand
whenever a Core class member changes — but a workaround that depends on
someone remembering is not a guard.

It failed on 2026-09-05, and failed expensively. `MesenSheets::SheetCell`
(`Core/NES/HdPacks/TileSheetTypes.h`) gained two `std::vector` members for the
Phase 9 alias pass. `SheetRender.cpp` was touched and recompiled;
`SheetGrouping.cpp` was not. The two objects then disagreed on
`sizeof(SheetCell)`, so a `SheetGroup` built by one and read by the other
reported a `Cells.size()` of `14757395258967641294` and
`MesenSheets::RenderGroup` walked off the end of the image buffer. Every one
of the 30 ROMs in the test library segfaulted in `HdPackBuilder::SaveHdPack`,
at the very end of a 300-second recording — five minutes of work per ROM
thrown away, and a crash signature (`_platform_memmove`, `EXC_BAD_ACCESS` at
`0x1`) that points at the render code rather than at the stale object that
actually caused it.

The cost profile is what makes this worth a decision rather than a habit: the
failure is silent at build time, arbitrarily delayed at run time, and its
symptom names the wrong file.

Non-goals: changing the source manifest (ADR-0007 already guards that),
touching the MSVC/`Core.vcxproj` build, or reorganising headers.

## Decision

Generate and consume dependency files:

- add `-MMD -MP` to `CXXFLAGS` (and therefore `OBJCXXFLAGS`), so every
  compile writes a sibling `.d` listing the headers it read. `-MP` emits
  phony targets for those headers, so deleting or renaming one does not
  break the build with "No rule to make target";
- `-include` the `.d` files for every object the build knows about, so a
  header edit rebuilds exactly the translation units that include it;
- add `*.d` to `.gitignore` next to the existing object-file rules, and
  extend `make clean` to remove them, so a `.d` naming a header that no
  longer exists cannot outlive the tree it described;
- keep the manual clean rebuild documented as the recovery step for a tree
  whose `.d` files predate this change.

`-MMD` (not `-MD`) deliberately ignores system headers: a toolchain upgrade
should not invalidate every object, and the failure mode this ADR exists to
prevent is a *project* header changing shape.

## Verification

Proven on the tree this ADR was written against: after a clean rebuild,
`touch Core/NES/HdPacks/TileSheetTypes.h` followed by `make capture-tool`
recompiles the six HdPacks translation units that include it — including
`SheetGrouping.cpp`, the object that was stale when the library segfaulted —
plus the three transitive consumers (`NesConsole.cpp`, `NesPpu.cpp`,
`InteropDLL/EmuApiWrapper.cpp`) and nothing else. Before this change the same
`touch` recompiled nothing at all.

## Consequences

- The first build after this lands is a full rebuild — no `.d` files exist
  yet, so every object is out of date. That is the correct one-time cost.
- Incremental builds get slightly slower (one extra file written per
  translation unit) and correct, which is the trade this makes.
- CI is unaffected: it always builds from a clean tree, so it never had the
  bug and gains nothing but the write cost.
- `Core.vcxproj` is untouched, so the Windows build keeps whatever
  header tracking MSBuild already does. The two build systems continue to be
  kept in step by `scripts/check-core-manifest.sh` (ADR-0007), which is about
  the *set* of sources, not their dependencies.
- Removing the manual-clean habit removes the only reason anyone had to run
  `find ... -name '*.o' -delete`, which is itself a footgun on a tree with a
  build in flight.

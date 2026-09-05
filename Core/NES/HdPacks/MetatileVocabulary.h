#pragma once
//ADR-0153 §1/§3 (Phase 9, slice F9.1): the game's own building block, inferred
//from the recorded background grid stream. Host-free (see TileSheetTypes.h) -
//no pch.h, no Emulator, no console type, no I/O - so this links into
//`make core-unit-tests` exactly like Core/Shared/Video/BorderLayout.h.
//
//The pass is a port of scripts/spike_tile_sheets.py (2026-09-04 spike,
//evidence under runs/spike-sheets/): stable screens -> HUD rows -> grid phase
//detection -> vocabulary with counts, contexts and E/S adjacency.
#include "NES/HdPacks/TileSheetTypes.h"
#include "NES/HdPacks/SheetRender.h"   // for MesenSheets::TileLookup

namespace MesenSheets
{
	//Distinct stable screens: consecutive frames with an identical cell grid,
	//held for >= minStableFrames, with at least half the playfield drawn.
	std::vector<const GridFrame*> SelectStableScreens(const std::vector<GridFrame>& frames, uint32_t minStableFrames, uint32_t& distinctOut);

	//Top/bottom cell rows that form a status bar: blank across the distinct
	//stable screens, or mostly frozen across a quorum of them while still
	//drawing something (ADR-0153 §3, amended twice - byte-identity misses every
	//HUD with a score in it, and unanimity misses every HUD whose recording
	//also contains a title screen).
	void DetectHudRows(const std::vector<const GridFrame*>& screens, uint32_t& topRows, uint32_t& bottomRows);

	//ADR-0153 §1 (amended): the phase with the fewest distinct 2x2 tuples wins,
	//and its margin over the other three is HasGrid; the unit is 16 unless the
	//recording is too thin in aligned placements to justify it.
	GridDetection DetectGrid(const std::vector<const GridFrame*>& screens, uint32_t hudRows, uint32_t hudBottomRows);

	//The whole F9.1 pass: stable screens -> HUD rows -> grid detection ->
	//vocabulary with counts, contexts and E/S adjacency between entries.
	Vocabulary BuildVocabulary(const std::vector<GridFrame>& frames, const TileLookup& lookup);
}

#pragma once
//ADR-0153 §2 (Phase 9, slice F9.5): the mutual-predictability criterion applied
//to OAM instead of background adjacency. A separate module rather than more
//SheetGrouping because the *evidence* is a different shape - a stream of OAM
//snapshots, where "next to" means a relative offset in pixels that can point any
//way, not one of two fixed grid directions. What the two share once the edges
//exist (DSU, BFS layout, biggest group first) is reused from SheetGrouping
//rather than copied. Host-free (see TileSheetTypes.h): no pch.h, no Emulator,
//no I/O. Its stateful partner, per ADR-0127, is HdPackBuilder: that class
//records the OAM stream during a session and writes the sprNNN.png/.json bytes
//SheetRender makes out of the groups returned here.
#include "NES/HdPacks/TileSheetTypes.h"

namespace MesenSheets
{
	//Distinct sprite shapes in the recording, most-seen first (ADR-0153 §3), as
	//a Vocabulary at grid unit 8 with one shape per entry - so SheetRender and
	//SerializeSheet treat a sprite cell exactly like a metatile cell. Count is
	//the number of OAM instances, over de-duplicated frames.
	Vocabulary BuildSpriteVocabulary(const std::vector<OamFrame>& frames);

	//Two sprites join when they hold one *constant* relative offset over at
	//least `minCount` recorded frames and that offset accounts for at least
	//`minProb` of both shapes' appearances. A bullet that drifts past everything
	//has many offsets and clears none of them.
	std::vector<GroupEdge> SelectSpriteEdges(const std::vector<OamFrame>& frames, const Vocabulary& vocab, uint32_t minCount, double minProb);

	//Those edges through SheetGrouping's DSU/BFS: components of
	//2..kSheetMaxObjectCells cells laid out at their dominant offsets.
	std::vector<SheetGroup> BuildSprites(const std::vector<OamFrame>& frames, const Vocabulary& vocab, uint32_t minCount, double minProb);

	//Convenience overload using kSheetMinPairCount / kSheetMinPairProb.
	std::vector<SheetGroup> BuildSprites(const std::vector<OamFrame>& frames, const Vocabulary& vocab);
}

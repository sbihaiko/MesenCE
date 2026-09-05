#pragma once
//ADR-0153 §2 (Phase 9): mutual-predictability grouping - the criterion that
//replaces F5.4e's "seen adjacent >= 2 times" union-find, which collapsed any
//contiguous scene into one component and so never emitted an object sheet on a
//real game. Host-free (see TileSheetTypes.h): no pch.h, no Emulator, no I/O.
//HdPackBuilder feeds the vocabulary in and writes the bytes SheetRender makes
//out of the groups returned here.
#include "NES/HdPacks/TileSheetTypes.h"

namespace MesenSheets
{
	//ADR-0153 §2: edges that pass the mutual-predictability test, in both
	//directions, with their evidence. Deterministic order.
	std::vector<GroupEdge> SelectPredictiveEdges(const Vocabulary& vocab, uint32_t minCount, double minProb);

	//DSU over those edges; components of 2..kSheetMaxObjectCells cells become
	//objects, laid out by BFS at their dominant E/S offsets.
	std::vector<SheetGroup> BuildObjects(const Vocabulary& vocab, uint32_t minCount, double minProb);

	//Convenience overload using kSheetMinPairCount / kSheetMinPairProb.
	std::vector<SheetGroup> BuildObjects(const Vocabulary& vocab);

	//The half of the criterion that does not care where the edges came from,
	//shared with SpriteGrouping (F9.5): components of 2..kSheetMaxObjectCells
	//cells, then a BFS layout at each edge's Dx/Dy, biggest group first.
	std::vector<std::vector<uint32_t>> BuildEdgeComponents(const std::vector<GroupEdge>& edges, uint32_t cellCount);
	std::vector<SheetGroup> LayoutGroups(const Vocabulary& vocab, const std::vector<GroupEdge>& edges);
}

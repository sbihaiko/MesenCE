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
	//Path-halving union-find over cell indexes. Header-level because both
	//grouping modules need the same components: SheetGrouping over predictive
	//edges, SpriteGrouping over an OAM frame's spatial clusters (ADR-0170).
	class Dsu
	{
	public:
		explicit Dsu(size_t size) : _parent(size)
		{
			for(size_t i = 0; i < size; i++) {
				_parent[i] = (uint32_t)i;
			}
		}

		uint32_t Find(uint32_t node)
		{
			while(_parent[node] != node) {
				_parent[node] = _parent[_parent[node]];
				node = _parent[node];
			}
			return node;
		}

		void Union(uint32_t a, uint32_t b)
		{
			uint32_t rootA = Find(a);
			uint32_t rootB = Find(b);
			if(rootA != rootB) {
				_parent[rootA] = rootB;
			}
		}

	private:
		std::vector<uint32_t> _parent;
	};

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
	std::vector<SheetGroup> LayoutGroups(const Vocabulary& vocab, const std::vector<GroupEdge>& edges);

	//ADR-0175 (issue #175): the slots of a group's Columns x Rows grid that no
	//member occupies, row-major. A group sheet's grid is the *bounding box* of
	//a BFS layout, so a figure that is not a rectangle - an L-shaped ledge, the
	//two rows of a "GAME OVER" - leaves blanks in it by construction. They are
	//not missing art and there is nothing to paint in them; without this list
	//an artist cannot tell a deliberate blank from a subject the recorder
	//failed to place, which is exactly what issue #175 reported.
	std::vector<SheetSlot> EmptyGroupSlots(const SheetGroup& group);
}

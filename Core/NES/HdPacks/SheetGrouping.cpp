#include "NES/HdPacks/SheetGrouping.h"
#include <algorithm>
#include <deque>
#include <limits>
#include <set>
#include <utility>

namespace MesenSheets
{
	namespace
	{
		//---- edge selection ------------------------------------------------

		//Per-direction out/in totals: out(A) = every B ever seen at A's east
		//(or south) side, in(B) = every A that ever sat west (north) of B.
		struct Degrees
		{
			std::map<uint32_t, uint32_t> Out;
			std::map<uint32_t, uint32_t> In;

			explicit Degrees(const AdjacencyMap& adjacency)
			{
				for(const auto& entry : adjacency) {
					Out[entry.first.first] += entry.second;
					In[entry.first.second] += entry.second;
				}
			}

			uint32_t Total(const std::map<uint32_t, uint32_t>& side, uint32_t node) const
			{
				auto match = side.find(node);
				return match == side.end() ? 0 : match->second;
			}
		};

		//ADR-0153 §2: B is the usual thing east of A *and* A is the usual thing
		//west of B. Sand next to everything fails; a 2x2 boss door passes.
		void SelectDirection(const AdjacencyMap& adjacency, char dir, uint32_t minCount, double minProb, std::vector<GroupEdge>& output)
		{
			Degrees degrees(adjacency);
			for(const auto& entry : adjacency) {
				uint32_t a = entry.first.first;
				uint32_t b = entry.first.second;
				uint32_t count = entry.second;
				uint32_t outA = degrees.Total(degrees.Out, a);
				uint32_t inB = degrees.Total(degrees.In, b);
				if(a == b || count < minCount || outA == 0 || inB == 0) {
					continue;
				}
				double probAb = (double)count / outA;
				double probBa = (double)count / inB;
				if(probAb < minProb || probBa < minProb) {
					continue;
				}
				GroupEdge edge;
				edge.A = a;
				edge.B = b;
				edge.Dir = dir;
				edge.Dx = dir == 'E' ? 1 : 0;
				edge.Dy = dir == 'E' ? 0 : 1;
				edge.Count = count;
				edge.ProbAB = probAb;
				edge.ProbBA = probBa;
				output.push_back(edge);
			}
		}

		//---- components ----------------------------------------------------

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

		//A single cell is not a figure, and a component past kSheetMaxObjectCells
		//is a contiguous background region - exactly the F5.4e failure ADR-0153
		//retires. Members come out sorted ascending, which keeps every tie-break
		//below deterministic.
		std::vector<std::vector<uint32_t>> BuildComponentsImpl(const std::vector<GroupEdge>& edges, uint32_t cellCount)
		{
			Dsu dsu(cellCount);
			for(const GroupEdge& edge : edges) {
				if(edge.A < cellCount && edge.B < cellCount) {
					dsu.Union(edge.A, edge.B);
				}
			}
			std::map<uint32_t, std::vector<uint32_t>> byRoot;
			for(uint32_t i = 0; i < cellCount; i++) {
				byRoot[dsu.Find(i)].push_back(i);
			}
			std::vector<std::vector<uint32_t>> components;
			for(auto& entry : byRoot) {
				size_t size = entry.second.size();
				if(size >= 2 && size <= kSheetMaxObjectCells) {
					components.push_back(std::move(entry.second));
				}
			}
			return components;
		}

		//---- layout --------------------------------------------------------

		struct Neighbour
		{
			uint32_t Node = 0;
			int32_t Dx = 0;
			int32_t Dy = 0;
		};

		using AdjList = std::map<uint32_t, std::vector<Neighbour>>;
		using PosMap = std::map<uint32_t, std::pair<int32_t, int32_t>>;

		//Undirected walkable form of the edges internal to one component; the
		//kept edges themselves are copied out as the group's evidence.
		AdjList InternalAdjacency(const std::vector<GroupEdge>& edges, const std::vector<uint32_t>& members, std::vector<GroupEdge>& outEdges)
		{
			std::set<uint32_t> memberSet(members.begin(), members.end());
			AdjList adjacency;
			for(const GroupEdge& edge : edges) {
				if(!memberSet.count(edge.A) || !memberSet.count(edge.B)) {
					continue;
				}
				outEdges.push_back(edge);
				adjacency[edge.A].push_back({ edge.B, edge.Dx, edge.Dy });
				adjacency[edge.B].push_back({ edge.A, -edge.Dx, -edge.Dy });
			}
			return adjacency;
		}

		size_t DegreeOf(const AdjList& adjacency, uint32_t node)
		{
			auto match = adjacency.find(node);
			return match == adjacency.end() ? 0 : match->second.size();
		}

		//Most connected member first: the hub of the figure, so the BFS spreads
		//outwards instead of dragging one arm across the sheet.
		uint32_t PickStart(const std::vector<uint32_t>& members, const AdjList& adjacency)
		{
			uint32_t best = members.front();
			size_t bestDegree = DegreeOf(adjacency, best);
			for(uint32_t member : members) {
				size_t degree = DegreeOf(adjacency, member);
				if(degree > bestDegree) {
					best = member;
					bestDegree = degree;
				}
			}
			return best;
		}

		int32_t MaxX(const PosMap& positions)
		{
			int32_t maxX = 0;
			for(const auto& entry : positions) {
				maxX = std::max(maxX, entry.second.first);
			}
			return maxX;
		}

		//BFS from the hub, each neighbour placed at (+1,0) for an E edge and
		//(0,+1) for an S edge. A member the walk never reaches is appended in a
		//fresh column on row 0, so nothing silently drops.
		PosMap PlaceMembers(const std::vector<uint32_t>& members, const AdjList& adjacency)
		{
			PosMap positions;
			std::set<std::pair<int32_t, int32_t>> taken;
			std::deque<uint32_t> queue;
			uint32_t start = PickStart(members, adjacency);
			positions[start] = std::make_pair(0, 0);
			taken.insert(positions[start]);
			queue.push_back(start);
			while(!queue.empty()) {
				uint32_t node = queue.front();
				queue.pop_front();
				auto match = adjacency.find(node);
				if(match == adjacency.end()) {
					continue;
				}
				std::pair<int32_t, int32_t> origin = positions[node];
				for(const Neighbour& neighbour : match->second) {
					if(positions.count(neighbour.Node)) {
						continue;
					}
					std::pair<int32_t, int32_t> spot(origin.first + neighbour.Dx, origin.second + neighbour.Dy);
					//Sprite offsets are quantised to cells (F9.5), so two members
					//can land on the same square; nudge east until one is free
					//rather than let a cell overwrite another on the sheet.
					while(taken.count(spot)) {
						spot.first++;
					}
					taken.insert(spot);
					positions[neighbour.Node] = spot;
					queue.push_back(neighbour.Node);
				}
			}
			for(uint32_t member : members) {
				if(!positions.count(member)) {
					positions[member] = std::make_pair(MaxX(positions) + 1, 0);
					taken.insert(positions[member]);
				}
			}
			return positions;
		}

		//---- groups --------------------------------------------------------

		void FillCell(const Vocabulary& vocab, uint32_t metatile, SheetCell& cell)
		{
			cell.Metatile = (int32_t)metatile;
			if(metatile < vocab.Entries.size()) {
				const MetatileEntry& entry = vocab.Entries[metatile];
				cell.Key = entry.Key;
				cell.Count = entry.Count;
				cell.Context = entry.Context;
			}
		}

		//X/Y stay in CELLS: SheetRender::RenderGroup owns the conversion to
		//sheet pixels and the gutter (ADR-0153 §3).
		SheetGroup MakeGroup(const Vocabulary& vocab, const std::vector<uint32_t>& members, const PosMap& positions, std::vector<GroupEdge> edges)
		{
			int32_t minX = std::numeric_limits<int32_t>::max();
			int32_t minY = minX;
			int32_t maxX = std::numeric_limits<int32_t>::min();
			int32_t maxY = maxX;
			for(const auto& entry : positions) {
				minX = std::min(minX, entry.second.first);
				maxX = std::max(maxX, entry.second.first);
				minY = std::min(minY, entry.second.second);
				maxY = std::max(maxY, entry.second.second);
			}
			SheetGroup group;
			group.Edges = std::move(edges);
			group.Columns = (uint32_t)(maxX - minX + 1);
			group.Rows = (uint32_t)(maxY - minY + 1);
			for(uint32_t member : members) {
				const std::pair<int32_t, int32_t>& position = positions.at(member);
				SheetCell cell;
				cell.Index = (uint32_t)group.Cells.size();
				cell.X = position.first - minX;
				cell.Y = position.second - minY;
				FillCell(vocab, member, cell);
				group.Cells.push_back(cell);
			}
			return group;
		}

		//obj000 is always the biggest figure; ties go to the component holding
		//the smallest vocabulary index, which is unique (components are disjoint).
		bool LargerFirst(const SheetGroup& a, const SheetGroup& b)
		{
			if(a.Cells.size() != b.Cells.size()) {
				return a.Cells.size() > b.Cells.size();
			}
			return a.Cells.front().Metatile < b.Cells.front().Metatile;
		}
	}

	std::vector<GroupEdge> SelectPredictiveEdges(const Vocabulary& vocab, uint32_t minCount, double minProb)
	{
		std::vector<GroupEdge> edges;
		//AdjacencyMap is ordered by (A, B), so East-then-South emission is
		//already byte-stable without an extra sort.
		SelectDirection(vocab.East, 'E', minCount, minProb, edges);
		SelectDirection(vocab.South, 'S', minCount, minProb, edges);
		return edges;
	}

	std::vector<std::vector<uint32_t>> BuildEdgeComponents(const std::vector<GroupEdge>& edges, uint32_t cellCount)
	{
		return BuildComponentsImpl(edges, cellCount);
	}

	std::vector<SheetGroup> LayoutGroups(const Vocabulary& vocab, const std::vector<GroupEdge>& edges)
	{
		std::vector<SheetGroup> groups;
		for(const std::vector<uint32_t>& members : BuildComponentsImpl(edges, (uint32_t)vocab.Entries.size())) {
			std::vector<GroupEdge> internalEdges;
			AdjList adjacency = InternalAdjacency(edges, members, internalEdges);
			PosMap positions = PlaceMembers(members, adjacency);
			groups.push_back(MakeGroup(vocab, members, positions, std::move(internalEdges)));
		}
		std::sort(groups.begin(), groups.end(), LargerFirst);
		return groups;
	}

	std::vector<SheetGroup> BuildObjects(const Vocabulary& vocab, uint32_t minCount, double minProb)
	{
		return LayoutGroups(vocab, SelectPredictiveEdges(vocab, minCount, minProb));
	}

	std::vector<SheetGroup> BuildObjects(const Vocabulary& vocab)
	{
		return BuildObjects(vocab, kSheetMinPairCount, kSheetMinPairProb);
	}
}

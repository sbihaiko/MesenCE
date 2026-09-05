//ADR-0153 §6: screen-based and continuous stitching. Port of the 2026-09-04
//spike (scripts/spike_tile_sheets.py: shift_match, stitch, shift_match_x,
//stitch_continuous), with one behavioural change the ADR asks for: a cut in the
//continuous stitcher starts a new map instead of leaving a gap in the old one.
//F9.8 adds the rule the spike never had: a screen joins a map only on positive
//adjacency evidence, and a recording that produces none produces no map.
//F9.12 adds the continuous half of the same idea: a region ends when a step
//that did not move the camera stops showing the same place.
#include "NES/HdPacks/ScreenStitcher.h"

#include <algorithm>
#include <cstdarg>
#include <cstdio>
#include <map>
#include <string>
#include <utility>

namespace MesenSheets
{
	namespace
	{
		//The spike's search window: a full screen horizontally, most of one
		//vertically. Cheap enough - this runs per screen pair, not per frame.
		constexpr int32_t kScreenMaxDx = 31;
		constexpr int32_t kScreenMaxDy = 22;
		//A horizontal scroller never moves a screen and a half in one sample.
		constexpr int32_t kContinuousMaxDx = 12;
		//Below this the two frames are not the same place any more (ADR-0153 §6).
		constexpr double kMinMatch = 0.5;
		//A frame with less than this drawn is a fade, a menu or a blank.
		constexpr uint32_t kMinDrawnCells = 200;
		//Sampling step BuildMaps hands to the continuous stitcher.
		constexpr uint32_t kDefaultFrameStep = 3;

		struct CellRef
		{
			int32_t Col;
			int32_t Row;
			ShapeId Shape;
		};

		int32_t Sign(int32_t v) { return v > 0 ? 1 : (v < 0 ? -1 : 0); }

		//Cell parity of the detected 16x16 grid; always true at grid unit 8.
		bool IsAligned(int32_t v, uint8_t phase)
		{
			return ((((v - (int32_t)phase) % 2) + 2) % 2) == 0;
		}

		uint32_t PlayRows(const Vocabulary& vocab)
		{
			uint32_t used = vocab.HudRows + vocab.HudBottomRows;
			return used < kGridRows ? kGridRows - used : 0;
		}

		ShapeId ShapeAt(const GridFrame& f, int32_t col, int32_t row, uint32_t hudBottomRows)
		{
			if(col < 0 || row < 0 || col >= (int32_t)kGridCols || row >= (int32_t)(kGridRows - hudBottomRows)) {
				return kEmptyCell;
			}
			return f.Cells[row][col];
		}

		//The drawn playfield cells of `f`, in row-major order.
		std::vector<CellRef> PlayfieldCells(const GridFrame& f, uint32_t hudRows, uint32_t hudBottomRows)
		{
			std::vector<CellRef> cells;
			cells.reserve(kGridRows * kGridCols);
			for(uint32_t r = hudRows; r < kGridRows - hudBottomRows; r++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					if(f.Cells[r][c] != kEmptyCell) {
						cells.push_back({ (int32_t)c, (int32_t)r, f.Cells[r][c] });
					}
				}
			}
			return cells;
		}

		//Content identity of a screen: the playfield only, so the HUD's clock
		//never makes two visits to the same room look like two rooms.
		std::string ScreenKey(const GridFrame& f, uint32_t hudRows, uint32_t hudBottomRows)
		{
			uint32_t last = kGridRows - hudBottomRows;
			const char* start = (const char*)&f.Cells[hudRows][0];
			return std::string(start, (size_t)(last - hudRows) * kGridCols * sizeof(ShapeId));
		}

		std::string Format(const char* fmt, ...)
		{
			char buffer[160];
			va_list args;
			va_start(args, fmt);
			vsnprintf(buffer, sizeof(buffer), fmt, args);
			va_end(args);
			return std::string(buffer);
		}
	}

	ShiftMatch BestShift(const GridFrame& a, const GridFrame& b, uint32_t hudRows, uint32_t hudBottomRows, int32_t maxDx, int32_t maxDy)
	{
		ShiftMatch best;
		std::vector<CellRef> cells = PlayfieldCells(b, hudRows, hudBottomRows);
		size_t total = cells.size();
		if(total == 0) {
			return best;
		}

		size_t bestHits = 0;
		bool haveBest = false;
		for(int32_t dy = -maxDy; dy <= maxDy; dy++) {
			for(int32_t dx = -maxDx; dx <= maxDx; dx++) {
				if(dx == 0 && dy == 0) {
					continue;
				}
				size_t hits = 0;
				for(size_t i = 0; i < total; i++) {
					//Even a perfect run from here on could not beat the best.
					if(haveBest && hits + (total - i) <= bestHits) {
						break;
					}
					const CellRef& cell = cells[i];
					if(ShapeAt(a, cell.Col + dx, cell.Row + dy, hudBottomRows) == cell.Shape) {
						hits++;
					}
				}
				if(!haveBest || hits > bestHits) {
					haveBest = true;
					bestHits = hits;
					best.Dx = dx;
					best.Dy = dy;
					best.Score = (double)hits / (double)total;
				}
			}
		}
		return best;
	}

	namespace
	{
		//1-D variant used by the continuous stitcher. Unlike BestShift it keeps
		//dx == 0 as a candidate: "the camera did not move" is a valid answer for
		//a single frame step, and dropping it would fake a cut on a still frame.
		//`outStillScore` is the score of "the camera did not move", which F9.8
		//uses as the baseline a claimed shift has to beat.
		ShiftMatch BestShiftX(const GridFrame& a, const GridFrame& b, uint32_t hudRows, uint32_t hudBottomRows, int32_t maxDx, double& outStillScore)
		{
			ShiftMatch best;
			outStillScore = 0;
			std::vector<CellRef> cells = PlayfieldCells(b, hudRows, hudBottomRows);
			size_t total = cells.size();
			if(total == 0) {
				return best;
			}
			size_t bestHits = 0;
			bool haveBest = false;
			for(int32_t dx = -maxDx; dx <= maxDx; dx++) {
				size_t hits = 0;
				for(size_t i = 0; i < total; i++) {
					//No early exit here: the still score is needed in full, and
					//a shift that cannot win still has to be counted exactly
					//when it is the one at dx == 0.
					const CellRef& cell = cells[i];
					if(ShapeAt(a, cell.Col + dx, cell.Row, hudBottomRows) == cell.Shape) {
						hits++;
					}
				}
				if(dx == 0) {
					outStillScore = (double)hits / (double)total;
				}
				//Ties go to the smallest displacement: on flat content every
				//offset scores alike, and "it moved twelve cells" is a claim,
				//while "it did not move" is the null hypothesis.
				bool better = !haveBest || hits > bestHits || (hits == bestHits && std::abs(dx) < std::abs(best.Dx));
				if(better) {
					haveBest = true;
					bestHits = hits;
					best.Dx = dx;
					best.Score = (double)hits / (double)total;
				}
			}
			return best;
		}

		//Reads the 1 (unit 8) or 4 (unit 16) shapes of the metatile whose
		//top-left cell is (col, row). False when any of them was never drawn.
		template<typename TReader>
		bool ReadMetatile(const TReader& read, int32_t col, int32_t row, int32_t step, MetatileKey& key)
		{
			key = MetatileKey();
			for(int32_t dy = 0; dy < step; dy++) {
				for(int32_t dx = 0; dx < step; dx++) {
					ShapeId shape = read(col + dx, row + dy);
					if(shape == kEmptyCell) {
						return false;
					}
					key.Tiles[(size_t)dy * step + dx] = shape;
				}
			}
			return true;
		}

		//Walks a cell rectangle through the vocabulary and emits one placement
		//per known metatile, at map pixels relative to (col0, row0).
		template<typename TReader>
		void EmitPlacements(const Vocabulary& vocab, int32_t col0, int32_t col1, int32_t row0, int32_t row1, int32_t originX, int32_t originY, const TReader& read, std::vector<SheetPlacement>& out)
		{
			int32_t step = vocab.Grid.Unit >= 16 ? 2 : 1;
			for(int32_t r = row0; r + step - 1 <= row1; r++) {
				if(step == 2 && !IsAligned(r, vocab.Grid.PhaseY)) {
					continue;
				}
				for(int32_t c = col0; c + step - 1 <= col1; c++) {
					if(step == 2 && !IsAligned(c, vocab.Grid.PhaseX)) {
						continue;
					}
					MetatileKey key;
					if(!ReadMetatile(read, c, r, step, key)) {
						continue;
					}
					int32_t index = vocab.Find(key);
					if(index < 0) {
						continue;
					}
					out.push_back({ originX + (c - col0) * 8, originY + (r - row0) * 8, (uint32_t)index });
				}
			}
		}
	}

	namespace
	{
		struct PlacedScreen
		{
			const GridFrame* Frame;
			int32_t X; //screen grid coordinates, relative to the component root
			int32_t Y;
		};

		//One distinct screen (playfield identity), however often it was visited.
		struct ScreenNode
		{
			const GridFrame* Frame = nullptr;
			uint32_t Order = 0;  //recording index of the first sighting
			uint32_t Degree = 0; //links incident on this screen
		};

		//A measured link between two screens that follow each other in the
		//recording: B sits (Sx, Sy) screens away from A.
		struct ScreenLink
		{
			uint32_t A = 0;
			uint32_t B = 0;
			int32_t Sx = 0;
			int32_t Sy = 0;
			int32_t Dx = 0;
			int32_t Dy = 0;
			double Score = 0;
			uint32_t Order = 0; //recording index of B, for the log
		};

		struct Component
		{
			std::vector<uint32_t> Nodes;
			std::vector<uint32_t> Links;
		};

		//Screen B sits one screen away from A, in the direction the content
		//moved between them (the dominant axis wins a diagonal).
		void ScreenStep(const ShiftMatch& match, int32_t& sx, int32_t& sy)
		{
			sx = Sign(match.Dx);
			sy = Sign(match.Dy);
			if(sx != 0 && sy != 0) {
				if(std::abs(match.Dx) >= std::abs(match.Dy)) {
					sy = 0;
				} else {
					sx = 0;
				}
			}
		}

		//The early-transition frames between two stable screens: mostly the
		//first one, already shifted a few cells. A frame halfway through the
		//transition is half A / half B and matches neither above kMinMatch.
		//The spike read a raw frame stream and stepped at least 2 frames in;
		//here the stream is de-duplicated (ADR-0153 §5), so a whole transition
		//can be a single entry and the first one after the anchor is already
		//"mostly A, shifted" - stepping 2 in would skip past it. Since no fixed
		//fraction of the gap fits both shapes, F9.8 probes kStitchTransitionProbes
		//of them; each one still has to carry its own evidence.
		std::vector<size_t> TransitionFrames(size_t anchorIndex, size_t screenIndex)
		{
			std::vector<size_t> probes;
			if(screenIndex < anchorIndex + 2) {
				return probes; //nothing recorded in between: a hard cut
			}
			size_t gap = screenIndex - anchorIndex;
			for(uint32_t p = 1; p <= kStitchTransitionProbes; p++) {
				size_t index = anchorIndex + std::max<size_t>(1, gap * p / (kStitchTransitionProbes + 1));
				if(index <= anchorIndex || index >= screenIndex) {
					continue;
				}
				if(std::find(probes.begin(), probes.end(), index) == probes.end()) {
					probes.push_back(index);
				}
			}
			return probes;
		}

		struct BandEvidence
		{
			double Ratio = 0;     //share of the exposed band the candidate carries
			double NullRatio = 0; //share the anchor already carried at the same cells
			uint32_t Cells = 0;
			bool Ok = false;
		};

		//The F9.8 adjacency evidence. `mid` matches the anchor at shift
		//(dx, dy) and the candidate `b` is claimed to sit one screen away in
		//direction (sx, sy). Every playfield cell of `mid` whose anchor-relative
		//position falls outside the anchor was exposed by the scroll, so it can
		//only have come from the screen moving in; mapping it one screen back
		//lands on `b`'s opposite edge. The share of those cells that `b` really
		//carries is the measurement - a hard cut has no such band at all, and a
		//band belonging to some other screen does not match.
		BandEvidence BorderBandEvidence(const GridFrame& anchor, const GridFrame& mid, const GridFrame& b, const Vocabulary& vocab, int32_t dx, int32_t dy, int32_t sx, int32_t sy)
		{
			BandEvidence evidence;
			int32_t playRows = (int32_t)PlayRows(vocab);
			int32_t firstRow = (int32_t)vocab.HudRows;
			int32_t lastRow = (int32_t)(kGridRows - vocab.HudBottomRows);
			if(playRows <= 0 || (sx == 0 && sy == 0)) {
				return evidence;
			}

			uint32_t hits = 0;
			uint32_t nulls = 0;
			uint32_t total = 0;
			for(int32_t r = firstRow; r < lastRow; r++) {
				for(int32_t c = 0; c < (int32_t)kGridCols; c++) {
					int32_t worldCol = c + dx;
					int32_t worldRow = r + dy;
					if(worldCol >= 0 && worldCol < (int32_t)kGridCols && worldRow >= firstRow && worldRow < lastRow) {
						continue; //still the anchor's own content
					}
					int32_t bCol = worldCol - sx * (int32_t)kGridCols;
					int32_t bRow = worldRow - sy * playRows;
					if(bCol < 0 || bCol >= (int32_t)kGridCols || bRow < firstRow || bRow >= lastRow) {
						continue; //two screens out: not this candidate's edge
					}
					ShapeId shape = mid.Cells[r][c];
					if(shape == kEmptyCell) {
						continue;
					}
					total++;
					hits += b.Cells[bRow][bCol] == shape ? 1 : 0;
					//The null hypothesis: the band reads the same whether or not
					//the candidate exists. A screen that is mostly one backdrop
					//tile - a Punch-Out!! card - agrees with every other screen's
					//edge, so a bare band ratio would rubber-stamp the collage.
					nulls += anchor.Cells[r][c] == shape ? 1 : 0;
				}
			}

			evidence.Cells = total;
			evidence.Ratio = total > 0 ? (double)hits / (double)total : 0;
			evidence.NullRatio = total > 0 ? (double)nulls / (double)total : 0;
			evidence.Ok = total >= kStitchMinBandCells && evidence.Ratio >= kStitchBandMatch && evidence.Ratio >= evidence.NullRatio + kStitchBandLead;
			return evidence;
		}

		//Distinct screens become nodes; a consecutive pair becomes an edge only
		//when a transition frame carries adjacency evidence for it (F9.8: a
		//shift above kMinMatch *and* a border band that is really the
		//candidate's edge). There is deliberately no single
		//anchor: on a real recording the first stable screens are the title,
		//the story crawl and the file select, none of which links to anything,
		//and anchoring on them stranded the screens that do link to each other.
		//ADR-0153 §6 asks for one map per connected region, so the graph is
		//built first and split into components afterwards.
		void BuildScreenGraph(const std::vector<GridFrame>& frames, const std::vector<const GridFrame*>& screens, const Vocabulary& vocab, std::vector<ScreenNode>& nodes, std::vector<ScreenLink>& links, std::vector<std::string>& log)
		{
			std::map<std::string, uint32_t> ids;
			std::vector<uint32_t> nodeOf(screens.size(), 0);
			for(size_t k = 0; k < screens.size(); k++) {
				std::string key = ScreenKey(*screens[k], vocab.HudRows, vocab.HudBottomRows);
				auto it = ids.find(key);
				if(it != ids.end()) {
					nodeOf[k] = it->second;
					continue;
				}
				nodeOf[k] = (uint32_t)nodes.size();
				ids[key] = nodeOf[k];
				nodes.push_back({ screens[k], (uint32_t)k, 0 });
			}

			for(size_t k = 1; k < screens.size(); k++) {
				uint32_t a = nodeOf[k - 1];
				uint32_t b = nodeOf[k];
				if(a == b) {
					continue; //the same screen twice in a row: nothing to link
				}
				size_t from = (size_t)(screens[k - 1] - frames.data());
				size_t to = (size_t)(screens[k] - frames.data());
				std::vector<size_t> probes = TransitionFrames(from, to);
				if(probes.empty()) {
					log.push_back(Format("screen %u: no transition frame (cut), no link", (uint32_t)k));
					continue;
				}

				//F9.8: the best-supported probe wins, and only if it clears the
				//evidence bar. Nothing is appended on a shift alone.
				const std::string keyA = ScreenKey(*screens[k - 1], vocab.HudRows, vocab.HudBottomRows);
				const std::string keyB = ScreenKey(*screens[k], vocab.HudRows, vocab.HudBottomRows);
				ScreenLink best;
				BandEvidence bestEvidence;
				double bestShiftScore = 0;
				for(size_t mid : probes) {
					const GridFrame& frame = frames[mid];
					if(frame.DrawnCells() < kMinDrawnCells) {
						continue; //a fade or a blank: nothing is scrolling here
					}
					//A probe identical to either endpoint is not a transition -
					//nothing has moved in yet, or everything already has.
					std::string keyMid = ScreenKey(frame, vocab.HudRows, vocab.HudBottomRows);
					if(keyMid == keyA || keyMid == keyB) {
						continue;
					}
					ShiftMatch match = BestShift(*screens[k - 1], frame, vocab.HudRows, vocab.HudBottomRows, kScreenMaxDx, kScreenMaxDy);
					if(match.Score < kMinMatch) {
						continue;
					}
					if(std::abs(match.Dx) < kStitchMinShiftCells && std::abs(match.Dy) < kStitchMinShiftCells) {
						continue; //too thin a band to be a measurement
					}
					int32_t sx = 0;
					int32_t sy = 0;
					ScreenStep(match, sx, sy);
					BandEvidence evidence = BorderBandEvidence(*screens[k - 1], frame, *screens[k], vocab, match.Dx, match.Dy, sx, sy);
					if(evidence.Ratio - evidence.NullRatio > bestEvidence.Ratio - bestEvidence.NullRatio || (!bestEvidence.Ok && evidence.Ok)) {
						bestEvidence = evidence;
						bestShiftScore = match.Score;
						best = ScreenLink{ a, b, sx, sy, match.Dx, match.Dy, match.Score, (uint32_t)k };
					}
				}

				if(!bestEvidence.Ok) {
					log.push_back(Format("screen %u: no adjacency evidence (band %.2f vs null %.2f over %u cells), no link", (uint32_t)k, bestEvidence.Ratio, bestEvidence.NullRatio, bestEvidence.Cells));
					continue;
				}
				log.push_back(Format("screen %u: shift match %.2f, border band %.2f over %u cells -> link", (uint32_t)k, bestShiftScore, bestEvidence.Ratio, bestEvidence.Cells));
				links.push_back(best);
				nodes[a].Degree++;
				nodes[b].Degree++;
			}
		}

		uint32_t DsuFind(std::vector<uint32_t>& parent, uint32_t x)
		{
			while(parent[x] != x) {
				parent[x] = parent[parent[x]];
				x = parent[x];
			}
			return x;
		}

		//Connected regions of the screen graph, nodes in first-sighting order.
		std::vector<Component> FindComponents(const std::vector<ScreenNode>& nodes, const std::vector<ScreenLink>& links)
		{
			std::vector<uint32_t> parent(nodes.size());
			for(uint32_t i = 0; i < nodes.size(); i++) {
				parent[i] = i;
			}
			for(const ScreenLink& link : links) {
				uint32_t ra = DsuFind(parent, link.A);
				uint32_t rb = DsuFind(parent, link.B);
				if(ra != rb) {
					parent[ra] = rb;
				}
			}

			std::vector<Component> components;
			std::map<uint32_t, size_t> slot;
			for(uint32_t i = 0; i < nodes.size(); i++) {
				uint32_t root = DsuFind(parent, i);
				auto it = slot.find(root);
				if(it == slot.end()) {
					slot[root] = components.size();
					components.push_back(Component());
					it = slot.find(root);
				}
				components[it->second].Nodes.push_back(i);
			}
			for(uint32_t i = 0; i < links.size(); i++) {
				components[slot[DsuFind(parent, links[i].A)]].Links.push_back(i);
			}
			return components;
		}

		//BFS from the busiest screen of the component; every traversed link
		//moves one screen in its own direction.
		std::vector<PlacedScreen> PlaceComponent(const Component& component, const std::vector<ScreenNode>& nodes, const std::vector<ScreenLink>& links, std::vector<std::string>& log)
		{
			std::map<uint32_t, std::vector<std::pair<uint32_t, uint32_t>>> adjacency;
			for(uint32_t li : component.Links) {
				adjacency[links[li].A].push_back(std::make_pair(links[li].B, li));
				adjacency[links[li].B].push_back(std::make_pair(links[li].A, li));
			}

			uint32_t start = component.Nodes[0];
			for(uint32_t n : component.Nodes) {
				if(nodes[n].Degree > nodes[start].Degree) {
					start = n;
				}
			}

			std::map<uint32_t, std::pair<int32_t, int32_t>> positions;
			std::vector<uint32_t> queue;
			positions[start] = std::make_pair(0, 0);
			queue.push_back(start);
			log.push_back(Format("screen %u: component root, placed at (0,0)", nodes[start].Order));
			for(size_t qi = 0; qi < queue.size(); qi++) {
				uint32_t current = queue[qi];
				for(const std::pair<uint32_t, uint32_t>& edge : adjacency[current]) {
					if(positions.find(edge.first) != positions.end()) {
						continue;
					}
					const ScreenLink& link = links[edge.second];
					int32_t sx = link.A == current ? link.Sx : -link.Sx;
					int32_t sy = link.A == current ? link.Sy : -link.Sy;
					int32_t x = positions[current].first + sx;
					int32_t y = positions[current].second + sy;
					positions[edge.first] = std::make_pair(x, y);
					queue.push_back(edge.first);
					log.push_back(Format("screen %u: shift (%d,%d) match %.2f -> placed at (%d,%d)", link.Order, link.Dx, link.Dy, link.Score, x, y));
				}
			}

			std::vector<PlacedScreen> placed;
			for(uint32_t n : queue) {
				placed.push_back({ nodes[n].Frame, positions[n].first, positions[n].second });
			}
			return placed;
		}

		//Lays the placed screens out on a common canvas and walks each one's
		//playfield through the vocabulary.
		void FinishScreenMap(const std::vector<PlacedScreen>& placed, const Vocabulary& vocab, StitchedMap& map)
		{
			int32_t minX = placed[0].X;
			int32_t minY = placed[0].Y;
			int32_t maxX = minX;
			int32_t maxY = minY;
			for(const PlacedScreen& screen : placed) {
				minX = std::min(minX, screen.X);
				minY = std::min(minY, screen.Y);
				maxX = std::max(maxX, screen.X);
				maxY = std::max(maxY, screen.Y);
			}
			uint32_t playRows = PlayRows(vocab);
			map.Width = (uint32_t)(maxX - minX + 1) * kGridCols * 8;
			map.Height = (uint32_t)(maxY - minY + 1) * playRows * 8;

			int32_t lastRow = (int32_t)(kGridRows - vocab.HudBottomRows) - 1;
			for(const PlacedScreen& screen : placed) {
				const GridFrame* frame = screen.Frame;
				uint32_t hudBottom = vocab.HudBottomRows;
				auto read = [frame, hudBottom](int32_t col, int32_t row) { return ShapeAt(*frame, col, row, hudBottom); };
				int32_t originX = (screen.X - minX) * (int32_t)kGridCols * 8;
				int32_t originY = (screen.Y - minY) * (int32_t)playRows * 8;
				EmitPlacements(vocab, 0, (int32_t)kGridCols - 1, (int32_t)vocab.HudRows, lastRow, originX, originY, read, map.Placements);
			}
		}

		StitchedMap BuildComponentMap(const Component& component, const std::vector<ScreenNode>& nodes, const std::vector<ScreenLink>& links, const Vocabulary& vocab, const std::string& summary)
		{
			StitchedMap map;
			map.Mode = StitchMode::Screen;
			map.HudRows = vocab.HudRows;
			map.Log.push_back(summary);
			std::vector<PlacedScreen> placed = PlaceComponent(component, nodes, links, map.Log);
			FinishScreenMap(placed, vocab, map);
			map.Log.push_back(Format("map: %u screens, %ux%u px, %u placements", (uint32_t)placed.size(), map.Width, map.Height, (uint32_t)map.Placements.size()));
			return map;
		}

		bool BiggerComponent(const Component& a, const Component& b, const std::vector<ScreenNode>& nodes)
		{
			if(a.Nodes.size() != b.Nodes.size()) {
				return a.Nodes.size() > b.Nodes.size();
			}
			return nodes[a.Nodes[0]].Order < nodes[b.Nodes[0]].Order;
		}

		//One StitchedMap per connected region, largest first. A one-screen
		//region is never a map: with F9.8 it means no adjacency evidence was
		//found for that screen, and a map of one screen is a copy of the
		//`backgrounds/screenNNN.png` the bootstrap already writes, so it is
		//dropped even when it is all there is (see ScreenStitcher.h).
		std::vector<StitchedMap> BuildScreenMaps(const std::vector<GridFrame>& frames, const std::vector<const GridFrame*>& screens, const Vocabulary& vocab, uint32_t& outLargestScreens)
		{
			std::vector<StitchedMap> maps;
			outLargestScreens = 0;
			if(screens.empty() || frames.empty() || PlayRows(vocab) == 0) {
				return maps;
			}

			std::vector<ScreenNode> nodes;
			std::vector<ScreenLink> links;
			std::vector<std::string> graphLog;
			BuildScreenGraph(frames, screens, vocab, nodes, links, graphLog);
			std::vector<Component> components = FindComponents(nodes, links);
			std::sort(components.begin(), components.end(), [&nodes](const Component& a, const Component& b) { return BiggerComponent(a, b, nodes); });

			outLargestScreens = (uint32_t)components[0].Nodes.size();
			size_t unlinked = 0;
			for(const Component& component : components) {
				unlinked += component.Nodes.size() == 1 ? 1 : 0;
			}
			std::string summary = Format("screen stitcher: %u screens (%u distinct), %u links, %u regions, %u screens with no link", (uint32_t)screens.size(), (uint32_t)nodes.size(), (uint32_t)links.size(), (uint32_t)components.size(), (uint32_t)unlinked);

			size_t keep = 0;
			while(keep < components.size() && components[keep].Nodes.size() >= 2) {
				keep++;
			}
			for(size_t i = 0; i < keep; i++) {
				maps.push_back(BuildComponentMap(components[i], nodes, links, vocab, summary));
			}
			if(!maps.empty()) {
				maps[0].Log.insert(maps[0].Log.end(), graphLog.begin(), graphLog.end());
			}
			return maps;
		}
	}

	StitchedMap StitchScreens(const std::vector<GridFrame>& frames, const std::vector<const GridFrame*>& screens, const Vocabulary& vocab)
	{
		uint32_t largest = 0;
		std::vector<StitchedMap> maps = BuildScreenMaps(frames, screens, vocab, largest);
		if(!maps.empty()) {
			return maps[0]; //the largest connected region
		}
		StitchedMap map;
		map.Mode = StitchMode::Screen;
		map.HudRows = vocab.HudRows;
		map.Log.push_back("screen stitcher: no stable screen to work with");
		return map;
	}

	namespace
	{
		//(world column, cell row) -> shape. Ordered, so the column extents of a
		//region are just the first and last key.
		using World = std::map<std::pair<int32_t, int32_t>, ShapeId>;

		//First writer wins: the earliest sample of a column is the one that saw
		//it without the sprite overlap of a later pass.
		void PaintFrame(const GridFrame& frame, int32_t cum, const Vocabulary& vocab, World& world)
		{
			for(uint32_t r = vocab.HudRows; r < kGridRows - vocab.HudBottomRows; r++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					ShapeId shape = frame.Cells[r][c];
					if(shape != kEmptyCell) {
						world.emplace(std::make_pair((int32_t)c + cum, (int32_t)r), shape);
					}
				}
			}
		}

		StitchedMap CloseRegion(const World& world, const Vocabulary& vocab, std::vector<std::string>& log)
		{
			StitchedMap map;
			map.Mode = StitchMode::Continuous;
			map.HudRows = vocab.HudRows;
			map.Log.swap(log);
			if(world.empty()) {
				return map;
			}
			int32_t col0 = world.begin()->first.first;
			int32_t col1 = world.rbegin()->first.first;
			map.Width = (uint32_t)(col1 - col0 + 1) * 8;
			map.Height = PlayRows(vocab) * 8;

			auto read = [&world](int32_t col, int32_t row) {
				auto it = world.find(std::make_pair(col, row));
				return it == world.end() ? kEmptyCell : it->second;
			};
			int32_t lastRow = (int32_t)(kGridRows - vocab.HudBottomRows) - 1;
			EmitPlacements(vocab, col0, col1, (int32_t)vocab.HudRows, lastRow, 0, 0, read, map.Placements);
			map.Log.push_back(Format("continuous region: %u px wide, %u placements", map.Width, (uint32_t)map.Placements.size()));
			return map;
		}
	}

	std::vector<StitchedMap> StitchContinuous(const std::vector<GridFrame>& frames, const Vocabulary& vocab, uint32_t frameStep)
	{
		std::vector<StitchedMap> maps;
		uint32_t step = frameStep > 0 ? frameStep : 1;
		if(frames.empty() || PlayRows(vocab) == 0) {
			return maps;
		}

		World world;
		std::vector<std::string> log;
		int32_t cum = 0;
		uint32_t unsupported = 0;
		const GridFrame* prev = nullptr;
		for(size_t i = 0; i < frames.size(); i += step) {
			const GridFrame& frame = frames[i];
			if(frame.DrawnCells() < kMinDrawnCells) {
				continue;
			}
			if(prev != nullptr) {
				double stillScore = 0;
				ShiftMatch match = BestShiftX(*prev, frame, vocab.HudRows, vocab.HudBottomRows, kContinuousMaxDx, stillScore);
				//F9.8: an offset that cannot beat "the camera did not move" is
				//not a measurement, so the frame is painted where the previous
				//one was. F9.12 reads the same test the other way round: a step
				//that does not claim a shift claims *the same place*, and is
				//judged on the still score against the stricter bar.
				bool moved = match.Dx != 0 && match.Score >= stillScore + kStitchStillMargin;
				double score = moved ? match.Score : stillScore;
				double bar = moved ? kMinMatch : kStitchWorldAgree;
				if(score < bar) {
					if(unsupported > 0) {
						log.push_back(Format("%u frame(s) shifted no better than standing still, painted in place", unsupported));
						unsupported = 0;
					}
					//F9.12: the two messages are worth telling apart in the run
					//log - one is "the camera outran the sampling", the other is
					//"this is not the same place any more".
					if(moved) {
						log.push_back(Format("frame %u: match %.2f < %.2f, cut -> new region", frame.FrameNumber, score, bar));
					} else {
						log.push_back(Format("frame %u: standing still but only %.2f of the playfield agrees, world replaced, cut -> new region", frame.FrameNumber, score));
					}
					maps.push_back(CloseRegion(world, vocab, log));
					world.clear();
					log.clear();
					cum = 0;
				} else if(!moved) {
					//Counted, not logged per frame - a long still stretch would
					//drown the log. Only an argmax that was disbelieved is worth
					//counting; a plain dx == 0 is just a still frame.
					unsupported += match.Dx != 0 ? 1 : 0;
				} else {
					cum += match.Dx;
				}
			}
			PaintFrame(frame, cum, vocab, world);
			prev = &frame;
		}
		if(unsupported > 0) {
			log.push_back(Format("%u frame(s) shifted no better than standing still, painted in place", unsupported));
		}
		maps.push_back(CloseRegion(world, vocab, log));

		maps.erase(std::remove_if(maps.begin(), maps.end(), [](const StitchedMap& m) { return m.Width == 0; }), maps.end());
		return maps;
	}

	std::vector<StitchedMap> BuildMaps(const std::vector<GridFrame>& frames, const std::vector<const GridFrame*>& screens, const Vocabulary& vocab)
	{
		uint32_t largestRegion = 0;
		std::vector<StitchedMap> screenMaps = BuildScreenMaps(frames, screens, vocab, largestRegion);
		screenMaps.erase(std::remove_if(screenMaps.begin(), screenMaps.end(), [](const StitchedMap& m) { return m.Placements.empty(); }), screenMaps.end());
		if(largestRegion >= 2) {
			return screenMaps;
		}

		//ADR-0153 §6: the screen stitcher found no connected region, so try
		//the scroller.
		std::vector<StitchedMap> regions = StitchContinuous(frames, vocab, kDefaultFrameStep);
		regions.erase(std::remove_if(regions.begin(), regions.end(), [](const StitchedMap& m) {
			return m.Width <= kContinuousMinWidth || m.Placements.empty();
		}), regions.end());
		if(!regions.empty()) {
			return regions;
		}

		//Neither mode found evidence-backed geometry, so there is no map. F9.8
		//deliberately does not fall back to one map per screen: see
		//ScreenStitcher.h. (screenMaps is empty here by construction.)
		return screenMaps;
	}
}

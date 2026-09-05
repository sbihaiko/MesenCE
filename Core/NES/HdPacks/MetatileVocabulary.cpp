//ADR-0153 §1/§3 (Phase 9, slice F9.1). Port of the offline prototype
//scripts/spike_tile_sheets.py (`stable_screens`, `grid_hash`, `frame_grid`,
//`metatiles`) into a host-free Core module. No pch.h, no Emulator, no I/O.
#include "NES/HdPacks/MetatileVocabulary.h"
#include <algorithm>
#include <set>
#include <utility>

namespace MesenSheets
{
	//The spike's --min-stable default: a quarter second of held picture.
	static constexpr uint32_t kDefaultMinStableFrames = 15;
	//A whole-screen static image would otherwise make the entire frame "HUD".
	static constexpr uint32_t kMaxHudRows = 6;
	//Fallback vocabulary source when the game never holds still.
	static constexpr size_t kMaxFallbackScreens = 64;
	//A screen must have at least half the playfield drawn to be worth keeping.
	static constexpr uint32_t kMinDrawnCells = kGridRows * kGridCols / 2;

	//One vocabulary entry while it is still being accumulated.
	struct Observation
	{
		uint32_t Count = 0;
		bool AllHud = true;  //every observation sat inside the HUD band
		bool Aligned = false; //seen at least once at the chosen phase
	};

	using KeyPair = std::pair<MetatileKey, MetatileKey>;
	using Placements = std::map<std::pair<uint32_t, uint32_t>, MetatileKey>;

	//---- screen selection --------------------------------------------------

	//Raw cell bytes: the identity of a screen inside an ordered container.
	static std::string ScreenKey(const GridFrame& frame)
	{
		return std::string((const char*)frame.Cells, sizeof(frame.Cells));
	}

	//Keeps the first occurrence of every distinct grid, in input order.
	static std::vector<const GridFrame*> DistinctOnly(const std::vector<const GridFrame*>& screens)
	{
		std::set<std::string> seen;
		std::vector<const GridFrame*> out;
		for(const GridFrame* frame : screens) {
			if(seen.insert(ScreenKey(*frame)).second) {
				out.push_back(frame);
			}
		}
		return out;
	}

	//A game that never holds still still deserves a vocabulary: the distinct
	//frames with the most drawn cells, capped, back in recording order.
	static std::vector<const GridFrame*> BusiestFrames(const std::vector<GridFrame>& frames)
	{
		std::vector<const GridFrame*> all;
		for(const GridFrame& frame : frames) {
			all.push_back(&frame);
		}
		all = DistinctOnly(all);

		std::vector<std::pair<uint32_t, size_t>> ranked;
		for(size_t i = 0; i < all.size(); i++) {
			ranked.emplace_back(all[i]->DrawnCells(), i);
		}
		std::stable_sort(ranked.begin(), ranked.end(), [](const std::pair<uint32_t, size_t>& a, const std::pair<uint32_t, size_t>& b) {
			return a.first > b.first;
		});
		if(ranked.size() > kMaxFallbackScreens) {
			ranked.resize(kMaxFallbackScreens);
		}
		std::sort(ranked.begin(), ranked.end(), [](const std::pair<uint32_t, size_t>& a, const std::pair<uint32_t, size_t>& b) {
			return a.second < b.second;
		});

		std::vector<const GridFrame*> out;
		for(const std::pair<uint32_t, size_t>& entry : ranked) {
			out.push_back(all[entry.second]);
		}
		return out;
	}

	std::vector<const GridFrame*> SelectStableScreens(const std::vector<GridFrame>& frames, uint32_t minStableFrames, uint32_t& distinctOut)
	{
		std::vector<const GridFrame*> kept;
		size_t i = 0;
		while(i < frames.size()) {
			//The recorder collapses duplicates, so a run is normally one entry
			//carrying RepeatCount; a fixture may still hold literal repeats, so
			//sum the run either way and both forms give the same vocabulary.
			size_t j = i;
			uint32_t held = frames[i].RepeatCount;
			while(j + 1 < frames.size() && frames[j + 1].SameCells(frames[i])) {
				j++;
				held += frames[j].RepeatCount;
			}
			if(held >= minStableFrames && frames[i].DrawnCells() >= kMinDrawnCells) {
				kept.push_back(&frames[i]);
			}
			i = j + 1;
		}
		if(kept.size() < 2) {
			kept = BusiestFrames(frames);
		}
		distinctOut = (uint32_t)DistinctOnly(kept).size();
		return kept;
	}

	//---- HUD detection -----------------------------------------------------

	//Rows scanned from `start` in direction `step` that belong to a status bar;
	//stops at the first row that does not.
	//
	//Two relaxations of "identical on every screen", both forced by measurement:
	//
	// - Byte-identity per column is too strict for a real HUD: a score, a timer
	//   and a life counter all change while the labels around them do not, so
	//   Super Mario Bros. and Contra reported zero HUD rows and spilled their
	//   digits into the scene sheet. A row needs only kHudRowFrozenRatio of its
	//   columns to hold still, and enough drawn cells (kHudRowDrawnRatio) to be
	//   a status bar rather than a stretch of sky that matches everywhere.
	//
	// - Agreement across *all* screens is too strict as well, because the screen
	//   set is a whole recording: a title screen, a menu and a game-over card sit
	//   next to the gameplay screens and share no row with them. Excitebike's
	//   gauge bar and Metroid's energy bar were invisible for exactly that
	//   reason. A column now holds still when its most common shape covers
	//   kHudRowScreenAgreement of the screens, which is the same test as before
	//   at agreement 1.0 and tolerates a minority of unrelated screens below it.
	static uint32_t CountFrozenRows(const std::vector<const GridFrame*>& screens, int32_t start, int32_t step)
	{
		uint32_t rows = 0;
		uint32_t quorum = (uint32_t)(kHudRowScreenAgreement * screens.size());
		if(quorum < 2) {
			quorum = 2;
		}
		for(int32_t r = start; r >= 0 && r < (int32_t)kGridRows; r += step) {
			uint32_t frozen = 0;
			uint32_t drawn = 0;
			for(uint32_t c = 0; c < kGridCols; c++) {
				//Modal shape of this column across the screen set.
				std::map<ShapeId, uint32_t> votes;
				for(size_t i = 0; i < screens.size(); i++) {
					votes[screens[i]->Cells[r][c]]++;
				}
				ShapeId modal = kEmptyCell;
				uint32_t best = 0;
				for(const std::pair<const ShapeId, uint32_t>& vote : votes) {
					if(vote.second > best) {
						best = vote.second;
						modal = vote.first;
					}
				}
				if(best < quorum) {
					continue;
				}
				frozen++;
				drawn += modal != kEmptyCell ? 1 : 0;
			}
			bool blank = drawn == 0 && frozen == kGridCols;
			bool statusBar = frozen >= (uint32_t)(kHudRowFrozenRatio * kGridCols)
				&& drawn >= (uint32_t)(kHudRowDrawnRatio * kGridCols);
			if(!blank && !statusBar) {
				break;
			}
			rows++;
		}
		return rows;
	}

	void DetectHudRows(const std::vector<const GridFrame*>& screensIn, uint32_t& topRows, uint32_t& bottomRows)
	{
		topRows = 0;
		bottomRows = 0;

		//A single screen is trivially identical to itself on every row.
		std::vector<const GridFrame*> screens = DistinctOnly(screensIn);
		if(screens.size() < 2) {
			return;
		}

		uint32_t top = CountFrozenRows(screens, 0, 1);
		if(top >= kGridRows) {
			return; //nothing ever moves: a static image, not a HUD
		}
		uint32_t bottom = CountFrozenRows(screens, (int32_t)kGridRows - 1, -1);
		top = std::min(top, kMaxHudRows);
		bottom = std::min(bottom, kMaxHudRows);
		if(top + bottom >= kGridRows) {
			return;
		}
		topRows = top;
		bottomRows = bottom;
	}

	//---- grid detection ----------------------------------------------------

	//The 2x2 tuple whose top-left cell is (col, row); false when any of the
	//four cells is empty or the tuple would leave the grid.
	static bool MakeMetatile(const GridFrame& frame, uint32_t col, uint32_t row, MetatileKey& out)
	{
		if(col + 1 >= kGridCols || row + 1 >= kGridRows) {
			return false;
		}
		ShapeId ids[4] = { frame.Cells[row][col], frame.Cells[row][col + 1], frame.Cells[row + 1][col], frame.Cells[row + 1][col + 1] };
		for(uint32_t i = 0; i < 4; i++) {
			if(ids[i] == kEmptyCell) {
				return false;
			}
		}
		for(uint32_t i = 0; i < 4; i++) {
			out.Tiles[i] = ids[i];
		}
		return true;
	}

	//Grid unit 8: a cell is its own one-tile "metatile".
	static bool MakeSingle(const GridFrame& frame, uint32_t col, uint32_t row, MetatileKey& out)
	{
		if(frame.Cells[row][col] == kEmptyCell) {
			return false;
		}
		out.Tiles = { frame.Cells[row][col], kEmptyCell, kEmptyCell, kEmptyCell };
		return true;
	}

	//Every 2x2 placement of one phase over one screen's playfield.
	static void CollectPhase(const GridFrame& frame, uint32_t phaseX, uint32_t phaseY, uint32_t firstRow, uint32_t lastRow, std::map<MetatileKey, uint32_t>& counts, std::vector<MetatileKey>& placements)
	{
		for(uint32_t r = firstRow; r + 1 <= lastRow; r++) {
			if((r % 2) != phaseY) {
				continue;
			}
			for(uint32_t c = 0; c + 1 < kGridCols; c++) {
				if((c % 2) != phaseX) {
					continue;
				}
				MetatileKey key;
				if(MakeMetatile(frame, c, r, key)) {
					counts[key]++;
					placements.push_back(key);
				}
			}
		}
	}

	//ADR-0153 §1: placements whose tuple was seen often enough, over all of them.
	static double Consistency(const std::map<MetatileKey, uint32_t>& counts, const std::vector<MetatileKey>& placements)
	{
		if(placements.empty()) {
			return 0;
		}
		uint32_t consistent = 0;
		for(const MetatileKey& key : placements) {
			std::map<MetatileKey, uint32_t>::const_iterator it = counts.find(key);
			if(it != counts.end() && it->second >= kGridConsistencyMinCount) {
				consistent++;
			}
		}
		return (double)consistent / (double)placements.size();
	}

	//The same self-consistency measure at unit 8: one cell, no phase.
	static double SingleCellConsistency(const std::vector<const GridFrame*>& screens, uint32_t firstRow, uint32_t lastRow)
	{
		std::map<ShapeId, uint32_t> counts;
		std::vector<ShapeId> placements;
		for(const GridFrame* frame : screens) {
			for(uint32_t r = firstRow; r <= lastRow && r < kGridRows; r++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					ShapeId id = frame->Cells[r][c];
					if(id != kEmptyCell) {
						counts[id]++;
						placements.push_back(id);
					}
				}
			}
		}
		if(placements.empty()) {
			return 0;
		}
		uint32_t consistent = 0;
		for(ShapeId id : placements) {
			consistent += counts[id] >= kGridConsistencyMinCount ? 1 : 0;
		}
		return (double)consistent / (double)placements.size();
	}

	//What one phase looks like over the whole playfield.
	struct PhaseStat
	{
		size_t Distinct = 0;
		size_t Placements = 0;
		double Consistency = 0;
	};

	static PhaseStat MeasurePhase(const std::vector<const GridFrame*>& screens, uint32_t phaseX, uint32_t phaseY, uint32_t firstRow, uint32_t lastRow)
	{
		std::map<MetatileKey, uint32_t> counts;
		std::vector<MetatileKey> placements;
		for(const GridFrame* frame : screens) {
			CollectPhase(*frame, phaseX, phaseY, firstRow, lastRow, counts, placements);
		}
		PhaseStat stat;
		stat.Distinct = counts.size();
		stat.Placements = placements.size();
		stat.Consistency = Consistency(counts, placements);
		return stat;
	}

	//ADR-0153 §1 (amended): a real grid has one parity whose vocabulary is
	//markedly smaller than the other three; without a grid the four phases are
	//interchangeable. Measured 0.28 on Zelda, 0.02 on Excitebike.
	static double MeasureAdvantage(const PhaseStat stats[4], uint32_t best)
	{
		double others = 0;
		for(uint32_t p = 0; p < 4; p++) {
			if(p != best) {
				others += (double)stats[p].Distinct;
			}
		}
		others /= 3.0;
		return others > 0 ? 1.0 - (double)stats[best].Distinct / others : 0;
	}

	GridDetection DetectGrid(const std::vector<const GridFrame*>& screensIn, uint32_t hudRows, uint32_t hudBottomRows)
	{
		static const uint8_t phases[4][2] = { { 0, 0 }, { 1, 0 }, { 0, 1 }, { 1, 1 } };

		GridDetection detection;
		std::vector<const GridFrame*> screens = DistinctOnly(screensIn);
		uint32_t firstRow = std::min(hudRows, kGridRows - 1);
		uint32_t lastRow = hudBottomRows < kGridRows ? kGridRows - hudBottomRows - 1 : 0;

		//The winner is the phase with the fewest distinct tuples, not the most
		//self-consistent one: consistency saturates and is not even stable.
		PhaseStat stats[4];
		uint32_t best = 0;
		for(uint32_t p = 0; p < 4; p++) {
			stats[p] = MeasurePhase(screens, phases[p][0], phases[p][1], firstRow, lastRow);
			detection.PhaseScores[p] = stats[p].Consistency;
			if(stats[p].Distinct < stats[best].Distinct) {
				best = p;
			}
		}
		detection.PhaseAdvantage = MeasureAdvantage(stats, best);
		detection.HasGrid = detection.PhaseAdvantage >= kGridPhaseAdvantage;
		detection.Alt8x8 = SingleCellConsistency(screens, firstRow, lastRow);

		if(stats[best].Placements < kMinMetatilePlacements) {
			//Essentially text and menus: there is nothing to cut into blocks.
			detection.Unit = 8;
			detection.PhaseX = 0;
			detection.PhaseY = 0;
			detection.ChosenConsistency = detection.Alt8x8;
			return detection;
		}

		//16 either way; without a privileged parity the cut is arbitrary, so
		//take (0,0) and say so through HasGrid.
		uint32_t chosen = detection.HasGrid ? best : 0;
		detection.Unit = 16;
		detection.PhaseX = phases[chosen][0];
		detection.PhaseY = phases[chosen][1];
		detection.ChosenConsistency = detection.PhaseScores[chosen];
		return detection;
	}

	//---- vocabulary --------------------------------------------------------

	//One screen's placements at the given phase, over the *whole* frame - the
	//HUD included, since hud/font sheets come out of the same vocabulary.
	static void CollectScreen(const GridFrame& frame, const GridDetection& grid, uint32_t phaseX, uint32_t phaseY, Placements& out)
	{
		uint32_t step = grid.Unit == 16 ? 2 : 1;
		for(uint32_t r = 0; r + step <= kGridRows; r++) {
			if(step == 2 && (r % 2) != phaseY) {
				continue;
			}
			for(uint32_t c = 0; c + step <= kGridCols; c++) {
				if(step == 2 && (c % 2) != phaseX) {
					continue;
				}
				MetatileKey key;
				bool ok = step == 2 ? MakeMetatile(frame, c, r, key) : MakeSingle(frame, c, r, key);
				if(ok) {
					out[std::make_pair(r, c)] = key;
				}
			}
		}
	}

	//A metatile is "in the HUD" only when every row it covers is frozen.
	static bool InHudBand(uint32_t row, uint32_t span, uint32_t hudTop, uint32_t hudBottom)
	{
		if(row + span <= hudTop) {
			return true;
		}
		return hudBottom > 0 && row >= kGridRows - hudBottom;
	}

	//Folds one screen's placements into the observation map and the E/S counts.
	static void AccumulateScreen(const Placements& placements, uint32_t step, uint32_t hudTop, uint32_t hudBottom, bool aligned, std::map<MetatileKey, Observation>& obs, std::map<KeyPair, uint32_t>* east, std::map<KeyPair, uint32_t>* south)
	{
		for(Placements::const_iterator it = placements.begin(); it != placements.end(); ++it) {
			uint32_t row = it->first.first;
			uint32_t col = it->first.second;
			Observation& o = obs[it->second];
			o.Count++;
			o.Aligned = o.Aligned || aligned;
			o.AllHud = o.AllHud && InHudBand(row, step, hudTop, hudBottom);
			if(!east || !south) {
				continue;
			}
			Placements::const_iterator e = placements.find(std::make_pair(row, col + step));
			if(e != placements.end()) {
				(*east)[std::make_pair(it->second, e->second)]++;
			}
			Placements::const_iterator s = placements.find(std::make_pair(row + step, col));
			if(s != placements.end()) {
				(*south)[std::make_pair(it->second, s->second)]++;
			}
		}
	}

	//How many of the four NES colour indexes a tile's 64 pixels actually use.
	static uint32_t DistinctColorCount(const SheetTileKey& tile)
	{
		bool used[4] = {};
		for(uint32_t y = 0; y < 8; y++) {
			uint8_t lo = tile.TileData[y];
			uint8_t hi = tile.TileData[y + 8];
			for(uint32_t x = 0; x < 8; x++) {
				uint8_t bit = (uint8_t)(7 - x);
				used[((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)] = true;
			}
		}
		return (uint32_t)(used[0] + used[1] + used[2] + used[3]);
	}

	//A glyph: every drawn tile of the cell uses at most 2 colour indexes
	//(ADR-0153 §3). Shapes the lookup cannot resolve carry no pixels, so they
	//neither prove nor disprove the test.
	static bool IsFontCell(const MetatileKey& key, const TileLookup& lookup)
	{
		if(!lookup) {
			return false;
		}
		for(ShapeId id : key.Tiles) {
			if(id == kEmptyCell) {
				continue;
			}
			const SheetTileKey* tile = lookup(id);
			if(tile && DistinctColorCount(*tile) > 2) {
				return false;
			}
		}
		return true;
	}

	//ADR-0153 §3, in order: misc, then hud, then font (font wins), else scene.
	//Rarity alone no longer means misc - MarkIsolatedAsMisc has the second
	//half of the rule, once the adjacency map exists to test it against.
	static SheetContext Classify(const Observation& obs, const MetatileKey& key, const TileLookup& lookup)
	{
		if(!obs.Aligned) {
			return SheetContext::Misc;
		}
		if(!obs.AllHud) {
			return SheetContext::Scene;
		}
		return IsFontCell(key, lookup) ? SheetContext::Font : SheetContext::Hud;
	}

	//Descending count, ties broken by key, so sheet order never wobbles.
	static bool ByCountThenKey(const MetatileEntry& a, const MetatileEntry& b)
	{
		return a.Count != b.Count ? a.Count > b.Count : a.Key < b.Key;
	}

	//Observation map -> sorted entries + index, contexts resolved.
	static void BuildEntries(const std::map<MetatileKey, Observation>& obs, const TileLookup& lookup, Vocabulary& vocab)
	{
		for(std::map<MetatileKey, Observation>::const_iterator it = obs.begin(); it != obs.end(); ++it) {
			MetatileEntry entry;
			entry.Key = it->first;
			entry.Count = it->second.Count;
			entry.Aligned = it->second.Aligned;
			entry.Context = Classify(it->second, it->first, lookup);
			vocab.Entries.push_back(entry);
		}
		std::sort(vocab.Entries.begin(), vocab.Entries.end(), ByCountThenKey);
		for(uint32_t i = 0; i < (uint32_t)vocab.Entries.size(); i++) {
			vocab.Index[vocab.Entries[i].Key] = i;
		}
	}

	//Key-keyed adjacency counts -> index-keyed, once the order is final.
	static void RemapAdjacency(const std::map<KeyPair, uint32_t>& counts, const Vocabulary& vocab, AdjacencyMap& out)
	{
		for(std::map<KeyPair, uint32_t>::const_iterator it = counts.begin(); it != counts.end(); ++it) {
			int32_t a = vocab.Find(it->first.first);
			int32_t b = vocab.Find(it->first.second);
			if(a >= 0 && b >= 0) {
				out[std::make_pair((uint32_t)a, (uint32_t)b)] += it->second;
			}
		}
	}

	//Every shape the chosen grid already covers; anything else would vanish
	//from the sheets entirely.
	static std::set<ShapeId> CoveredShapes(const std::map<MetatileKey, Observation>& obs)
	{
		std::set<ShapeId> covered;
		for(std::map<MetatileKey, Observation>::const_iterator it = obs.begin(); it != obs.end(); ++it) {
			for(ShapeId id : it->first.Tiles) {
				if(id != kEmptyCell) {
					covered.insert(id);
				}
			}
		}
		return covered;
	}

	//Every tuple of the three losing phases, but only where it is the sole
	//witness of a shape the chosen grid never covers. Cataloguing all of them
	//would bury the noise budget in sampling artefacts, not vocabulary.
	static void CollectOrphanCandidates(const std::vector<const GridFrame*>& screens, const GridDetection& grid, uint32_t hudTop, uint32_t hudBottom, const std::set<ShapeId>& covered, std::map<MetatileKey, Observation>& offPhase)
	{
		for(uint32_t p = 0; p < 4; p++) {
			uint32_t phaseX = p % 2;
			uint32_t phaseY = p / 2;
			if(phaseX == grid.PhaseX && phaseY == grid.PhaseY) {
				continue;
			}
			for(const GridFrame* frame : screens) {
				Placements all;
				CollectScreen(*frame, grid, phaseX, phaseY, all);
				Placements orphans;
				for(Placements::const_iterator it = all.begin(); it != all.end(); ++it) {
					for(ShapeId id : it->second.Tiles) {
						if(id != kEmptyCell && covered.find(id) == covered.end()) {
							orphans[it->first] = it->second;
							break;
						}
					}
				}
				AccumulateScreen(orphans, 2, hudTop, hudBottom, false, offPhase, nullptr, nullptr);
			}
		}
	}

	//One entry per orphan shape: the metatile that contains it most often
	//(ties broken by key, so the pick never wobbles).
	static void KeepBestPerOrphan(const std::map<MetatileKey, Observation>& offPhase, const std::set<ShapeId>& covered, std::map<MetatileKey, Observation>& obs)
	{
		std::map<ShapeId, MetatileKey> best;
		for(std::map<MetatileKey, Observation>::const_iterator it = offPhase.begin(); it != offPhase.end(); ++it) {
			for(ShapeId id : it->first.Tiles) {
				if(id == kEmptyCell || covered.find(id) != covered.end()) {
					continue;
				}
				std::map<ShapeId, MetatileKey>::iterator cur = best.find(id);
				if(cur == best.end() || offPhase.at(cur->second).Count < it->second.Count) {
					best[id] = it->first;
				}
			}
		}
		for(std::map<ShapeId, MetatileKey>::const_iterator it = best.begin(); it != best.end(); ++it) {
			if(obs.find(it->second) == obs.end()) {
				obs[it->second] = offPhase.at(it->second);
			}
		}
	}

	//Vocabulary indexes that sit E or S of a common scene cell, either way round.
	static void NeighbouredByScene(const AdjacencyMap& adjacency, const std::set<uint32_t>& scene, std::set<uint32_t>& out)
	{
		for(AdjacencyMap::const_iterator it = adjacency.begin(); it != adjacency.end(); ++it) {
			uint32_t a = it->first.first;
			uint32_t b = it->first.second;
			if(scene.find(a) != scene.end()) {
				out.insert(b);
			}
			if(scene.find(b) != scene.end()) {
				out.insert(a);
			}
		}
	}

	//ADR-0153 §3 (amended): a rare cell is noise only when it belongs nowhere.
	//A bush seen once but ringed by sand is scene; a stray "GAME OVER" is not.
	//The neighbour must be a *common* scene cell (Count > 1), which is what
	//"ringed by sand" means. Accepting any scene neighbour would rescue every
	//singleton - inside a full 30x32 screen every metatile has one - and the
	//noise budget would read 0% on every game instead of measuring anything.
	//"Scene" here is the provisional classification, which does not depend on
	//adjacency, so the test has no fixed point to chase.
	static void MarkIsolatedAsMisc(Vocabulary& vocab)
	{
		std::set<uint32_t> scene;
		for(uint32_t i = 0; i < (uint32_t)vocab.Entries.size(); i++) {
			if(vocab.Entries[i].Context == SheetContext::Scene && vocab.Entries[i].Count > 1) {
				scene.insert(i);
			}
		}
		std::set<uint32_t> neighboured;
		NeighbouredByScene(vocab.East, scene, neighboured);
		NeighbouredByScene(vocab.South, scene, neighboured);

		for(uint32_t i = 0; i < (uint32_t)vocab.Entries.size(); i++) {
			MetatileEntry& entry = vocab.Entries[i];
			if(entry.Count == 1 && neighboured.find(i) == neighboured.end()) {
				entry.Context = SheetContext::Misc;
			}
		}
	}

	//ADR-0156 (F9.9). One sighting: the cell, where it sat, under which fine
	//scroll. Position and scroll are both part of the identity because the
	//captured screen is a *positional* surface: the same cell one column to the
	//left, or the same column at another sub-tile offset, is a pixel the screen
	//PNG does not cover.
	struct Sighting
	{
		uint32_t Cell;
		uint32_t Row;
		uint32_t Col;
		uint8_t FineX;

		bool operator<(const Sighting& o) const
		{
			if(Cell != o.Cell) { return Cell < o.Cell; }
			if(Row != o.Row) { return Row < o.Row; }
			if(Col != o.Col) { return Col < o.Col; }
			return FineX < o.FineX;
		}
	};

	//Every sighting a captured frame accounts for, plus which cells any captured
	//frame shows at all.
	static void CollectCapturedSightings(const std::vector<GridFrame>& frames, const Vocabulary& vocab, std::set<Sighting>& explained, std::set<uint32_t>& shown)
	{
		for(size_t i = 0; i < frames.size(); i++) {
			if(!frames[i].Captured) {
				continue;
			}
			Placements placements;
			CollectScreen(frames[i], vocab.Grid, vocab.Grid.PhaseX, vocab.Grid.PhaseY, placements);
			for(Placements::const_iterator it = placements.begin(); it != placements.end(); ++it) {
				int32_t index = vocab.Find(it->second);
				if(index < 0) {
					continue;
				}
				Sighting sighting = { (uint32_t)index, it->first.first, it->first.second, frames[i].FineX };
				explained.insert(sighting);
				shown.insert((uint32_t)index);
			}
		}
	}

	//Cells with at least one sighting no captured frame accounts for. Those
	//pixels do reach the screen through their tile art, so the cell has to stay
	//on the contact sheet whatever else is true of it.
	static void CollectUnexplained(const std::vector<GridFrame>& frames, const Vocabulary& vocab, const std::set<Sighting>& explained, std::set<uint32_t>& unexplained)
	{
		for(size_t i = 0; i < frames.size(); i++) {
			if(frames[i].Captured) {
				continue;
			}
			Placements placements;
			CollectScreen(frames[i], vocab.Grid, vocab.Grid.PhaseX, vocab.Grid.PhaseY, placements);
			for(Placements::const_iterator it = placements.begin(); it != placements.end(); ++it) {
				int32_t index = vocab.Find(it->second);
				if(index < 0) {
					continue;
				}
				Sighting sighting = { (uint32_t)index, it->first.first, it->first.second, frames[i].FineX };
				if(explained.find(sighting) == explained.end()) {
					unexplained.insert((uint32_t)index);
				}
			}
		}
	}

	void MarkScreenResidentCells(const std::vector<GridFrame>& frames, Vocabulary& vocab)
	{
		std::set<Sighting> explained;
		std::set<uint32_t> shown;
		CollectCapturedSightings(frames, vocab, explained, shown);
		if(shown.empty()) {
			return; //nothing was captured: there is no screen surface to route to
		}
		std::set<uint32_t> unexplained;
		CollectUnexplained(frames, vocab, explained, unexplained);

		for(uint32_t i = 0; i < (uint32_t)vocab.Entries.size(); i++) {
			MetatileEntry& entry = vocab.Entries[i];
			//Scene only. hud/font are legibility surfaces of their own (a status
			//bar sits inside every captured screen, so the test would empty
			//them), and misc is the noise budget PRD Phase 9 test 7 measures.
			if(entry.Context != SheetContext::Scene) {
				continue;
			}
			entry.ScreenResident = shown.find(i) != shown.end() && unexplained.find(i) == unexplained.end();
		}
	}

	//Second pass at unit 16 (ADR-0153 §3 "unaligned"): rescue the shapes the
	//chosen phase never covers, nothing more.
	static void CollectOffPhase(const std::vector<const GridFrame*>& screens, const GridDetection& grid, uint32_t hudTop, uint32_t hudBottom, std::map<MetatileKey, Observation>& obs)
	{
		std::set<ShapeId> covered = CoveredShapes(obs);
		std::map<MetatileKey, Observation> offPhase;
		CollectOrphanCandidates(screens, grid, hudTop, hudBottom, covered, offPhase);
		KeepBestPerOrphan(offPhase, covered, obs);
	}

	Vocabulary BuildVocabulary(const std::vector<GridFrame>& frames, const TileLookup& lookup)
	{
		Vocabulary vocab;
		uint32_t distinct = 0;
		std::vector<const GridFrame*> kept = SelectStableScreens(frames, kDefaultMinStableFrames, distinct);
		vocab.StableScreens = (uint32_t)kept.size();
		vocab.DistinctScreens = distinct;

		std::vector<const GridFrame*> screens = DistinctOnly(kept);
		DetectHudRows(screens, vocab.HudRows, vocab.HudBottomRows);
		vocab.Grid = DetectGrid(screens, vocab.HudRows, vocab.HudBottomRows);

		uint32_t step = vocab.Grid.Unit == 16 ? 2 : 1;
		std::map<MetatileKey, Observation> obs;
		std::map<KeyPair, uint32_t> east;
		std::map<KeyPair, uint32_t> south;
		for(const GridFrame* frame : screens) {
			Placements placements;
			CollectScreen(*frame, vocab.Grid, vocab.Grid.PhaseX, vocab.Grid.PhaseY, placements);
			AccumulateScreen(placements, step, vocab.HudRows, vocab.HudBottomRows, true, obs, &east, &south);
		}
		if(vocab.Grid.Unit == 16) {
			CollectOffPhase(screens, vocab.Grid, vocab.HudRows, vocab.HudBottomRows, obs);
		}

		BuildEntries(obs, lookup, vocab);
		RemapAdjacency(east, vocab, vocab.East);
		RemapAdjacency(south, vocab, vocab.South);
		MarkIsolatedAsMisc(vocab);
		//After the contexts are final: residency is a scene-cell decision, and
		//MarkIsolatedAsMisc is what makes a cell stop being a scene cell.
		MarkScreenResidentCells(frames, vocab);
		return vocab;
	}
}

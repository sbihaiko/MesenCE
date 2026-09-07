//ADR-0153 §2 (Phase 9, F9.5) - see SpriteGrouping.h. Stateful partner: HdPackBuilder.
#include "NES/HdPacks/SpriteGrouping.h"
#include "NES/HdPacks/SheetGrouping.h"
#include <algorithm>
#include <cstdlib>
#include <set>
#include <utility>

namespace MesenSheets
{
	namespace
	{
		using Offset = std::pair<int32_t, int32_t>;
		using PairKey = std::pair<uint32_t, uint32_t>;

		MetatileKey SpriteKey(ShapeId shape)
		{
			MetatileKey key;
			key.Tiles[0] = shape;
			return key;
		}

		//Cell coordinates for a pixel offset, rounded to the nearest 8x8 cell.
		//The sheet is a legibility surface with a gutter between cells, so an
		//odd-pixel metasprite offset (Excitebike's rider sits a few pixels above
		//the bike, not a whole tile) is worth rounding rather than dropping.
		int32_t ToCells(int32_t pixels)
		{
			return (pixels + (pixels >= 0 ? 4 : -4)) / 8;
		}

		char DirOf(int32_t dx, int32_t dy)
		{
			if(std::abs(dx) >= std::abs(dy)) {
				return dx >= 0 ? 'E' : 'W';
			}
			return dy >= 0 ? 'S' : 'N';
		}

		//Instances per shape and, per ordered shape pair, how often each exact
		//relative offset was seen. Both are counted once per *recorded* frame:
		//RepeatCount is deliberately ignored, so a paused screen cannot
		//manufacture the minimum count the criterion asks for.
		struct SpriteStats
		{
			std::map<uint32_t, uint32_t> Appearances;
			std::map<PairKey, std::map<Offset, uint32_t>> Offsets;
		};

		SpriteStats Accumulate(const std::vector<OamFrame>& frames, const Vocabulary& vocab)
		{
			SpriteStats stats;
			for(const OamFrame& frame : frames) {
				std::vector<int32_t> cells;
				cells.reserve(frame.Entries.size());
				for(const OamEntry& entry : frame.Entries) {
					cells.push_back(vocab.Find(SpriteKey(entry.Shape)));
				}
				for(size_t i = 0; i < cells.size(); i++) {
					if(cells[i] < 0) {
						continue;
					}
					stats.Appearances[(uint32_t)cells[i]]++;
					for(size_t j = 0; j < cells.size(); j++) {
						//A single vocabulary cell cannot hold two positions in a
						//group, so a shape paired with itself is not an edge.
						if(i == j || cells[j] < 0 || cells[i] == cells[j]) {
							continue;
						}
						int32_t dx = (int32_t)frame.Entries[j].X - (int32_t)frame.Entries[i].X;
						int32_t dy = (int32_t)frame.Entries[j].Y - (int32_t)frame.Entries[i].Y;
						if(std::abs(dx) > kSpriteMaxOffset || std::abs(dy) > kSpriteMaxOffset) {
							continue;
						}
						stats.Offsets[PairKey((uint32_t)cells[i], (uint32_t)cells[j])][Offset(dx, dy)]++;
					}
				}
			}
			return stats;
		}

		//The offset the pair holds most often; ties go to the smallest (dx, dy),
		//which the ordered map already hands out first.
		std::pair<Offset, uint32_t> DominantOffset(const std::map<Offset, uint32_t>& offsets)
		{
			std::pair<Offset, uint32_t> best(Offset(0, 0), 0);
			for(const auto& entry : offsets) {
				if(entry.second > best.second) {
					best = entry;
				}
			}
			return best;
		}
	}

	Vocabulary BuildSpriteVocabulary(const std::vector<OamFrame>& frames)
	{
		std::map<ShapeId, uint32_t> counts;
		for(const OamFrame& frame : frames) {
			for(const OamEntry& entry : frame.Entries) {
				if(entry.Shape != kEmptyCell) {
					counts[entry.Shape]++;
				}
			}
		}

		Vocabulary vocab;
		//Unit 8: an OAM entry is one 8x8 tile, and the sprite sheet's cell grid
		//is what turns a pixel offset into a cell offset.
		vocab.Grid.Unit = 8;
		for(const auto& entry : counts) {
			MetatileEntry cell;
			cell.Key = SpriteKey(entry.first);
			cell.Count = entry.second;
			vocab.Entries.push_back(cell);
		}
		std::stable_sort(vocab.Entries.begin(), vocab.Entries.end(), [](const MetatileEntry& a, const MetatileEntry& b) {
			return a.Count != b.Count ? a.Count > b.Count : a.Key < b.Key;
		});
		for(uint32_t i = 0; i < vocab.Entries.size(); i++) {
			vocab.Index[vocab.Entries[i].Key] = i;
		}
		return vocab;
	}

	std::vector<GroupEdge> SelectSpriteEdges(const std::vector<OamFrame>& frames, const Vocabulary& vocab, uint32_t minCount, double minProb)
	{
		SpriteStats stats = Accumulate(frames, vocab);
		std::vector<GroupEdge> edges;
		for(const auto& pair : stats.Offsets) {
			//Accumulate() counts both orderings of every pair with mirrored
			//offsets, so one of the two is enough; A < B keeps Dx/Dy reading
			//"where B sits relative to A" and the evidence list free of twins.
			if(pair.first.first >= pair.first.second) {
				continue;
			}
			std::pair<Offset, uint32_t> dominant = DominantOffset(pair.second);
			uint32_t count = dominant.second;
			uint32_t appearA = stats.Appearances[pair.first.first];
			uint32_t appearB = stats.Appearances[pair.first.second];
			if(count < minCount || appearA == 0 || appearB == 0) {
				continue;
			}
			//The metatile criterion's denominator is "every placement of A in
			//that direction"; the OAM analogue is "every appearance of A", so a
			//sprite that is only sometimes at this offset - or that turns up
			//without its partner - fails exactly like sand next to everything.
			double probAb = (double)count / appearA;
			double probBa = (double)count / appearB;
			if(probAb < minProb || probBa < minProb) {
				continue;
			}
			GroupEdge edge;
			edge.A = pair.first.first;
			edge.B = pair.first.second;
			edge.Dx = ToCells(dominant.first.first);
			edge.Dy = ToCells(dominant.first.second);
			edge.Dir = DirOf(dominant.first.first, dominant.first.second);
			edge.Count = count;
			edge.ProbAB = probAb;
			edge.ProbBA = probBa;
			edges.push_back(edge);
		}
		return edges;
	}

	std::vector<SheetGroup> BuildSprites(const std::vector<OamFrame>& frames, const Vocabulary& vocab, uint32_t minCount, double minProb)
	{
		return LayoutGroups(vocab, SelectSpriteEdges(frames, vocab, minCount, minProb));
	}

	std::vector<SheetGroup> BuildSprites(const std::vector<OamFrame>& frames, const Vocabulary& vocab)
	{
		return BuildSprites(frames, vocab, kSheetMinPairCount, kSheetMinPairProb);
	}

	//ADR-0164 §1 (F9.17): see SpriteGrouping.h. Where SelectSpriteEdges throws
	//the losing mass away, this keeps it: the pairs that scored 0.3 are what a
	//composition tool re-ranks under a lock, and the denominators it divides by
	//must be on disk with the same meaning they had at grouping time.
	SpriteAdjacencyStats AccumulateSpriteAdjacency(const std::vector<OamFrame>& frames, const Vocabulary& vocab)
	{
		SpriteAdjacencyStats stats;
		stats.OamFrames = (uint32_t)frames.size();
		std::vector<std::map<uint32_t, uint32_t>> floorCounts(vocab.Entries.size());
		//Directed within-cap offsets per unordered pair. Only the lower index as
		//reference is recorded (mirroring SelectSpriteEdges, which keeps one of
		//the two mirrored orderings), so Dx/Dy always read "where B sits
		//relative to A".
		std::map<PairKey, std::map<Offset, uint32_t>> offsets;
		std::map<PairKey, uint32_t> coFrames;

		for(const OamFrame& frame : frames) {
			std::vector<int32_t> cells;
			cells.reserve(frame.Entries.size());
			std::set<uint32_t> present;
			for(const OamEntry& entry : frame.Entries) {
				int32_t cell = vocab.Find(SpriteKey(entry.Shape));
				cells.push_back(cell);
				if(cell < 0) {
					continue;
				}
				present.insert((uint32_t)cell);
				//Bottom edge (Y + 8) quantised to 8 px. Accumulated per instance
				//over the de-duplicated frames, like Appearances: an 8x16 figure's
				//lower half lands on the true bottom, and two identical actors on
				//one ground both reach the same band.
				uint32_t band = ((uint32_t)entry.Y + 8) & ~7u;
				floorCounts[(size_t)cell][band]++;
			}
			//Co-presence: both shapes on screen at all, any distance, counted
			//once per frame. Every pair that ever shares a frame and clears the
			//noise floor reaches the file - a boss and a level enemy that never
			//come within 32 px get a pair with empty offsets, not none at all.
			for(std::set<uint32_t>::const_iterator it = present.begin(); it != present.end(); ++it) {
				for(std::set<uint32_t>::const_iterator inner = it; inner != present.end(); ++inner) {
					if(inner == it) {
						continue;
					}
					coFrames[PairKey(*it, *inner)]++;
				}
			}
			for(size_t i = 0; i < cells.size(); i++) {
				if(cells[i] < 0) {
					continue;
				}
				for(size_t j = 0; j < cells.size(); j++) {
					if(i == j || cells[j] < 0 || cells[i] >= cells[j]) {
						continue;
					}
					int32_t dx = (int32_t)frame.Entries[j].X - (int32_t)frame.Entries[i].X;
					int32_t dy = (int32_t)frame.Entries[j].Y - (int32_t)frame.Entries[i].Y;
					if(std::abs(dx) > kSpriteMaxOffset || std::abs(dy) > kSpriteMaxOffset) {
						continue;
					}
					offsets[PairKey((uint32_t)cells[i], (uint32_t)cells[j])][Offset(dx, dy)]++;
				}
			}
		}

		//Floors: the top kAdjacencyMaxFloors bands per node, count descending
		//then band ascending, so two saves of one recording never wobble.
		stats.Floors.resize(vocab.Entries.size());
		for(size_t node = 0; node < vocab.Entries.size(); node++) {
			std::vector<SpriteFloorBand> bands;
			for(const std::pair<const uint32_t, uint32_t>& band : floorCounts[node]) {
				SpriteFloorBand sample;
				sample.Bottom = band.first;
				sample.Count = band.second;
				bands.push_back(sample);
			}
			std::sort(bands.begin(), bands.end(), [](const SpriteFloorBand& a, const SpriteFloorBand& b) {
				return a.Count != b.Count ? a.Count > b.Count : a.Bottom < b.Bottom;
			});
			if(bands.size() > kAdjacencyMaxFloors) {
				bands.resize(kAdjacencyMaxFloors);
			}
			stats.Floors[node] = std::move(bands);
		}

		//Pairs: only those with enough co-presence to be evidence, offsets
		//pruned to the top kAdjacencyMaxOffsets by count (ties by offset).
		for(const std::pair<const PairKey, uint32_t>& pair : coFrames) {
			if(pair.second < kAdjacencyMinPairCount) {
				continue;
			}
			SpritePairStat stat;
			stat.A = pair.first.first;
			stat.B = pair.first.second;
			stat.CoFrames = pair.second;
			std::map<PairKey, std::map<Offset, uint32_t>>::const_iterator match = offsets.find(pair.first);
			if(match != offsets.end()) {
				std::vector<SpriteOffsetSample> samples;
				for(const std::pair<const Offset, uint32_t>& offset : match->second) {
					SpriteOffsetSample sample;
					sample.Dx = offset.first.first;
					sample.Dy = offset.first.second;
					sample.Count = offset.second;
					stat.Count += offset.second;
					samples.push_back(sample);
				}
				std::sort(samples.begin(), samples.end(), [](const SpriteOffsetSample& a, const SpriteOffsetSample& b) {
					if(a.Count != b.Count) { return a.Count > b.Count; }
					if(a.Dx != b.Dx) { return a.Dx < b.Dx; }
					return a.Dy < b.Dy;
				});
				for(size_t i = 0; i < samples.size(); i++) {
					if(i < kAdjacencyMaxOffsets) {
						stat.Offsets.push_back(samples[i]);
					} else {
						stat.Other += samples[i].Count;
					}
				}
			}
			stats.Pairs.push_back(stat);
		}
		return stats;
	}
}

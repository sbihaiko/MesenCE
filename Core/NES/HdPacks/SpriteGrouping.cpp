//ADR-0153 §2 (Phase 9, F9.5) - see SpriteGrouping.h. Stateful partner: HdPackBuilder.
#include "NES/HdPacks/SpriteGrouping.h"
#include "NES/HdPacks/SheetGrouping.h"
#include <algorithm>
#include <cstdlib>
#include <set>
#include <tuple>
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

		//Per shape: the number of OAM instances (Appearances) and the number of
		//frames it appeared in at all (NodeFrames, once per frame however many
		//instances - the same quantity ADR-0173 named NodeFrames for floors[]).
		//Per ordered shape pair: how many *frames* held each exact relative
		//offset. Everything here is counted over the de-duplicated frame stream,
		//RepeatCount deliberately ignored, so a paused screen cannot manufacture
		//the minimum count the criterion asks for.
		//
		//ADR-0176 (issue #176): Offsets and NodeFrames are both per frame, so
		//the grouping ratio divides like by like. Appearances stays as the
		//honest instance count - adjacency.json reports it - but is no longer
		//the denominator of that ratio.
		struct SpriteStats
		{
			std::map<uint32_t, uint32_t> Appearances;
			std::map<uint32_t, uint32_t> NodeFrames;
			std::map<PairKey, std::map<Offset, uint32_t>> Offsets;
		};

		SpriteStats Accumulate(const std::vector<OamFrame>& frames, const Vocabulary& vocab)
		{
			SpriteStats stats;
			//Reused across frames to keep the per-frame de-duplication cheap.
			std::set<uint32_t> present;
			std::set<std::pair<PairKey, Offset>> seenThisFrame;
			for(const OamFrame& frame : frames) {
				std::vector<int32_t> cells;
				cells.reserve(frame.Entries.size());
				for(const OamEntry& entry : frame.Entries) {
					cells.push_back(vocab.Find(SpriteKey(entry.Shape)));
				}
				present.clear();
				seenThisFrame.clear();
				for(size_t i = 0; i < cells.size(); i++) {
					if(cells[i] < 0) {
						continue;
					}
					stats.Appearances[(uint32_t)cells[i]]++;
					present.insert((uint32_t)cells[i]);
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
						//ADR-0176 §2: the frame counts once when *some* instance
						//of A has *some* instance of B at this offset. A second
						//instance pair at the same offset in the same frame is
						//the same evidence seen twice, not twice the evidence.
						seenThisFrame.insert(std::make_pair(PairKey((uint32_t)cells[i], (uint32_t)cells[j]), Offset(dx, dy)));
					}
				}
				for(uint32_t node : present) {
					stats.NodeFrames[node]++;
				}
				for(const std::pair<PairKey, Offset>& seen : seenThisFrame) {
					stats.Offsets[seen.first][seen.second]++;
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

		//ADR-0177 (issue #179): a cluster's tiles touched; that is not the same
		//statement as "these tiles are one figure". Whenever one actor walks
		//over or past another, the BuildPoses DSU fuses them and the pack gains
		//an entry holding both. Label those so the composition editor can stop
		//offering them - without deleting anything, exactly as ADR-0173 does
		//for a screen-fixed sprite.
		//
		//The evidence is structural and needs no threshold: an entry is a
		//fusion when its tiles split, at some translation, into two entries the
		//recorder *also* saw standing on their own. Both parts are kept poses,
		//so both already cleared kPoseMinFrames.
		void LabelPoseFusions(std::vector<PoseEntry>& entries)
		{
			//Tile set -> rank. A kept pose's Tiles are normalised (the smallest
			//Dx and the smallest Dy are both 0) and sorted, so the vector is
			//already a usable key. emplace keeps the first, i.e. the best rank,
			//should two entries ever share a set.
			std::map<std::vector<PoseTile>, uint32_t> byTiles;
			//Candidates indexed on their anchor tile's node. Tiles[0] is the
			//topmost-leftmost tile (the sort is Dy, Dx, Node), and a candidate
			//can only align inside another pose at a tile carrying that node -
			//which is what keeps this pass from being poses-squared in practice.
			std::map<uint32_t, std::vector<uint32_t>> byAnchorNode;
			for(size_t i = 0; i < entries.size(); i++) {
				if(entries[i].Tiles.empty()) {
					continue;
				}
				byTiles.emplace(entries[i].Tiles, (uint32_t)i);
				byAnchorNode[entries[i].Tiles[0].Node].push_back((uint32_t)i);
			}

			for(size_t bi = 0; bi < entries.size(); bi++) {
				const std::vector<PoseTile>& whole = entries[bi].Tiles;
				//Both halves have to clear kPoseMinTiles to be poses at all.
				if(whole.size() < 2 * (size_t)kPoseMinTiles) {
					continue;
				}
				std::set<PoseTile> wholeSet(whole.begin(), whole.end());

				//Ranks, ascending: ADR-0177 §2 tries candidates in file order,
				//so the part this names first is the most-seen part the split
				//admits.
				std::set<uint32_t> candidates;
				for(const PoseTile& tile : whole) {
					std::map<uint32_t, std::vector<uint32_t>>::const_iterator bucket = byAnchorNode.find(tile.Node);
					if(bucket == byAnchorNode.end()) {
						continue;
					}
					for(uint32_t rank : bucket->second) {
						if(rank != (uint32_t)bi && entries[rank].Tiles.size() < whole.size()) {
							candidates.insert(rank);
						}
					}
				}

				bool labelled = false;
				for(uint32_t rank : candidates) {
					const std::vector<PoseTile>& part = entries[rank].Tiles;
					const PoseTile& head = part[0];
					for(const PoseTile& tile : whole) {
						if(tile.Node != head.Node) {
							continue;
						}
						int32_t shiftX = tile.Dx - head.Dx;
						int32_t shiftY = tile.Dy - head.Dy;
						std::set<PoseTile> placed;
						bool fits = true;
						for(const PoseTile& member : part) {
							PoseTile moved;
							moved.Node = member.Node;
							moved.Dx = member.Dx + shiftX;
							moved.Dy = member.Dy + shiftY;
							if(!wholeSet.count(moved)) {
								fits = false;
								break;
							}
							placed.insert(moved);
						}
						if(!fits) {
							continue;
						}

						//The remainder, re-normalised to its own top-left -
						//the space every kept pose's Tiles already live in.
						std::vector<PoseTile> rest;
						for(const PoseTile& member : whole) {
							if(!placed.count(member)) {
								rest.push_back(member);
							}
						}
						if(rest.size() < (size_t)kPoseMinTiles) {
							continue;
						}
						int32_t restX = rest[0].Dx;
						int32_t restY = rest[0].Dy;
						for(const PoseTile& member : rest) {
							restX = std::min(restX, member.Dx);
							restY = std::min(restY, member.Dy);
						}
						for(PoseTile& member : rest) {
							member.Dx -= restX;
							member.Dy -= restY;
						}
						std::sort(rest.begin(), rest.end());

						std::map<std::vector<PoseTile>, uint32_t>::const_iterator match = byTiles.find(rest);
						if(match == byTiles.end()) {
							continue;
						}
						entries[bi].FusionOf.push_back(rank);
						entries[bi].FusionOf.push_back(match->second);
						labelled = true;
						break;
					}
					if(labelled) {
						break;
					}
				}
			}
		}

		//---- ADR-0179 (F9.20) ---------------------------------------------

		//One spatially connected cluster of a frame: its normalised tile set
		//(the pose identity) and where its top-left sat on screen, in pixels.
		struct PoseCluster
		{
			std::vector<PoseTile> Tiles;
			int32_t X = 0;
			int32_t Y = 0;
		};

		//The ADR-0170 §1 segmentation of one retained frame: entries the
		//vocabulary knows, DSU-joined within kPoseMaxGap on both axes, each
		//cluster normalised to its own top-left at round-to-nearest cell and
		//reduced to a set. Clusters under kPoseMinTiles are not returned.
		std::vector<PoseCluster> SegmentFrame(const OamFrame& frame, const Vocabulary& vocab)
		{
			std::vector<PoseCluster> out;
			//An unknown shape is skipped rather than clustered: it would move
			//the top-left and so shift every offset in the pose.
			std::vector<std::pair<int32_t, int32_t>> points;
			std::vector<uint32_t> nodes;
			for(const OamEntry& entry : frame.Entries) {
				int32_t node = vocab.Find(SpriteKey(entry.Shape));
				if(node < 0) {
					continue;
				}
				points.push_back(std::make_pair((int32_t)entry.X, (int32_t)entry.Y));
				nodes.push_back((uint32_t)node);
			}
			if(points.size() < kPoseMinTiles) {
				return out;
			}
			Dsu sets(points.size());
			for(size_t i = 0; i < points.size(); i++) {
				for(size_t j = i + 1; j < points.size(); j++) {
					if(std::abs(points[i].first - points[j].first) <= kPoseMaxGap && std::abs(points[i].second - points[j].second) <= kPoseMaxGap) {
						sets.Union((uint32_t)i, (uint32_t)j);
					}
				}
			}
			std::map<uint32_t, std::vector<size_t>> clusters;
			for(size_t i = 0; i < points.size(); i++) {
				clusters[sets.Find((uint32_t)i)].push_back(i);
			}
			for(const std::pair<const uint32_t, std::vector<size_t>>& cluster : clusters) {
				if(cluster.second.size() < kPoseMinTiles) {
					continue;
				}
				PoseCluster pc;
				pc.X = points[cluster.second[0]].first;
				pc.Y = points[cluster.second[0]].second;
				for(size_t index : cluster.second) {
					pc.X = std::min(pc.X, points[index].first);
					pc.Y = std::min(pc.Y, points[index].second);
				}
				pc.Tiles.reserve(cluster.second.size());
				for(size_t index : cluster.second) {
					PoseTile tile;
					tile.Node = nodes[index];
					tile.Dx = ToCells(points[index].first - pc.X);
					tile.Dy = ToCells(points[index].second - pc.Y);
					pc.Tiles.push_back(tile);
				}
				//A set, not a list: two OAM entries of the same shape rounding
				//onto one cell are one member, exactly as the S10.a ground
				//truth counted them.
				std::sort(pc.Tiles.begin(), pc.Tiles.end());
				pc.Tiles.erase(std::unique(pc.Tiles.begin(), pc.Tiles.end()), pc.Tiles.end());
				if(pc.Tiles.size() < kPoseMinTiles) {
					continue;
				}
				out.push_back(pc);
			}
			return out;
		}

		//Does `part`, translated so that its head lands on `at` (a tile of
		//`whole` carrying the head's node), fit inside `wholeSet`? Fills
		//`placed` with the translated members when it does.
		bool PartFitsAt(const std::vector<PoseTile>& part, const PoseTile& at, const std::set<PoseTile>& wholeSet, std::set<PoseTile>& placed)
		{
			const PoseTile& head = part[0];
			int32_t shiftX = at.Dx - head.Dx;
			int32_t shiftY = at.Dy - head.Dy;
			placed.clear();
			for(const PoseTile& member : part) {
				PoseTile moved;
				moved.Node = member.Node;
				moved.Dx = member.Dx + shiftX;
				moved.Dy = member.Dy + shiftY;
				if(!wholeSet.count(moved)) {
					return false;
				}
				placed.insert(moved);
			}
			return true;
		}

		//ADR-0179 §4: a kept, non-fusion pose is a *variant* of the first kept
		//pose (file order) that fits inside it leaving a remainder below
		//kPoseMinTiles - a figure plus its projectile or muzzle flash. The
		//remainder could never be a pose, which is exactly what separates a
		//variant from ADR-0177's fusion. Containment only, no threshold.
		void LabelPoseVariants(std::vector<PoseEntry>& entries)
		{
			std::map<uint32_t, std::vector<uint32_t>> byAnchorNode;
			for(size_t i = 0; i < entries.size(); i++) {
				if(!entries[i].Tiles.empty() && entries[i].FusionOf.empty()) {
					byAnchorNode[entries[i].Tiles[0].Node].push_back((uint32_t)i);
				}
			}
			for(size_t vi = 0; vi < entries.size(); vi++) {
				const std::vector<PoseTile>& whole = entries[vi].Tiles;
				if(!entries[vi].FusionOf.empty() || whole.size() <= (size_t)kPoseMinTiles) {
					continue;
				}
				std::set<PoseTile> wholeSet(whole.begin(), whole.end());
				std::set<uint32_t> candidates;
				for(const PoseTile& tile : whole) {
					std::map<uint32_t, std::vector<uint32_t>>::const_iterator bucket = byAnchorNode.find(tile.Node);
					if(bucket == byAnchorNode.end()) {
						continue;
					}
					for(uint32_t rank : bucket->second) {
						size_t partSize = entries[rank].Tiles.size();
						if(rank != (uint32_t)vi && partSize < whole.size() && whole.size() - partSize < (size_t)kPoseMinTiles) {
							candidates.insert(rank);
						}
					}
				}
				for(uint32_t rank : candidates) {
					const std::vector<PoseTile>& part = entries[rank].Tiles;
					bool fits = false;
					std::set<PoseTile> placed;
					for(const PoseTile& tile : whole) {
						if(tile.Node == part[0].Node && PartFitsAt(part, tile, wholeSet, placed)) {
							fits = true;
							break;
						}
					}
					if(fits) {
						entries[vi].VariantOf = (int32_t)rank;
						break;
					}
				}
			}
		}

		//One run of one pose on a track: the pose and how many frames
		//(RepeatCount included) it was held before the track changed pose.
		typedef PoseTrackRun TrackRun;

		//ADR-0179 §1: greedy nearest-first linking of kept clusters between
		//consecutive retained frames, within kPoseTrackMaxMove. Fills
		//Hold/Next on the entries and returns the tracks as runs.
		std::vector<std::vector<TrackRun>> LinkPoseTracks(const std::vector<OamFrame>& frames, const Vocabulary& vocab, std::vector<PoseEntry>& entries)
		{
			std::map<std::vector<PoseTile>, uint32_t> rankOf;
			for(size_t i = 0; i < entries.size(); i++) {
				rankOf.emplace(entries[i].Tiles, (uint32_t)i);
			}
			struct Live
			{
				int32_t X;
				int32_t Y;
				uint32_t Pose;
				size_t Track;
			};
			std::vector<std::vector<TrackRun>> tracks;
			std::vector<Live> prev;
			for(const OamFrame& frame : frames) {
				std::vector<Live> cur;
				for(const PoseCluster& cluster : SegmentFrame(frame, vocab)) {
					std::map<std::vector<PoseTile>, uint32_t>::const_iterator it = rankOf.find(cluster.Tiles);
					if(it == rankOf.end()) {
						continue; //below the ADR-0170 §2 thresholds: invisible to the linker
					}
					Live live;
					live.X = cluster.X;
					live.Y = cluster.Y;
					live.Pose = it->second;
					live.Track = (size_t)-1;
					cur.push_back(live);
				}
				//Every candidate link, nearest first; ties broken by position in
				//either frame so two saves of one stream link identically.
				std::vector<std::tuple<int32_t, size_t, size_t>> links;
				for(size_t pi = 0; pi < prev.size(); pi++) {
					for(size_t ci = 0; ci < cur.size(); ci++) {
						int32_t d = std::abs(prev[pi].X - cur[ci].X) + std::abs(prev[pi].Y - cur[ci].Y);
						if(d <= kPoseTrackMaxMove) {
							links.push_back(std::make_tuple(d, pi, ci));
						}
					}
				}
				std::sort(links.begin(), links.end());
				std::vector<bool> prevUsed(prev.size(), false);
				for(const std::tuple<int32_t, size_t, size_t>& link : links) {
					size_t pi = std::get<1>(link);
					size_t ci = std::get<2>(link);
					if(prevUsed[pi] || cur[ci].Track != (size_t)-1) {
						continue;
					}
					prevUsed[pi] = true;
					cur[ci].Track = prev[pi].Track;
					std::vector<TrackRun>& track = tracks[prev[pi].Track];
					if(prev[pi].Pose == cur[ci].Pose) {
						entries[cur[ci].Pose].Hold++;
						track.back().Held += frame.RepeatCount;
					} else {
						std::vector<PoseLink>& next = entries[prev[pi].Pose].Next;
						bool found = false;
						for(PoseLink& edge : next) {
							if(edge.Pose == cur[ci].Pose) {
								edge.Count++;
								found = true;
								break;
							}
						}
						if(!found) {
							PoseLink edge;
							edge.Pose = cur[ci].Pose;
							edge.Count = 1;
							next.push_back(edge);
						}
						TrackRun run;
						run.Frame = frame.FrameNumber;
						run.Pose = cur[ci].Pose;
						run.Held = frame.RepeatCount;
						track.push_back(run);
					}
				}
				for(Live& live : cur) {
					if(live.Track == (size_t)-1) {
						TrackRun run;
						run.Frame = frame.FrameNumber;
						run.Pose = live.Pose;
						run.Held = frame.RepeatCount;
						tracks.push_back(std::vector<TrackRun>(1, run));
						live.Track = tracks.size() - 1;
					}
				}
				prev = cur;
			}
			for(PoseEntry& entry : entries) {
				std::stable_sort(entry.Next.begin(), entry.Next.end(), [](const PoseLink& a, const PoseLink& b) {
					if(a.Count != b.Count) { return a.Count > b.Count; }
					return a.Pose < b.Pose;
				});
			}
			return tracks;
		}

		uint32_t MedianOf(std::vector<uint32_t> values)
		{
			if(values.empty()) {
				return 0;
			}
			std::sort(values.begin(), values.end());
			return values[values.size() / 2];
		}

		//A cycle occurrence, canonically rotated: the most-seen pose (lowest
		//rank) first; when it occurs twice in the period, the rotation with
		//the lexicographically smallest pose vector.
		std::vector<uint32_t> CanonicalRotation(const std::vector<uint32_t>& block, size_t& shift)
		{
			std::vector<uint32_t> best;
			shift = 0;
			for(size_t r = 0; r < block.size(); r++) {
				if(block[r] != *std::min_element(block.begin(), block.end())) {
					continue;
				}
				std::vector<uint32_t> rotated;
				for(size_t k = 0; k < block.size(); k++) {
					rotated.push_back(block[(r + k) % block.size()]);
				}
				if(best.empty() || rotated < best) {
					best = rotated;
					shift = r;
				}
			}
			return best;
		}

		//ADR-0179 §3: cycles by period repetition on each track, then
		//sequences by identical occurrence on what the cycles left uncovered.
		void FindPoseRuns(const std::vector<std::vector<TrackRun>>& tracks, PoseStats& stats)
		{
			struct Occurrences
			{
				uint32_t Repeats = 0;
				std::vector<std::vector<uint32_t>> Holds; //per position
			};
			std::map<std::vector<uint32_t>, Occurrences> cycles;
			std::map<std::vector<uint32_t>, Occurrences> sequences;

			for(const std::vector<TrackRun>& track : tracks) {
				size_t n = track.size();
				std::vector<bool> covered(n, false);
				size_t start = 0;
				while(start < n) {
					bool found = false;
					for(size_t p = 2; p <= (size_t)kPoseCycleMaxPeriod && start + 2 * p <= n; p++) {
						size_t r = 1;
						while(start + (r + 1) * p <= n) {
							bool same = true;
							for(size_t k = 0; k < p && same; k++) {
								same = track[start + k].Pose == track[start + r * p + k].Pose;
							}
							if(!same) {
								break;
							}
							r++;
						}
						if(r < (size_t)kPoseCycleMinRepeats) {
							continue;
						}
						std::vector<uint32_t> block;
						for(size_t k = 0; k < p; k++) {
							block.push_back(track[start + k].Pose);
						}
						if(std::set<uint32_t>(block.begin(), block.end()).size() < 2) {
							continue;
						}
						size_t shift = 0;
						std::vector<uint32_t> key = CanonicalRotation(block, shift);
						Occurrences& occ = cycles[key];
						occ.Repeats += (uint32_t)r;
						occ.Holds.resize(p);
						for(size_t k = 0; k < r * p; k++) {
							occ.Holds[(k + p - shift) % p].push_back(track[start + k].Held);
						}
						//Cover the full repeats and the partial repeat that
						//follows, so a tail of the loop is not read as a sequence.
						size_t end = start + r * p;
						while(end < n && track[end].Pose == block[(end - start) % p]) {
							end++;
						}
						for(size_t k = start; k < end; k++) {
							covered[k] = true;
						}
						start = end;
						found = true;
						break;
					}
					if(!found) {
						start++;
					}
				}
				//Uncovered segments -> every all-distinct window of an allowed length.
				size_t i = 0;
				while(i < n) {
					if(covered[i]) {
						i++;
						continue;
					}
					size_t j = i;
					while(j < n && !covered[j]) {
						j++;
					}
					for(size_t a = i; a < j; a++) {
						std::set<uint32_t> seen;
						std::vector<uint32_t> window;
						std::vector<uint32_t> holds;
						for(size_t b = a; b < j && window.size() < (size_t)kPoseSequenceMaxLength; b++) {
							if(!seen.insert(track[b].Pose).second) {
								break;
							}
							window.push_back(track[b].Pose);
							holds.push_back(track[b].Held);
							if(window.size() >= (size_t)kPoseSequenceMinLength) {
								Occurrences& occ = sequences[window];
								occ.Repeats++;
								occ.Holds.resize(window.size());
								for(size_t k = 0; k < holds.size(); k++) {
									occ.Holds[k].push_back(holds[k]);
								}
							}
						}
					}
					i = j;
				}
			}

			for(const std::pair<const std::vector<uint32_t>, Occurrences>& cycle : cycles) {
				PoseRun run;
				run.Poses = cycle.first;
				run.Repeats = cycle.second.Repeats;
				for(const std::vector<uint32_t>& holds : cycle.second.Holds) {
					run.Hold.push_back(MedianOf(holds));
				}
				stats.Cycles.push_back(run);
			}
			//Longest first, then most repeated: a window inside an accepted
			//longer one is the same animation seen shorter, not a second one.
			std::vector<std::pair<std::vector<uint32_t>, Occurrences>> candidates;
			for(const std::pair<const std::vector<uint32_t>, Occurrences>& seq : sequences) {
				if(seq.second.Repeats >= kPoseCycleMinRepeats) {
					candidates.push_back(seq);
				}
			}
			std::stable_sort(candidates.begin(), candidates.end(), [](const std::pair<std::vector<uint32_t>, Occurrences>& a, const std::pair<std::vector<uint32_t>, Occurrences>& b) {
				if(a.first.size() != b.first.size()) { return a.first.size() > b.first.size(); }
				if(a.second.Repeats != b.second.Repeats) { return a.second.Repeats > b.second.Repeats; }
				return a.first < b.first;
			});
			//A window of a cycle is that cycle seen too briefly to repeat - a
			//soldier who walked one and a half turns before he died. ADR-0179
			//§3 says "not part of any cycle", so it is matched around the loop.
			std::vector<std::vector<uint32_t>> loops;
			for(const PoseRun& cycle : stats.Cycles) {
				std::vector<uint32_t> twice = cycle.Poses;
				twice.insert(twice.end(), cycle.Poses.begin(), cycle.Poses.end());
				loops.push_back(twice);
			}
			std::vector<std::vector<uint32_t>> accepted;
			for(const std::pair<std::vector<uint32_t>, Occurrences>& seq : candidates) {
				bool inside = false;
				for(const std::vector<uint32_t>& loop : loops) {
					if(seq.first.size() <= loop.size() / 2 && std::search(loop.begin(), loop.end(), seq.first.begin(), seq.first.end()) != loop.end()) {
						inside = true;
						break;
					}
				}
				for(const std::vector<uint32_t>& longer : accepted) {
					if(inside) {
						break;
					}
					if(std::search(longer.begin(), longer.end(), seq.first.begin(), seq.first.end()) != longer.end()) {
						inside = true;
						break;
					}
				}
				if(inside) {
					continue;
				}
				accepted.push_back(seq.first);
				PoseRun run;
				run.Poses = seq.first;
				run.Repeats = seq.second.Repeats;
				for(const std::vector<uint32_t>& holds : seq.second.Holds) {
					run.Hold.push_back(MedianOf(holds));
				}
				stats.Sequences.push_back(run);
			}
			auto byRepeats = [](const PoseRun& a, const PoseRun& b) {
				if(a.Repeats != b.Repeats) { return a.Repeats > b.Repeats; }
				return a.Poses < b.Poses;
			};
			std::stable_sort(stats.Cycles.begin(), stats.Cycles.end(), byRepeats);
			std::stable_sort(stats.Sequences.begin(), stats.Sequences.end(), byRepeats);
			stats.Tracks = (uint32_t)tracks.size();
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
			uint32_t framesA = stats.NodeFrames[pair.first.first];
			uint32_t framesB = stats.NodeFrames[pair.first.second];
			if(count < minCount || framesA == 0 || framesB == 0) {
				continue;
			}
			//The metatile criterion's denominator is "every placement of A in
			//that direction"; the OAM analogue is "every frame A is on screen",
			//so a sprite that is only sometimes at this offset - or that turns
			//up without its partner - fails exactly like sand next to
			//everything.
			//
			//ADR-0176 (issue #176): the denominator used to be Appearances, the
			//instance count, against a numerator that is per frame. A shape
			//drawn twice in one frame then had an arithmetic ceiling of 0.5 and
			//every one of its edges was dropped regardless of the evidence -
			//the same biased denominator ADR-0173 fixed for floors[]. Both
			//sides are per frame now; kSheetMinPairCount / kSheetMinPairProb
			//keep their values and their meaning.
			double probAb = (double)count / framesA;
			double probBa = (double)count / framesB;
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
		std::vector<std::set<uint32_t>> seenPositions(vocab.Entries.size());
		std::vector<uint32_t> nodeFrames(vocab.Entries.size(), 0);
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
				seenPositions[(size_t)cell].insert(((uint32_t)entry.X << 8) | (uint32_t)entry.Y);
			}
			//Co-presence: both shapes on screen at all, any distance, counted
			//once per frame. Every pair that ever shares a frame and clears the
			//noise floor reaches the file - a boss and a level enemy that never
			//come within 32 px get a pair with empty offsets, not none at all.
			for(std::set<uint32_t>::const_iterator it = present.begin(); it != present.end(); ++it) {
				nodeFrames[*it]++;
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
		stats.Positions.resize(vocab.Entries.size());
		for(size_t node = 0; node < vocab.Entries.size(); node++) {
			stats.Positions[node] = (uint32_t)seenPositions[node].size();
		}
		stats.NodeFrames = std::move(nodeFrames);
		//ADR-0173: screen furniture - a HUD bar, a menu icon - is drawn at a
		//handful of fixed pixels for the whole capture, so its bottom edge lands
		//in several quantised bands at once and joins every one of them as a
		//member. An actor visits a new position nearly every frame it is on
		//screen; furniture returns to the same one over and over. That ratio is
		//the test, and it needs enough frames to mean anything.
		stats.ScreenFixed.assign(vocab.Entries.size(), 0);
		for(size_t node = 0; node < vocab.Entries.size(); node++) {
			//Neither `frames` (the function's OAM-stream parameter, C4457) nor
			//`nodeFrames` (the vector declared above, C4456): MSVC treats both
			//shadowing warnings as errors, and this scope is inside both.
			uint32_t frameCount = stats.NodeFrames[node];
			uint32_t positions = stats.Positions[node];
			if(frameCount >= kScreenFixedMinFrames && positions > 0 &&
				(uint64_t)positions * kScreenFixedRevisits <= (uint64_t)frameCount) {
				stats.ScreenFixed[node] = 1;
			}
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

	//ADR-0170 (F9.19): poses, from the per-frame structure AccumulateSpriteAdjacency
	//throws away. See SpriteGrouping.h for why the pairwise projection cannot
	//answer this question.
	InputStats BuildInputStats(const std::vector<OamFrame>& frames)
	{
		InputStats input;
		bool portSeen[2] = { false, false };
		for(const OamFrame& frame : frames) {
			input.Frames += frame.RepeatCount;
			uint8_t held = 0;
			bool pair[4][2] = {};
			for(uint32_t port = 0; port < 2; port++) {
				uint8_t byte = frame.Buttons[port];
				held |= byte;
				portSeen[port] = portSeen[port] || byte != 0;
				//A direction+action pair is a move one player made, so it is
				//read within a port; port 1 holding Right while port 2 holds A
				//is not a Right+A. Directions are bits 4..7, actions bits 0..1.
				for(uint32_t d = 0; d < 4; d++) {
					for(uint32_t a = 0; a < 2; a++) {
						pair[d][a] = pair[d][a] || ((byte & (1 << (4 + d))) && (byte & (1 << a)));
					}
				}
			}
			for(uint32_t b = 0; b < kButtonCount; b++) {
				if(held & (1 << b)) {
					input.Held[b] += frame.RepeatCount;
				}
			}
			for(uint32_t d = 0; d < 4; d++) {
				for(uint32_t a = 0; a < 2; a++) {
					if(pair[d][a]) {
						input.Pairs[d][a] += frame.RepeatCount;
					}
				}
			}
		}
		input.Ports = (portSeen[0] ? 1 : 0) + (portSeen[1] ? 1 : 0);
		return input;
	}

	PoseStats BuildPoses(const std::vector<OamFrame>& frames, const Vocabulary& vocab)
	{
		PoseStats stats;
		stats.RetainedFrames = (uint32_t)frames.size();
		//Sets-equal identity: the same body with a projectile one cell further
		//away is a different pose. Deliberate - a looser identity can merge two
		//real poses, and that failure is invisible in the file (ADR-0170).
		std::map<std::vector<PoseTile>, uint32_t> seen;
		for(const OamFrame& frame : frames) {
			stats.Frames += frame.RepeatCount;
			for(const PoseCluster& cluster : SegmentFrame(frame, vocab)) {
				seen[cluster.Tiles] += frame.RepeatCount;
			}
		}

		stats.PosesFound = (uint32_t)seen.size();
		std::vector<PoseEntry> kept;
		for(const std::pair<const std::vector<PoseTile>, uint32_t>& pose : seen) {
			if(pose.second < kPoseMinFrames) {
				continue;
			}
			PoseEntry entry;
			entry.Tiles = pose.first;
			entry.Frames = pose.second;
			for(const PoseTile& tile : entry.Tiles) {
				entry.Width = std::max(entry.Width, (uint32_t)(tile.Dx + 1));
				entry.Height = std::max(entry.Height, (uint32_t)(tile.Dy + 1));
			}
			kept.push_back(entry);
		}
		stats.PosesKept = (uint32_t)kept.size();

		//Frames descending, then by the tile set - the ADR sorts "by frames,
		//then by id", and the id is the position in this order, so the set is
		//what breaks the tie deterministically.
		std::stable_sort(kept.begin(), kept.end(), [](const PoseEntry& a, const PoseEntry& b) {
			if(a.Frames != b.Frames) { return a.Frames > b.Frames; }
			return a.Tiles < b.Tiles;
		});
		if(kept.size() > kMaxPoses) {
			kept.resize(kMaxPoses);
		}
		LabelPoseFusions(kept);
		//ADR-0179: variants by containment (§4), then the tracks (§1-2) and
		//what repetition finds on them (§3). All three read only the kept
		//table and the stream; none changes a pose or its rank.
		LabelPoseVariants(kept);
		std::vector<std::vector<TrackRun>> tracks = LinkPoseTracks(frames, vocab, kept);
		stats.Poses = kept;
		FindPoseRuns(tracks, stats);
		stats.Input = BuildInputStats(frames);
		stats.TrackRuns = tracks;
		return stats;
	}

	//ADR-0174 (issue #174): see SpriteGrouping.h. A cross-reference and nothing
	//more - it does not change what a sheet contains, how cells are grouped or
	//what a pose holds, so a consumer that ignores it reads the pack exactly as
	//before. That is the whole reason this, and not a change to the ADR-0153 §2
	//criterion, is the fix: the criterion decides the vocabulary and the layout
	//of every sheet, so loosening it re-cuts every pack ever recorded, while a
	//new optional field is additive in both directions.
	std::vector<uint32_t> PosesForCells(const PoseStats& stats, const std::vector<SheetCell>& cells)
	{
		std::set<uint32_t> nodes;
		for(const SheetCell& cell : cells) {
			if(cell.Metatile >= 0) {
				nodes.insert((uint32_t)cell.Metatile);
			}
		}
		std::vector<uint32_t> refs;
		if(nodes.empty()) {
			return refs;
		}

		//(covered, pose index) - covered descending, index ascending. The index
		//is already the ADR-0170 §1 rank (frames descending, then tiles), so
		//ties fall out in the order the file itself states.
		std::vector<std::pair<uint32_t, uint32_t>> scored;
		for(size_t i = 0; i < stats.Poses.size(); i++) {
			//ADR-0177: a fused entry is two figures that touched, not a figure.
			//This list exists so an artist can reach the subject a sheet's
			//cells belong to, and citing a fusion spends the kSheetMaxPoseRefs
			//budget on noise.
			if(!stats.Poses[i].FusionOf.empty()) {
				continue;
			}
			std::set<uint32_t> covered;
			for(const PoseTile& tile : stats.Poses[i].Tiles) {
				if(nodes.count(tile.Node)) {
					covered.insert(tile.Node);
				}
			}
			if(!covered.empty()) {
				scored.push_back(std::make_pair((uint32_t)covered.size(), (uint32_t)i));
			}
		}
		std::stable_sort(scored.begin(), scored.end(), [](const std::pair<uint32_t, uint32_t>& a, const std::pair<uint32_t, uint32_t>& b) {
			return a.first > b.first;
		});
		for(size_t i = 0; i < scored.size() && i < kSheetMaxPoseRefs; i++) {
			refs.push_back(scored[i].second);
		}
		return refs;
	}
}

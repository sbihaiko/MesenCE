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
	//`minProb` of the frames each shape appears in. A bullet that drifts past
	//everything has many offsets and clears none of them.
	//
	//ADR-0176 (issue #176): both sides of that ratio are counted once per
	//frame. The offset tally rises at most once per frame - the frame counts
	//when *some* instance of A has *some* instance of B there - and the
	//denominator is the frames the shape appeared in, not its instance count,
	//so a shape drawn twice in one frame is judged on the evidence instead of
	//being excluded by an arithmetic ceiling.
	std::vector<GroupEdge> SelectSpriteEdges(const std::vector<OamFrame>& frames, const Vocabulary& vocab, uint32_t minCount, double minProb);

	//Those edges through SheetGrouping's DSU/BFS: components of
	//2..kSheetMaxObjectCells cells laid out at their dominant offsets.
	std::vector<SheetGroup> BuildSprites(const std::vector<OamFrame>& frames, const Vocabulary& vocab, uint32_t minCount, double minProb);

	//Convenience overload using kSheetMinPairCount / kSheetMinPairProb.
	std::vector<SheetGroup> BuildSprites(const std::vector<OamFrame>& frames, const Vocabulary& vocab);

	//ADR-0164 §1 (F9.17): the far-field sprite statistics sheets/adjacency.json
	//persists, accumulated at save time from the same de-duplicated OamFrame
	//stream SpriteGrouping reads: per-shape bottom-edge floor bands (no distance
	//cap), per-pair co-presence (any distance), and the within-32 px offset
	//histogram pruned to its top kAdjacencyMaxOffsets. Unlike SelectSpriteEdges
	//it keeps *every* pair with CoFrames >= kAdjacencyMinPairCount and keeps the
	//unpruned denominators, so a reader recomputes conditional probabilities
	//under a lock instead of guessing at them.
	SpriteAdjacencyStats AccumulateSpriteAdjacency(const std::vector<OamFrame>& frames, const Vocabulary& vocab);

	//ADR-0170 (F9.19): the pose sidecar sheets/poses.json, from the same
	//retained OamFrame stream. AccumulateSpriteAdjacency projects the stream
	//onto pairwise totals, which cannot be inverted - knowing A and B were
	//often on screen together never says whether they shared one silhouette.
	//This keeps the per-frame structure instead: each frame is segmented into
	//spatially connected clusters (within kPoseMaxGap on both axes), each
	//cluster normalised to its own top-left and expressed as a set of
	//(node, dx, dy), and equal sets merge. It is the *measured* enumeration -
	//PRD spike S10.a built its ground truth exactly this way, off ADR-0169's
	//live OAM channel, and found the ADR-0168 evidence[] walk recovering 6.7 %
	//of it. Entries below kPoseMinFrames / kPoseMinTiles are dropped and the
	//kept set is capped at kMaxPoses.
	//ADR-0179 (F9.20) adds what the stream says about succession, without
	//touching how a pose is found or ranked: kept clusters are linked frame
	//to frame (nearest within kPoseTrackMaxMove) into tracks, each entry
	//gains Hold/Next, a kept pose that is another plus a sub-threshold
	//remainder is a VariantOf it, and the tracks are scanned for cycles
	//(period repeated >= kPoseCycleMinRepeats times, found on the sequence
	//so a silhouette can be two phases of one loop) and for sequences
	//(identical non-looping runs seen at least twice).
	PoseStats BuildPoses(const std::vector<OamFrame>& frames, const Vocabulary& vocab);

	//ADR-0174 (issue #174): the join from a sprNNN group sheet to the whole
	//figures its cells are part of. ADR-0153 §2's criterion cuts a character
	//into always-together fragments - measured on Contra, 35 sprite pairs that
	//were never once on screen apart (count == coFrames == 1338 at a constant
	//offset) still landed on different sheets, and a soldier ships cut at the
	//waist. ADR-0170/ADR-0171 already put the whole silhouette in poses.json;
	//what was missing is any way to get from a sheet to it, because a sheet
	//addresses cells and poses.json addresses vocabulary nodes.
	//
	//Returns the positions in stats.Poses - i.e. the "poseNNN" ids
	//SerializePoses writes - of every pose holding at least one of `cells`'
	//vocabulary nodes, ordered by the number of the sheet's *distinct* nodes it
	//covers descending, then by the pose's own rank (frames descending, then
	//id), so the first entry is the most complete figure this sheet is part of.
	//Capped at kSheetMaxPoseRefs. Empty when no cell belongs to a pose.
	std::vector<uint32_t> PosesForCells(const PoseStats& stats, const std::vector<SheetCell>& cells);
}

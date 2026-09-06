#pragma once
//ADR-0153 §6 (Phase 9): stitching the recorded grid stream into artist-facing
//maps. Host-free (see TileSheetTypes.h): no pch.h, no Emulator, no I/O - the
//builder feeds the frames in and writes the bytes back out.
#include "NES/HdPacks/TileSheetTypes.h"

namespace MesenSheets
{
	struct ShiftMatch
	{
		int32_t Dx = 0;
		int32_t Dy = 0;
		double Score = -1;
	};

	//Best whole-cell shift such that b(c,r) == a(c+dx, r+dy) over the playfield.
	ShiftMatch BestShift(const GridFrame& a, const GridFrame& b, uint32_t hudRows, uint32_t hudBottomRows, int32_t maxDx, int32_t maxDy);

	//Screen-based stitching (ADR-0153 §6): stable screens linked by the scroll
	//observed in an early-transition frame, anchored on the last placed screen.
	//
	//F9.8 - a link needs positive adjacency evidence. Matching the anchor at
	//*some* shift is not it: on a game that never scrolls (Mike Tyson's
	//Punch-Out!!) the best shift between two unrelated cards still scores well,
	//and the result was a collage - a fighter profile, a text screen, a round
	//card and the ring glued into one 1024 px strip, five times over. A shift
	//is now only believed when the band it exposes at the leading edge is the
	//candidate screen's opposite edge (kStitchBandMatch) *and* that band says
	//something the anchor did not already say (kStitchBandLead) - the second
	//test is what a screen made mostly of one backdrop tile cannot fake.
	//A direct A-to-B border overlap is *not*
	//accepted as a second, independent path: screen mode places neighbours a
	//whole screen apart, so two screens that genuinely share a column band are
	//not a screen step apart at all, and honouring such a link would place the
	//candidate at a geometry this model cannot express.
	//
	//When nothing anywhere in the recording produces evidence, the answer is
	//*no map*, not one map per screen: a one-screen map is a copy of the
	//`backgrounds/screenNNN.png` the bootstrap already writes (ADR-0050), so
	//it costs the artist a file and tells them nothing. ADR-0153 §6 never
	//promised a map on every recording - it only says which mode wins when
	//both have something to say.
	//Continuous stitching: accumulated per-frame x shift, a cut starts a new
	//region.
	//
	//F9.12 - the cut bar depends on what the step claims. A step that claims a
	//shift is cut below kMinMatch, as before. A step that does *not* - dx == 0,
	//or an argmax that cannot beat standing still (F9.8) - is a claim that both
	//frames show the same place, so it is cut below kStitchWorldAgree, measured
	//on "the camera did not move" rather than on the argmax. Without that, a
	//title/menu/cutscene screen that shares the level's terrain is welded into
	//the level map at offset zero: Super Mario Bros.' title screen is 1-1's
	//first screen with a logo panel and a menu stamped into the sky, agrees
	//with it over 0.700 of the playfield, and its logo, "ONE PLUMBER / TWO
	//PLUMBERS" and "TOP- 000000" ended up in map-000.png as level art. The rule
	//deliberately leaves scrolling steps alone, which is what keeps
	//Excitebike's continuous track in one piece (see TileSheetTypes.h).
	std::vector<StitchedMap> StitchContinuous(const std::vector<GridFrame>& frames, const Vocabulary& vocab, uint32_t frameStep);

	//The whole F9.2 pass: runs the screen stitcher first and falls back to the
	//continuous one per ADR-0153 §6. One StitchedMap per connected region.
	std::vector<StitchedMap> BuildMaps(const std::vector<GridFrame>& frames, const std::vector<const GridFrame*>& screens, const Vocabulary& vocab);

	//---- issue #164: choosing a captured screen's tileAtPosition anchors ----

	//One cell the builder is willing to condition a <background> on: where it
	//sits in the captured frame's grid, and how often the recording drew that
	//tile anywhere (ADR-0050 ranks the rarest first). The builder keeps the
	//pixel/palette/index detail on its own side - this module only reasons
	//about positions and shape ids.
	struct AnchorCandidate
	{
		uint32_t Row = 0;
		uint32_t Col = 0;
		uint32_t Usage = 0;
	};

	struct AnchorChoice
	{
		//Indices into the candidate list, in condition order.
		std::vector<size_t> Picked;
		//Recorded frames that are *not* variants of this screen and still
		//satisfy all of the picked conditions - i.e. frames where this screen
		//would be drawn over content it is not a picture of.
		uint32_t Rivals = 0;
		//No stable triple could tell the screen apart, so the pick fell back to
		//cells a variant may change (a combinatorial screen: a Tetris board).
		bool UsedVolatileCell = false;
	};

	//The F9.9 follow-up to ADR-0050's anchor rule (see TileSheetTypes.h for the
	//measurement): prefer cells no variant of this screen changes, and inside
	//that set pick the cells that most sharply separate the screen from the
	//rest of the recording. `capturedIndex` is the frame the screen PNG was
	//written from; out of range (no retained grid frame for it) degrades to
	//ADR-0050's plain rarity-and-spread greedy, which is also what an empty
	//stream yields.
	AnchorChoice SelectScreenAnchors(const std::vector<GridFrame>& frames, size_t capturedIndex, const std::vector<AnchorCandidate>& candidates);
}

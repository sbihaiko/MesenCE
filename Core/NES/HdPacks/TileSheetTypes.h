#pragma once
//ADR-0153 (Phase 9): shared vocabulary for the artist-legible sheet pipeline.
//Host-free on purpose - no pch.h, no Emulator, no console type - so
//MetatileVocabulary / ScreenStitcher / SheetGrouping / SheetRender all link
//into `make core-unit-tests` (same rule as Core/Shared/Video/BorderLayout.h,
//ADR-0127). HdPackBuilder is the only stateful partner: it records the grid
//stream and writes the bytes these modules return.
#include <cstdint>
#include <cstring>
#include <array>
#include <map>
#include <string>
#include <vector>

namespace MesenSheets
{
	//---- tuning constants (ADR-0153 §1, §2, §5) -----------------------------

	//A metatile pair joins an object only when both directions predict each
	//other: n >= MinPairCount and n/out(A) >= MinPairProb and n/in(B) >= MinPairProb.
	constexpr uint32_t kSheetMinPairCount = 3;
	constexpr double kSheetMinPairProb = 0.80;
	//Beyond this a "component" is a contiguous background region, not a figure.
	constexpr uint32_t kSheetMaxObjectCells = 32;
	//Diagnostic only since the §1 amendment: self-consistency saturates near 1
	//on every game, so it no longer gates the grid unit.
	constexpr double kGridConsistencyThreshold = 0.60;
	//A real grid has one parity with a markedly smaller vocabulary. Measured
	//0.20-0.34 (Zelda, attribute-aligned) vs 0.03-0.11 (Excitebike, no grid);
	//0.15 clears both ends whichever screen set feeds the vocabulary.
	constexpr double kGridPhaseAdvantage = 0.15;
	//A status-bar row keeps most of its columns across screens (labels) while a
	//few change (score, timer, lives), and carries real content - a stretch of
	//sky matches everywhere too, but draws nothing.
	constexpr double kHudRowFrozenRatio = 0.50;
	constexpr double kHudRowDrawnRatio = 0.25;
	//A recording is not one screen family: title cards, menus and game-over
	//screens share no row with the playfield. A column counts as frozen when its
	//most common shape covers this share of the screens, so a minority of
	//unrelated screens cannot hide a status bar.
	constexpr double kHudRowScreenAgreement = 0.60;
	//Below this the playfield is essentially text/menus: fall back to 8x8.
	constexpr uint32_t kMinMetatilePlacements = 64;
	//A 2x2 tuple counts towards consistency once it has been seen this often.
	constexpr uint32_t kGridConsistencyMinCount = 3;
	//F9.5: two OAM entries further apart than this are never joined. 32 px is a
	//4x4 block of 8x8 cells - half the kSheetMaxObjectCells budget - and past it
	//a constant offset says "both were on screen", not "these move together".
	constexpr int32_t kSpriteMaxOffset = 32;
	//Retained per-frame grids (de-duplicated); ~1.9 KB each.
	constexpr uint32_t kMaxSheetFrames = 4096;
	//1-cell gutter, transparent, between every sheet cell.
	constexpr uint32_t kSheetGutter = 1;
	//A map region narrower than this does not justify the continuous stitcher.
	constexpr uint32_t kContinuousMinWidth = 512;
	//One subject reaches the vocabulary under several keys: a mapper that swaps
	//CHR banks per animation frame (MMC2 in Punch-Out!!, MMC3 elsewhere)
	//delivers the same drawing under a different tile index, and CHR-RAM
	//re-uploads earn a fresh shape id for identical bytes. Measured by
	//scripts/spike_sheet_dedup.py over the 30-ROM library: 6906 vocabulary
	//cells collapse to 3733 subjects, and much of that is *exact* pixel
	//duplication (Ninja Gaiden 226 -> 67, Gauntlet 361 -> 105).
	//
	//The tolerance is the share of channel bytes allowed to differ before two
	//cells count as one subject, measured against the *ink* of the richer of
	//the two cells (pixels that are not its most common colour), never against
	//the cell area. Against the area it is not a tolerance at all: every
	//mostly-background metatile is within 10% of every other one, and the
	//first near-empty cell becomes an attractor - on a real Ninja Gaiden
	//recording 465 entries fell to 37 cells with a single cell holding 335 of
	//them. 0.10 was the value the spike measured with; it collapses bank
	//duplicates and near-identical animation frames without merging cells an
	//artist would paint differently. It is a measured starting point, not a
	//tuned optimum - the spike reports the curve.
	constexpr double kSheetAliasTolerance = 0.10;

	//---- F9.8: adjacency evidence before two screens share a map -----------
	//
	//A screen is appended to a map only when something measurable says it is a
	//neighbour. The evidence is a shared border band read through the scroll:
	//when a transition frame matches the already-placed screen at shift
	//(dx, dy), the cells that shift exposes at the leading edge lie *outside*
	//the placed screen, so they can only be the screen that was scrolling in -
	//and they must be the candidate's opposite edge. Without that, the screen
	//starts its own map instead of being concatenated at an arbitrary offset.
	//
	//Not measured on a fresh recording: re-recording needs the capture tool,
	//which this slice may not relink. The values are read off the only
	//stitched sequences on record, the 2026-09-04 spike (runs/spike-sheets):
	//Zelda's four accepted links score a whole-frame match of 0.73-0.77 at
	//shifts of 5-8 cells, i.e. the 16-25 % of the frame that did *not* match
	//the anchor is exactly the exposed band. On a real neighbour that band is
	//therefore almost entirely the candidate's content; 0.60 leaves room for
	//sprite overlap and a mid-transition sliver while still rejecting a band
	//that merely happens to carry the same tiles.
	constexpr double kStitchBandMatch = 0.60;
	//...and the band has to say something the anchor did not already say. A
	//screen that is mostly one backdrop tile - a Punch-Out!! profile card, a
	//text screen - agrees with every other screen's edge, so a bare band ratio
	//would rubber-stamp exactly the collage this slice exists to stop. The band
	//must therefore beat, by this margin, the share of the same cells the
	//anchor already carried at the same positions. Read off the spike again:
	//Zelda's dx=8 link scores 0.75 over the whole frame, i.e. 24 of 32 columns
	//are anchor-explained and the remaining 8 - the band - contributed nothing,
	//so a real neighbour's lead there is ~1.0. 0.25 is a wide safety margin
	//under that, and a backdrop-only band leads by 0.
	constexpr double kStitchBandLead = 0.25;
	//A band of fewer drawn cells than this is not a measurement - a strip of
	//sky agrees with anything. 24 cells is six unit-16 metatiles; Zelda's
	//narrowest accepted band (5 rows x 32 cols) is 160.
	constexpr uint32_t kStitchMinBandCells = 24;
	//A one-cell band cannot even carry one metatile of the candidate at grid
	//unit 16, so a shift that small is not evidence of a neighbour.
	constexpr int32_t kStitchMinShiftCells = 2;
	//Transition frames probed between two stable screens. The de-duplicated
	//stream (ADR-0153 §5) can put the whole transition in one entry or spread
	//it over many, so one fixed fraction of the gap is a lucky guess; three
	//evenly spread probes cover both shapes, and every probe still has to
	//clear the full evidence bar on its own.
	constexpr uint32_t kStitchTransitionProbes = 3;
	//---- F9.12: a continuous region ends when the world is replaced ---------
	//
	//Continuous mode had no notion of "this is a different place". Its only cut
	//was a whole-frame match below kMinMatch (0.5), and 0.5 is unreachable for a
	//screen swap that keeps the terrain: Super Mario Bros.' title screen is
	//drawn on top of the very start of world 1-1 - same hill, same bushes, same
	//ground - with a logo panel and a menu stamped into the sky. So the
	//title-to-level step reports dx == 0 ("the camera did not move") at a high
	//score, no cut fires, and PaintFrame's first-writer-wins bakes the logo,
	//"ONE PLUMBER / TWO PLUMBERS" and "TOP- 000000" into the level map's sky.
	//There is no seam in map-000.png because there is no offset: the two
	//screens are superimposed on the same world columns.
	//
	//The rule: a step that does *not* claim the camera moved is a claim that
	//both frames show the same place, so the whole playfield has to agree.
	//Below this share it did not - the content was replaced, not continued -
	//and the region ends. A step that does claim a shift is judged exactly as
	//before (kMinMatch), so a genuine scroller is not touched by this rule at
	//all: that is the Excitebike guard, by construction rather than by tuning.
	//
	//Measured, not swept, and not on a fresh recording - this slice may not
	//relink the capture tool. The numbers come off the 21 stable screens the
	//Super Mario Bros. recording installed under
	//`auto/textures/backgrounds/screen*.orig.png`, compared cell by cell (8x8,
	//pixel-exact) at the shift the stitcher accepts:
	//  - title screen vs the level's first screen: 0.700 agreement at dx == 0,
	//    i.e. 30 % of the playfield is title art the level does not have. It
	//    scores 0.699-0.700 against every one of the 19 level screens.
	//  - level screen vs the next level screen (camera still): 0.996-0.999.
	//  - Excitebike's screen001 vs screen002 (two unrelated non-scrolling
	//    screens): 0.746.
	//0.85 is the midpoint of that gap (0.848), so it sits ~0.15 above the
	//overlay case and ~0.15 below the tightest genuine same-place step. The
	//pixel-exact comparison is a proxy for the recorder's palette-agnostic
	//shape ids, and it can only *under*-count agreement (two cells that differ
	//only in palette read as different here and as equal in the stitcher), so
	//the genuine-step figures are a lower bound.
	constexpr double kStitchWorldAgree = 0.85;
	//Continuous mode: accept a non-zero x shift only when it beats "the camera
	//did not move" by this much. On near-uniform content every offset scores
	//alike and the argmax is arbitrary - that is how a still game grows a
	//kilopixel-wide strip of nothing. The margin is deliberately small: a real
	//scroll beats a still by tenths, not by hundredths, so 0.02 costs a genuine
	//scroller nothing. Unmeasured, for the same reason as kStitchBandMatch.
	constexpr double kStitchStillMargin = 0.02;

	constexpr uint32_t kGridCols = 32;
	constexpr uint32_t kGridRows = 30;

	//---- recorded data -----------------------------------------------------

	//An 8x8 background tile exactly as hires.txt keys it: the 16 CHR bytes plus
	//the 4-colour NES palette word ([31:24] = colour 0 ... [7:0] = colour 3).
	struct SheetTileKey
	{
		uint8_t TileData[16] = {};
		uint32_t PaletteColors = 0;

		bool operator==(const SheetTileKey& o) const
		{
			return PaletteColors == o.PaletteColors && memcmp(TileData, o.TileData, 16) == 0;
		}
		bool operator<(const SheetTileKey& o) const
		{
			int c = memcmp(TileData, o.TileData, 16);
			return c != 0 ? c < 0 : PaletteColors < o.PaletteColors;
		}
	};

	//Palette-agnostic shape id handed out by the recorder in first-sight order.
	using ShapeId = uint16_t;
	constexpr ShapeId kEmptyCell = 0xFFFF;

	//One recorded background frame: which shape sat at every 8x8 cell origin.
	//FineX is the sub-tile x scroll the cells were aligned to (0..7), so two
	//frames of the same screen at different scroll offsets compare equal.
	struct GridFrame
	{
		ShapeId Cells[kGridRows][kGridCols];
		uint8_t FineX = 0;
		uint32_t FrameNumber = 0;
		//How many consecutive recorded frames were identical to this one. The
		//recorder collapses duplicates, so "the screen held still for N frames"
		//reads as RepeatCount >= N instead of a run length in the stream.
		uint32_t RepeatCount = 1;
		//F9.9 (ADR-0156): this frame was written out as
		//backgrounds/screenNNN.png, so a `<background>` layer covers it at
		//render time. Set by HdPackBuilder when CaptureScreen succeeds; the
		//inference reads it to decide which cells the screen surface owns.
		bool Captured = false;

		GridFrame() { Clear(); }
		void Clear()
		{
			for(uint32_t r = 0; r < kGridRows; r++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					Cells[r][c] = kEmptyCell;
				}
			}
		}
		uint32_t DrawnCells() const
		{
			uint32_t n = 0;
			for(uint32_t r = 0; r < kGridRows; r++) {
				for(uint32_t c = 0; c < kGridCols; c++) {
					n += Cells[r][c] != kEmptyCell ? 1 : 0;
				}
			}
			return n;
		}
		bool SameCells(const GridFrame& o) const { return memcmp(Cells, o.Cells, sizeof(Cells)) == 0; }
	};

	//---- OAM (F9.5) --------------------------------------------------------

	//One sprite as the recorder saw it: the 8x8 shape id - taken *after* the OAM
	//flip bits are applied, so the mirrored half of a figure is its own shape and
	//can sit beside its twin on a sheet - plus its screen origin in pixels. An
	//8x16 sprite is recorded as its two 8x8 halves, which keeps the whole slice
	//on one unit and lets the grouping recover the tall figure by itself.
	struct OamEntry
	{
		ShapeId Shape = kEmptyCell;
		uint8_t X = 0;
		uint8_t Y = 0;

		bool operator==(const OamEntry& o) const { return Shape == o.Shape && X == o.X && Y == o.Y; }
	};

	//One frame's OAM, in OAM order. Consecutive identical frames collapse into
	//RepeatCount and the stream is capped at kMaxSheetFrames, exactly like
	//GridFrame - a paused screen must not manufacture evidence.
	struct OamFrame
	{
		std::vector<OamEntry> Entries;
		uint32_t FrameNumber = 0;
		uint32_t RepeatCount = 1;

		bool SameEntries(const OamFrame& o) const { return Entries == o.Entries; }
	};

	//---- vocabulary --------------------------------------------------------

	//A building block: 4 shapes (row-major) at grid unit 16, 1 shape + three
	//kEmptyCell at grid unit 8.
	struct MetatileKey
	{
		std::array<ShapeId, 4> Tiles = { kEmptyCell, kEmptyCell, kEmptyCell, kEmptyCell };

		bool operator==(const MetatileKey& o) const { return Tiles == o.Tiles; }
		bool operator<(const MetatileKey& o) const { return Tiles < o.Tiles; }
	};

	//Which sheet a cell belongs on. Split by context so a rupee counter never
	//sits between two trees (ADR-0153 §3).
	enum class SheetContext
	{
		Scene = 0,
		Hud = 1,
		Font = 2,
		Misc = 3
	};

	const char* ContextName(SheetContext context);

	//Automatic grid detection result; both the winner and the loser are
	//reported so a bad pick can be argued with (ADR-0153 §1).
	struct GridDetection
	{
		uint32_t Unit = 8;          //16 or 8
		uint8_t PhaseX = 0;         //cell parity the 16x16 grid is aligned to
		uint8_t PhaseY = 0;
		double ChosenConsistency = 0;
		double Alt8x8 = 0;
		double PhaseScores[4] = {}; //(0,0) (1,0) (0,1) (1,1)
		double PhaseAdvantage = 0;  //1 - distinct(best) / mean(distinct(others))
		bool HasGrid = false;       //false = the 2x2 cut is arbitrary, not the game's grid
	};

	struct MetatileEntry
	{
		MetatileKey Key;
		uint32_t Count = 0;
		SheetContext Context = SheetContext::Scene;
		bool Aligned = true; //false when only ever seen off the chosen phase
		//F9.9 (ADR-0156): every sighting of this cell, in the whole recorded
		//stream, sat where a captured screen already shows it, under the same
		//fine scroll. A `<background>` therefore covers it wherever it appears,
		//so its tile art is never the pixel that reaches the screen and a cell
		//spent on it in metatiles.png is dead paint. Kept in the vocabulary
		//(indexes are addresses - maps, objects and sprites cite them), left
		//off the contact sheet.
		bool ScreenResident = false;
	};

	//Directed adjacency counts between vocabulary entries, keyed (A, B).
	using AdjacencyMap = std::map<std::pair<uint32_t, uint32_t>, uint32_t>;

	//---- F9.9 routing floor (ADR-0156) -------------------------------------
	//
	//"Every sighting is explained" is trivially true of a recording that never
	//left one screen: the screen is captured, nothing else is ever seen, and
	//the whole scene vocabulary routes off metatiles.png. The pack that ships
	//is then worse than the one before the rule - an almost empty contact
	//sheet, and no way to tell it from a game that really is one screen.
	//
	//So routing is withheld unless the recording looks like gameplay. These are
	//two of the four clauses of scripts/gameplay_probe.py, chosen because they
	//need only what the builder already has at save time; the thresholds are
	//that script's, calibrated over 86 packs from three runs of a 30-ROM
	//library (17 of 20 hand-labelled menu-only recordings caught, no false
	//alarms).
	//
	//  - tile structure: how deterministically the frames reuse the same 2x2
	//    tuples. A tiled playfield saturates near 1.0; a run that only drew
	//    one-off compositions - a logo, a menu, a portrait - never accumulates
	//    repeats. Menu-only 0.76-0.87, gameplay >= 0.89.
	//  - misc share: cells off the detected grid with no adjacency support. A
	//    menu is drawn at text granularity, not on the game's grid. Gameplay
	//    <= 0.262; a Gauntlet run stuck in its menu, 0.635.
	//
	//Deliberately conservative in one direction only: a false "this is not
	//gameplay" costs the artist a fatter sheet, which is what they had before
	//F9.9. A false "this is gameplay" costs them the sheet.
	constexpr double kGameplayTileStructure = 0.86;
	constexpr double kGameplayMiscShare = 0.32;

	struct Vocabulary
	{
		GridDetection Grid;
		std::vector<MetatileEntry> Entries;
		//Vocabulary index of a metatile key.
		std::map<MetatileKey, uint32_t> Index;
		//Top rows that never change across distinct stable screens (the HUD).
		uint32_t HudRows = 0;
		//Bottom rows that never change (Metroid/SMB3-style status bars).
		uint32_t HudBottomRows = 0;
		AdjacencyMap East;
		AdjacencyMap South;
		uint32_t StableScreens = 0;
		uint32_t DistinctScreens = 0;
		//F9.9: set when the routing floor above refused the recording, so the
		//builder can say "withheld" rather than let it read as "nothing to
		//route" - the two look identical in a cell count.
		bool RoutingWithheld = false;

		int32_t Find(const MetatileKey& key) const
		{
			auto it = Index.find(key);
			return it == Index.end() ? -1 : (int32_t)it->second;
		}
	};

	//---- sheets ------------------------------------------------------------

	//A cell as laid out on a sheet. X/Y are the top-left in sheet pixels.
	struct SheetCell
	{
		uint32_t Index = 0;
		int32_t X = 0;
		int32_t Y = 0;
		uint32_t Count = 0;
		SheetContext Context = SheetContext::Scene;
		MetatileKey Key;
		int32_t Metatile = -1; //vocabulary index, for object/sprite/map cells
		//Vocabulary indexes that render to this same cell (ADR-0153 §3, alias
		//pass). Empty when the cell is the only key for its subject. The artist
		//paints the cell once; mep_build.py fans the crop back out to every
		//alias, so a bank-swapped duplicate can never drift out of sync with
		//the copy that was painted. AliasKeys carries their tile keys in the
		//same order: the sidecar has to be self-contained, or the round-trip
		//would need the vocabulary the artist never receives.
		std::vector<uint32_t> Aliases;
		std::vector<MetatileKey> AliasKeys;
	};

	//0xAARRGGBB, alpha 0 outside a cell (gutters and padding stay transparent).
	struct SheetImage
	{
		uint32_t Width = 0;
		uint32_t Height = 0;
		std::vector<uint32_t> Pixels;

		void Reset(uint32_t w, uint32_t h)
		{
			Width = w;
			Height = h;
			Pixels.assign((size_t)w * h, 0);
		}
		uint32_t* Row(uint32_t y) { return Pixels.data() + (size_t)y * Width; }
	};

	//Where one vocabulary cell was painted on a stitched map, in map pixels.
	struct SheetPlacement
	{
		int32_t X = 0;
		int32_t Y = 0;
		uint32_t Cell = 0;
	};

	enum class StitchMode
	{
		Screen = 0,
		Continuous = 1
	};

	//One connected map region. Placements are the slicing contract mep_build.py
	//reads back; the map itself is a paint surface, never a runtime layer.
	struct StitchedMap
	{
		StitchMode Mode = StitchMode::Screen;
		uint32_t Width = 0;  //in pixels
		uint32_t Height = 0;
		uint32_t HudRows = 0;
		std::vector<SheetPlacement> Placements;
		std::vector<std::string> Log; //per-screen decisions, for the run log
	};

	//Evidence for one edge that joined two cells into an object or a sprite.
	//Dx/Dy is where B sits relative to A, in cells: always (1,0)/(0,1) for a
	//metatile edge, any direction for an OAM edge (F9.5), which is why the
	//layout reads the offset instead of re-deriving it from Dir.
	struct GroupEdge
	{
		uint32_t A = 0;
		uint32_t B = 0;
		char Dir = 'E'; //'E', 'S', and for sprites also 'W' / 'N'
		int32_t Dx = 1;
		int32_t Dy = 0;
		uint32_t Count = 0;
		double ProbAB = 0;
		double ProbBA = 0;
	};

	struct SheetGroup
	{
		std::vector<SheetCell> Cells; //Metatile = vocabulary index, X/Y in cells
		std::vector<GroupEdge> Edges;
		uint32_t Columns = 0;
		uint32_t Rows = 0;
	};
}

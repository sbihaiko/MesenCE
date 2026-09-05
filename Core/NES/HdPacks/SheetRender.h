#pragma once
//ADR-0153 §3/§4 (Phase 9): pixels and sidecar JSON for the artist-legible
//sheets. Host-free (see TileSheetTypes.h); its stateful partner is
//HdPackBuilder, which owns the palette, the recorded shapes and the files.
//Everything here is pure: buffers in, buffers out - no I/O, no PNG encoding.
#include "NES/HdPacks/TileSheetTypes.h"
#include <functional>

namespace MesenSheets
{
	//Resolves a recorded shape id to a drawable tile (the representative
	//palette variant HdPackBuilder picked for that shape). May return nullptr
	//for a shape that never got art - the cell is then left transparent.
	using TileLookup = std::function<const SheetTileKey*(ShapeId)>;

	//NES master palette: 512 entries of 0x00RRGGBB (HdPackBuilder::_palette).
	using NesPalette = const uint32_t*;

	//---- pixels ------------------------------------------------------------

	//Draws one 8x8 tile at (x, y) of dst, opaque (alpha 0xFF) on all four
	//colour indexes - a transparent colour 0 would punch holes in a tree.
	//`transparentIndex0` is the sprite case (F9.5): OAM colour 0 *is* the
	//backdrop, so a sprite cell drawn opaque would ship a box around the figure.
	void RenderTile(const SheetTileKey& tile, NesPalette palette, SheetImage& dst, int32_t x, int32_t y, bool transparentIndex0 = false);

	//Draws a metatile (unit 16 = 2x2 tiles, unit 8 = a single tile) at (x, y).
	void RenderMetatile(const MetatileKey& key, const TileLookup& lookup, NesPalette palette, uint32_t unit, SheetImage& dst, int32_t x, int32_t y, bool transparentIndex0 = false);

	//Contact sheet of the given vocabulary indexes, `columns` per row, with a
	//kSheetGutter-wide transparent gutter around and between cells. Fills
	//outCells with each cell's sheet-pixel origin, count and context.
	SheetImage BuildContactSheet(const Vocabulary& vocab, const std::vector<uint32_t>& indexes, const TileLookup& lookup, NesPalette palette, uint32_t columns, std::vector<SheetCell>& outCells);

	//Nearest-neighbour upscale by an integer factor. The sheet PNG ships at the
	//pack scale so the artist paints on the canvas the pack renders at, while
	//the sidecar JSON keeps 1x logical coordinates (ADR-0153 §4).
	SheetImage Upscale(const SheetImage& source, uint32_t factor);

	//Number of columns that keeps a sheet roughly square, at least 1.
	uint32_t PreferredColumns(size_t cellCount);

	//---- alias pass (ADR-0153 §3, F9.7) ------------------------------------

	//Collapses `indexes` to one entry per *subject*: two vocabulary entries
	//that render to the same pixels (within `tolerance` of differing channel
	//bytes) are the same drawing arriving under different keys, which is what
	//a bank-swapping mapper produces. Returns the surviving indexes in their
	//original order - count-descending, so the sheet still opens on the blocks
	//the game is built out of - and fills `outAliases` with, for each survivor,
	//the indexes it absorbed.
	//
	//This collapses the *sheet*, not the vocabulary: maps and object groups
	//keep addressing entries by their original index, so nothing downstream has
	//to be renumbered. The artist paints fewer cells; mep_build.py fans each
	//painted cell back out over its aliases.
	std::vector<uint32_t> CollapseAliases(const Vocabulary& vocab, const std::vector<uint32_t>& indexes, const TileLookup& lookup, NesPalette palette, double tolerance, std::vector<std::vector<uint32_t>>& outAliases);

	//Paints a stitched map: every placement drawn at its map-pixel origin, no
	//gutters (a map must stay continuous for the seam test).
	SheetImage RenderMap(const StitchedMap& map, const Vocabulary& vocab, const TileLookup& lookup, NesPalette palette);

	//Paints one object/sprite group; group cell X/Y are in cells, and the sheet
	//adds the usual gutter so the artist can tell two blocks apart.
	SheetImage RenderGroup(const SheetGroup& group, const Vocabulary& vocab, const TileLookup& lookup, NesPalette palette, std::vector<SheetCell>& outCells, bool transparentIndex0 = false);

	//---- sidecar JSON ------------------------------------------------------

	//One document shape covers all four sheet kinds (ADR-0153 §4); the
	//kind-specific members are simply left empty when they do not apply.
	struct SheetJsonDoc
	{
		std::string Kind;          //"metatiles" | "hud" | "font" | "misc" | "map" | "object" | "sprite"
		std::string SheetFile;     //e.g. "metatiles.png"
		std::string ReferenceFile; //e.g. "metatiles.orig.png" ("" when absent)
		GridDetection Grid;
		uint32_t CellWidth = 16;
		uint32_t CellHeight = 16;
		uint32_t Gutter = kSheetGutter;
		uint32_t Columns = 1;
		std::vector<SheetCell> Cells;
		//F9.9: scene cells this sheet does *not* show because a captured screen
		//owns them (ADR-0156). Written so a reader can tell a sheet that is
		//small because the recording was thin from one that is small because
		//the routing worked - the two look identical in a cell count, and
		//scripts/gameplay_probe.py read the difference backwards until it had
		//this number.
		uint32_t RoutedCells = 0;

		//map only
		bool IsMap = false;
		StitchMode Mode = StitchMode::Screen;
		uint32_t HudRows = 0;
		std::vector<SheetPlacement> Placements;

		//object/sprite only
		std::vector<GroupEdge> Edges;
	};

	//Serialises `doc` to the ADR-0153 §4 schema. `lookup` resolves each cell's
	//shapes into the exact hires.txt keys, so a crop maps back to tile entries
	//with no guessing. Deterministic: same input, same bytes.
	std::string SerializeSheet(const SheetJsonDoc& doc, const TileLookup& lookup);
}

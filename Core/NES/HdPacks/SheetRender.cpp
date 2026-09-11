//ADR-0153 §3/§4 (Phase 9) - see SheetRender.h. Stateful partner: HdPackBuilder.
#include "NES/HdPacks/SheetRender.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <sstream>

namespace MesenSheets
{
	const char* ContextName(SheetContext context)
	{
		switch(context) {
			case SheetContext::Hud: return "hud";
			case SheetContext::Font: return "font";
			case SheetContext::Misc: return "misc";
			default: return "scene";
		}
	}

	void RenderTile(const SheetTileKey& tile, NesPalette palette, SheetImage& dst, int32_t x, int32_t y, bool transparentIndex0)
	{
		uint32_t colors[4];
		for(int c = 0; c < 4; c++) {
			colors[c] = palette[(tile.PaletteColors >> ((3 - c) * 8)) & 0x3F] | 0xFF000000;
		}
		if(transparentIndex0) {
			colors[0] = 0;
		}
		for(int row = 0; row < 8; row++) {
			int32_t py = y + row;
			if(py < 0 || py >= (int32_t)dst.Height) {
				continue;
			}
			uint8_t lo = tile.TileData[row];
			uint8_t hi = tile.TileData[row + 8];
			for(int col = 0; col < 8; col++) {
				int32_t px = x + col;
				if(px < 0 || px >= (int32_t)dst.Width) {
					continue;
				}
				int bit = 7 - col;
				int index = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1);
				if(index == 0 && transparentIndex0) {
					continue;
				}
				dst.Row((uint32_t)py)[px] = colors[index];
			}
		}
	}

	void RenderMetatile(const MetatileKey& key, const TileLookup& lookup, NesPalette palette, uint32_t unit, SheetImage& dst, int32_t x, int32_t y, bool transparentIndex0)
	{
		uint32_t tiles = unit >= 16 ? 4 : 1;
		for(uint32_t i = 0; i < tiles; i++) {
			if(key.Tiles[i] == kEmptyCell) {
				continue;
			}
			const SheetTileKey* tile = lookup ? lookup(key.Tiles[i]) : nullptr;
			if(!tile) {
				continue;
			}
			RenderTile(*tile, palette, dst, x + (int32_t)(i % 2) * 8, y + (int32_t)(i / 2) * 8, transparentIndex0);
		}
	}

	SheetImage Upscale(const SheetImage& source, uint32_t factor)
	{
		if(factor <= 1 || source.Width == 0 || source.Height == 0) {
			return source;
		}
		SheetImage out;
		out.Reset(source.Width * factor, source.Height * factor);
		for(uint32_t y = 0; y < out.Height; y++) {
			const uint32_t* src = source.Pixels.data() + (size_t)(y / factor) * source.Width;
			uint32_t* dst = out.Row(y);
			for(uint32_t x = 0; x < out.Width; x++) {
				dst[x] = src[x / factor];
			}
		}
		return out;
	}

	uint32_t PreferredColumns(size_t cellCount)
	{
		if(cellCount == 0) {
			return 1;
		}
		uint32_t columns = (uint32_t)std::ceil(std::sqrt((double)cellCount));
		return columns < 1 ? 1 : columns;
	}

	//---- alias pass --------------------------------------------------------

	//A cell's pixels, at 1x, as the comparison key. Rendering is the only
	//honest test: two entries hold different shape ids by construction, so
	//nothing short of the drawing itself tells you they are the same subject.
	static std::vector<uint32_t> RenderCellPixels(const Vocabulary& vocab, uint32_t index, const TileLookup& lookup, NesPalette palette)
	{
		uint32_t unit = vocab.Grid.Unit;
		SheetImage cell;
		cell.Reset(unit, unit);
		RenderMetatile(vocab.Entries[index].Key, lookup, palette, unit, cell, 0, 0);
		return cell.Pixels;
	}

	//How much of a cell is drawn at all: pixels that are not its most common
	//colour. The alias budget is a share of *this*, not of the cell area - with
	//an area budget every sparse metatile falls into whichever near-empty cell
	//came first, and it does: Ninja Gaiden collapsed 465 vocabulary entries to
	//37 cells with one of them swallowing 335 of them.
	static uint32_t InkCount(const std::vector<uint32_t>& pixels)
	{
		std::map<uint32_t, uint32_t> votes;
		for(size_t i = 0; i < pixels.size(); i++) {
			votes[pixels[i]]++;
		}
		uint32_t background = 0;
		for(const std::pair<const uint32_t, uint32_t>& vote : votes) {
			if(vote.second > background) {
				background = vote.second;
			}
		}
		return (uint32_t)pixels.size() - background;
	}

	//Channels that differ between two rendered cells, giving up once the budget
	//is blown - the early exit is what keeps an O(n^2) pass affordable on the
	//largest vocabulary in the library (Tetris, 657 cells).
	static bool WithinTolerance(const std::vector<uint32_t>& a, const std::vector<uint32_t>& b, uint32_t budget)
	{
		if(a.size() != b.size()) {
			return false;
		}
		uint32_t diff = 0;
		for(size_t i = 0; i < a.size(); i++) {
			if(a[i] == b[i]) {
				continue;
			}
			//Compare the four channels, so a pixel that is merely a shade off
			//costs less than a pixel that is a different colour entirely.
			for(int shift = 0; shift < 32; shift += 8) {
				if(((a[i] >> shift) & 0xFF) != ((b[i] >> shift) & 0xFF)) {
					diff++;
					if(diff > budget) {
						return false;
					}
				}
			}
		}
		return true;
	}

	std::vector<uint32_t> CollapseAliases(const Vocabulary& vocab, const std::vector<uint32_t>& indexes, const TileLookup& lookup, NesPalette palette, double tolerance, std::vector<std::vector<uint32_t>>& outAliases)
	{
		std::vector<uint32_t> survivors;
		outAliases.clear();
		if(indexes.empty()) {
			return survivors;
		}

		std::vector<std::vector<uint32_t>> pixels;
		std::vector<uint32_t> valid;
		for(uint32_t index : indexes) {
			if(index >= vocab.Entries.size()) {
				continue;
			}
			valid.push_back(index);
			pixels.push_back(RenderCellPixels(vocab, index, lookup, palette));
		}
		if(valid.empty()) {
			return survivors;
		}

		std::vector<uint32_t> ink;
		for(size_t i = 0; i < pixels.size(); i++) {
			ink.push_back(InkCount(pixels[i]));
		}

		std::vector<size_t> canonicalOf;
		for(size_t i = 0; i < valid.size(); i++) {
			size_t match = survivors.size();
			for(size_t s = 0; s < survivors.size(); s++) {
				//The richer of the two sets the budget, so a blank cell can
				//still absorb an exact duplicate of itself (budget 0) but
				//never a cell that draws something.
				uint32_t drawn = ink[i] > ink[canonicalOf[s]] ? ink[i] : ink[canonicalOf[s]];
				uint32_t budget = (uint32_t)(tolerance * drawn * 4);
				if(WithinTolerance(pixels[i], pixels[canonicalOf[s]], budget)) {
					match = s;
					break;
				}
			}
			if(match == survivors.size()) {
				survivors.push_back(valid[i]);
				canonicalOf.push_back(i);
				outAliases.emplace_back();
			} else {
				outAliases[match].push_back(valid[i]);
			}
		}
		return survivors;
	}

	SheetImage BuildContactSheet(const Vocabulary& vocab, const std::vector<uint32_t>& indexes, const TileLookup& lookup, NesPalette palette, uint32_t columns, std::vector<SheetCell>& outCells, bool transparentIndex0)
	{
		SheetImage image;
		outCells.clear();
		if(indexes.empty()) {
			return image;
		}
		if(columns == 0) {
			columns = 1;
		}
		uint32_t unit = vocab.Grid.Unit;
		uint32_t stride = unit + kSheetGutter;
		uint32_t rows = (uint32_t)((indexes.size() + columns - 1) / columns);
		image.Reset(columns * stride + kSheetGutter, rows * stride + kSheetGutter);

		for(size_t i = 0; i < indexes.size(); i++) {
			uint32_t vocabIndex = indexes[i];
			if(vocabIndex >= vocab.Entries.size()) {
				continue;
			}
			const MetatileEntry& entry = vocab.Entries[vocabIndex];
			SheetCell cell;
			cell.Index = (uint32_t)i;
			cell.X = (int32_t)(kSheetGutter + (i % columns) * stride);
			cell.Y = (int32_t)(kSheetGutter + (i / columns) * stride);
			cell.Count = entry.Count;
			cell.Context = entry.Context;
			cell.Key = entry.Key;
			cell.Metatile = (int32_t)vocabIndex;
			RenderMetatile(entry.Key, lookup, palette, unit, image, cell.X, cell.Y, transparentIndex0);
			outCells.push_back(cell);
		}
		return image;
	}

	SheetImage RenderMap(const StitchedMap& map, const Vocabulary& vocab, const TileLookup& lookup, NesPalette palette)
	{
		SheetImage image;
		//kMaxMapPixels: an empty image is the "refused" answer, checked by the
		//caller before it names a file (HdPackBuilder::WriteMapSheets logs it).
		if(map.Width == 0 || map.Height == 0 || (uint64_t)map.Width * map.Height > kMaxMapPixels) {
			return image;
		}
		image.Reset(map.Width, map.Height);
		for(const SheetPlacement& placement : map.Placements) {
			if(placement.Cell >= vocab.Entries.size()) {
				continue;
			}
			RenderMetatile(vocab.Entries[placement.Cell].Key, lookup, palette, vocab.Grid.Unit, image, placement.X, placement.Y);
		}
		return image;
	}

	SheetImage RenderGroup(const SheetGroup& group, const Vocabulary& vocab, const TileLookup& lookup, NesPalette palette, std::vector<SheetCell>& outCells, bool transparentIndex0)
	{
		SheetImage image;
		outCells.clear();
		if(group.Cells.empty() || group.Columns == 0 || group.Rows == 0) {
			return image;
		}
		uint32_t unit = vocab.Grid.Unit;
		uint32_t stride = unit + kSheetGutter;
		image.Reset(group.Columns * stride + kSheetGutter, group.Rows * stride + kSheetGutter);
		for(const SheetCell& source : group.Cells) {
			if(source.Metatile < 0 || (size_t)source.Metatile >= vocab.Entries.size()) {
				continue;
			}
			SheetCell cell = source;
			cell.X = (int32_t)kSheetGutter + source.X * (int32_t)stride;
			cell.Y = (int32_t)kSheetGutter + source.Y * (int32_t)stride;
			cell.Key = vocab.Entries[source.Metatile].Key;
			cell.Count = vocab.Entries[source.Metatile].Count;
			cell.Context = vocab.Entries[source.Metatile].Context;
			RenderMetatile(cell.Key, lookup, palette, unit, image, cell.X, cell.Y, transparentIndex0);
			outCells.push_back(cell);
		}
		return image;
	}

	//---- JSON --------------------------------------------------------------

	static std::string ToHex(uint32_t value, int digits)
	{
		static const char* kDigits = "0123456789ABCDEF";
		std::string out(digits, '0');
		for(int i = digits - 1; i >= 0; i--) {
			out[i] = kDigits[value & 0xF];
			value >>= 4;
		}
		return out;
	}

	static void AppendTiles(std::stringstream& json, const MetatileKey& key, uint32_t unit, const TileLookup& lookup)
	{
		uint32_t tiles = unit >= 16 ? 4 : 1;
		json << "[";
		bool first = true;
		for(uint32_t i = 0; i < tiles; i++) {
			const SheetTileKey* tile = (key.Tiles[i] != kEmptyCell && lookup) ? lookup(key.Tiles[i]) : nullptr;
			if(!first) {
				json << ", ";
			}
			first = false;
			if(!tile) {
				json << "null";
				continue;
			}
			std::string data;
			for(int b = 0; b < 16; b++) {
				data += ToHex(tile->TileData[b], 2);
			}
			json << "{ \"tile\": \"" << data << "\", \"palette\": \"" << ToHex(tile->PaletteColors, 8) << "\" }";
		}
		json << "]";
	}

	static std::string Fixed(double value)
	{
		std::stringstream out;
		out.setf(std::ios::fixed);
		out.precision(4);
		out << value;
		return out.str();
	}

	std::string SerializeSheet(const SheetJsonDoc& doc, const TileLookup& lookup)
	{
		std::stringstream json;
		json << "{\n";
		json << "  \"version\": 1,\n";
		json << "  \"kind\": \"" << doc.Kind << "\",\n";
		json << "  \"gridUnit\": " << doc.Grid.Unit << ",\n";
		json << "  \"gridPhase\": { \"x\": " << (uint32_t)doc.Grid.PhaseX << ", \"y\": " << (uint32_t)doc.Grid.PhaseY << " },\n";
		json << "  \"hasGrid\": " << (doc.Grid.HasGrid ? "true" : "false") << ",\n";
		json << "  \"phaseAdvantage\": " << Fixed(doc.Grid.PhaseAdvantage) << ",\n";
		//Diagnostics only since ADR-0153's amendment: the saturating consistency
		//measure decides nothing, phaseAdvantage does.
		json << "  \"gridConsistency\": { \"chosen\": " << Fixed(doc.Grid.ChosenConsistency) << ", \"alt8x8\": " << Fixed(doc.Grid.Alt8x8) << " },\n";
		json << "  \"cell\": { \"w\": " << doc.CellWidth << ", \"h\": " << doc.CellHeight << " },\n";
		json << "  \"gutter\": " << doc.Gutter << ",\n";
		json << "  \"columns\": " << doc.Columns << ",\n";
		json << "  \"routedCells\": " << doc.RoutedCells << ",\n";
		json << "  \"sheet\": \"" << doc.SheetFile << "\",\n";
		json << "  \"reference\": \"" << doc.ReferenceFile << "\",\n";

		if(doc.IsMap) {
			json << "  \"mode\": \"" << (doc.Mode == StitchMode::Continuous ? "continuous" : "screen") << "\",\n";
			json << "  \"hudRows\": " << doc.HudRows << ",\n";
			json << "  \"placements\": [";
			for(size_t i = 0; i < doc.Placements.size(); i++) {
				json << (i ? ",\n    " : "\n    ");
				json << "{ \"x\": " << doc.Placements[i].X << ", \"y\": " << doc.Placements[i].Y << ", \"cell\": " << doc.Placements[i].Cell << " }";
			}
			json << (doc.Placements.empty() ? "],\n" : "\n  ],\n");
		}

		if(!doc.Edges.empty()) {
			json << "  \"evidence\": [";
			for(size_t i = 0; i < doc.Edges.size(); i++) {
				const GroupEdge& edge = doc.Edges[i];
				json << (i ? ",\n    " : "\n    ");
				json << "{ \"a\": " << edge.A << ", \"b\": " << edge.B << ", \"dir\": \"" << edge.Dir
					<< "\", \"dx\": " << edge.Dx << ", \"dy\": " << edge.Dy
					<< ", \"count\": " << edge.Count << ", \"pAB\": " << Fixed(edge.ProbAB) << ", \"pBA\": " << Fixed(edge.ProbBA) << " }";
			}
			json << "\n  ],\n";
		}

		json << "  \"cells\": [";
		for(size_t i = 0; i < doc.Cells.size(); i++) {
			const SheetCell& cell = doc.Cells[i];
			json << (i ? ",\n    " : "\n    ");
			json << "{ \"index\": " << cell.Index
				<< ", \"x\": " << cell.X << ", \"y\": " << cell.Y
				<< ", \"count\": " << cell.Count
				<< ", \"context\": \"" << ContextName(cell.Context) << "\"";
			if(cell.Metatile >= 0) {
				json << ", \"metatile\": " << cell.Metatile;
			}
			if(!cell.Aliases.empty()) {
				//Every other vocabulary entry that renders to this cell, with
				//its own tile keys, so the round-trip can paint them all from
				//the one crop without consulting a vocabulary the artist never
				//receives (ADR-0153 §3/§4).
				json << ", \"aliases\": [";
				for(size_t a = 0; a < cell.Aliases.size(); a++) {
					json << (a ? ", " : "") << "{ \"metatile\": " << cell.Aliases[a] << ", \"tiles\": ";
					AppendTiles(json, a < cell.AliasKeys.size() ? cell.AliasKeys[a] : MetatileKey(), doc.Grid.Unit, lookup);
					json << " }";
				}
				json << "]";
			}
			json << ", \"label\": \"\", \"tiles\": ";
			AppendTiles(json, cell.Key, doc.Grid.Unit, lookup);
			json << " }";
		}
		json << (doc.Cells.empty() ? "]\n" : "\n  ]\n");
		json << "}\n";
		return json.str();
	}

	//ADR-0164 §1 (F9.17): see SheetRender.h. The background block is cheap to
	//make complete - the East/South maps are already bounded by the vocabulary,
	//so nothing is pruned and the degree totals a reader recomputes ADR-0153 §2
	//from are exact; the sprites block keeps the far-field statistics the offset
	//histogram cannot answer and prunes only within the 32 px histogram itself.
	std::string SerializeAdjacency(const Vocabulary& background, const Vocabulary& sprites, const SpriteAdjacencyStats& stats, const TileLookup& lookup, const std::map<uint32_t, std::vector<ScreenSite>>& residentSites)
	{
		//One edge plus its direction, for the deterministic (a, b, dir) order.
		struct Edge
		{
			uint32_t A;
			uint32_t B;
			char Dir;
			uint32_t Count;
		};

		std::vector<Edge> edges;
		std::vector<uint32_t> outE(background.Entries.size(), 0), inE(background.Entries.size(), 0);
		std::vector<uint32_t> outS(background.Entries.size(), 0), inS(background.Entries.size(), 0);
		edges.reserve(background.East.size() + background.South.size());
		for(const auto& entry : background.East) {
			uint32_t a = entry.first.first;
			uint32_t b = entry.first.second;
			outE[a] += entry.second;
			inE[b] += entry.second;
			edges.push_back({ a, b, 'E', entry.second });
		}
		for(const auto& entry : background.South) {
			uint32_t a = entry.first.first;
			uint32_t b = entry.first.second;
			outS[a] += entry.second;
			inS[b] += entry.second;
			edges.push_back({ a, b, 'S', entry.second });
		}
		std::sort(edges.begin(), edges.end(), [](const Edge& a, const Edge& b) {
			if(a.A != b.A) { return a.A < b.A; }
			if(a.B != b.B) { return a.B < b.B; }
			return a.Dir < b.Dir;
		});

		std::stringstream json;
		json << "{\n";
		json << "  \"version\": 1,\n";
		json << "  \"kind\": \"adjacency\",\n";
		json << "  \"background\": {\n";
		json << "    \"vocabulary\": \"metatiles.json\",\n";
		json << "    \"vocabularySize\": " << background.Entries.size() << ",\n";
		json << "    \"gridUnit\": " << background.Grid.Unit << ",\n";
		json << "    \"distinctScreens\": " << background.DistinctScreens << ",\n";
		json << "    \"nodes\": [";
		for(size_t i = 0; i < background.Entries.size(); i++) {
			const MetatileEntry& entry = background.Entries[i];
			json << (i ? ",\n      " : "\n      ");
			json << "{ \"cell\": " << i
				<< ", \"count\": " << entry.Count
				<< ", \"context\": \"" << ContextName(entry.Context) << "\""
				<< ", \"outE\": " << outE[i] << ", \"outS\": " << outS[i]
				<< ", \"inE\": " << inE[i] << ", \"inS\": " << inS[i];
			auto sit = residentSites.find((uint32_t)i);
			if(sit != residentSites.end() && !sit->second.empty()) {
				//ADR-0166 (F9.18): the screens that own this node's pixels, so a
				//reader crops them from backgrounds/<screen>.orig.png instead of
				//failing. Only present on resident nodes - a node a sheet shows
				//needs no screen source.
				json << ", \"screens\": [";
				for(size_t s = 0; s < sit->second.size(); s++) {
					json << (s ? ", " : "")
						<< "{ \"screen\": \"" << sit->second[s].Screen << "\""
						<< ", \"x\": " << sit->second[s].X
						<< ", \"y\": " << sit->second[s].Y << " }";
				}
				json << "]";
			}
			json << ", \"tiles\": ";
			AppendTiles(json, entry.Key, background.Grid.Unit, lookup);
			json << " }";
		}
		json << (background.Entries.empty() ? "],\n" : "\n    ],\n");
		json << "    \"edges\": [";
		for(size_t i = 0; i < edges.size(); i++) {
			json << (i ? ",\n      " : "\n      ");
			json << "{ \"a\": " << edges[i].A << ", \"b\": " << edges[i].B
				<< ", \"dir\": \"" << edges[i].Dir << "\", \"count\": " << edges[i].Count << " }";
		}
		json << (edges.empty() ? "]\n" : "\n    ]\n");
		json << "  }";

		if(!sprites.Entries.empty()) {
			json << ",\n  \"sprites\": {\n";
			json << "    \"vocabulary\": \"sprites.json\",\n";
			json << "    \"vocabularySize\": " << sprites.Entries.size() << ",\n";
			json << "    \"oamFrames\": " << stats.OamFrames << ",\n";
			json << "    \"nodes\": [";
			for(size_t i = 0; i < sprites.Entries.size(); i++) {
				const MetatileEntry& entry = sprites.Entries[i];
				json << (i ? ",\n      " : "\n      ");
				json << "{ \"cell\": " << i
					<< ", \"appearances\": " << entry.Count
					<< ", \"floors\": [";
				const std::vector<SpriteFloorBand> floors = i < stats.Floors.size() ? stats.Floors[i] : std::vector<SpriteFloorBand>();
				for(size_t f = 0; f < floors.size(); f++) {
					json << (f ? ", " : "");
					json << "{ \"bottom\": " << floors[f].Bottom << ", \"count\": " << floors[f].Count << " }";
				}
				json << "], \"tiles\": ";
				AppendTiles(json, entry.Key, sprites.Grid.Unit, lookup);
				json << " }";
			}
			json << "\n    ],\n";
			json << "    \"pairs\": [";
			for(size_t i = 0; i < stats.Pairs.size(); i++) {
				const SpritePairStat& pair = stats.Pairs[i];
				json << (i ? ",\n      " : "\n      ");
				json << "{ \"a\": " << pair.A << ", \"b\": " << pair.B
					<< ", \"coFrames\": " << pair.CoFrames
					<< ", \"count\": " << pair.Count
					<< ", \"offsets\": [";
				for(size_t o = 0; o < pair.Offsets.size(); o++) {
					json << (o ? ", " : "");
					json << "{ \"dx\": " << pair.Offsets[o].Dx << ", \"dy\": " << pair.Offsets[o].Dy << ", \"count\": " << pair.Offsets[o].Count << " }";
				}
				json << "], \"other\": " << pair.Other << " }";
			}
			json << (stats.Pairs.empty() ? "]\n" : "\n    ]\n");
			json << "  }\n";
		} else {
			json << "\n";
		}
		json << "}\n";
		return json.str();
	}

	//ADR-0170 §1 (F9.19): see SheetRender.h. Everything hard about a pose was
	//decided by BuildPoses - the clustering, the normalisation, the sets-equal
	//identity, the thresholds and the cap - so this is a transcription, and it
	//deliberately stays one: no field here is computed, because a number the
	//serializer derives is a number the unit tests cannot reach.
	std::string SerializePoses(const Vocabulary& sprites, const PoseStats& stats)
	{
		std::stringstream json;
		json << "{\n";
		json << "  \"version\": 1,\n";
		//The offset unit, so dx/dy read as cells without the reader assuming 8.
		json << "  \"unit\": " << sprites.Grid.Unit << ",\n";
		//Frames a pose's own "frames" is a share of: retained frames weighted by
		//RepeatCount, the universe BuildPoses counted in. The truncation counts
		//(poses found vs kept vs capped) stay in the save-time report line, per
		//ADR-0170 §2 - the file states its sampling, not its own pruning history.
		json << "  \"frames\": " << stats.Frames << ",\n";
		json << "  \"poses\": [";
		for(size_t i = 0; i < stats.Poses.size(); i++) {
			const PoseEntry& pose = stats.Poses[i];
			//Sorted by frames descending, so the id is the array position and
			//carries the ranking with it - nothing else keys a pose.
			char id[16];
			snprintf(id, sizeof(id), "pose%03u", (uint32_t)i);
			json << (i ? ",\n    " : "\n    ");
			json << "{ \"id\": \"" << id << "\""
				<< ", \"frames\": " << pose.Frames
				<< ", \"size\": [" << pose.Width << ", " << pose.Height << "]"
				<< ", \"tiles\": [";
			for(size_t t = 0; t < pose.Tiles.size(); t++) {
				const PoseTile& tile = pose.Tiles[t];
				json << (t ? ", " : "");
				json << "{ \"node\": " << tile.Node << ", \"dx\": " << tile.Dx << ", \"dy\": " << tile.Dy << " }";
			}
			json << "] }";
		}
		json << (stats.Poses.empty() ? "]\n" : "\n  ]\n");
		json << "}\n";
		return json.str();
	}
}

#pragma once
//ADR-0149 (Phase 8, Slice F8.3b): host-free layout/compositing math for the
//enhancement-pack border layer. Deliberately depends on nothing beyond the
//standard library so `make core-unit-tests` can link it without the Emulator;
//VideoRenderer owns file I/O, PNG decoding and settings and delegates the
//pure math here.
#include <cstdint>
#include <string>

enum class BorderScaleMode : uint8_t
{
	//Scale the canvas to fill the output while keeping its aspect ratio
	//(neutral letterboxing outside the canvas rect).
	Fit = 0,
	//Stretch the canvas to the whole output surface.
	Stretch = 1
};

struct BorderRect
{
	int32_t X = 0;
	int32_t Y = 0;
	uint32_t Width = 0;
	uint32_t Height = 0;

	bool operator==(const BorderRect& o) const { return X == o.X && Y == o.Y && Width == o.Width && Height == o.Height; }
	bool operator!=(const BorderRect& o) const { return !(*this == o); }
};

struct BorderLayout
{
	//Canvas = pixel size of border.png (the composited frame has this size).
	uint32_t CanvasWidth = 0;
	uint32_t CanvasHeight = 0;

	//Viewport = where the game frame lands inside the canvas (border.json
	//`viewport`; may be missing/invalid, in which case ApplyDefaultViewport()
	//supplies the ADR-0149 §1 heuristic).
	int32_t ViewportX = 0;
	int32_t ViewportY = 0;
	uint32_t ViewportWidth = 0;
	uint32_t ViewportHeight = 0;

	BorderScaleMode ScaleMode = BorderScaleMode::Fit;

	//false = border.png blended over the game (default); true = border drawn
	//first and the game copied strictly over the viewport.
	bool Underlay = false;

	//Layout for a canvas with no border.json at all: defaults + heuristic viewport.
	static BorderLayout ForCanvas(uint32_t canvasWidth, uint32_t canvasHeight);

	//Parses border.json's `scale_mode` value; returns false (and leaves `out`
	//untouched) for anything other than "fit"/"stretch".
	static bool ParseScaleMode(const std::string& value, BorderScaleMode& out);

	//True once the viewport has a non-zero area (a zero dimension means
	//"absent or invalid" and triggers the default heuristic).
	bool HasViewport() const { return ViewportWidth > 0 && ViewportHeight > 0; }

	//ADR-0149 §1 heuristic: 4:3 area, full canvas height, horizontally
	//centred inside the (typically 16:9) canvas. Only applied when the
	//viewport is missing/invalid, so an authored viewport always wins.
	void ApplyDefaultViewportIfMissing();

	//True when the viewport lies entirely inside the canvas.
	bool IsViewportInsideCanvas() const;

	//Viewport intersected with the canvas (what actually gets drawn); an
	//empty rect when the two don't overlap.
	BorderRect ClampedViewport() const;

	//Where the canvas lands on an output surface of outputWidth x outputHeight
	//according to ScaleMode (Fit letterboxes/pillarboxes, Stretch fills).
	BorderRect CanvasRectOnOutput(uint32_t outputWidth, uint32_t outputHeight) const;

	//Where the game viewport lands on the output surface (the viewport mapped
	//through CanvasRectOnOutput).
	BorderRect ViewportRectOnOutput(uint32_t outputWidth, uint32_t outputHeight) const;
};

//Standard source-over blend of one 0xAARRGGBB pixel (`src`, the border) onto
//another (`dst`, the game/canvas). Integer arithmetic, /255 rounding-down;
//alpha 255 returns src verbatim, alpha 0 returns dst verbatim.
uint32_t BorderBlendOver(uint32_t dst, uint32_t src);

//Nearest-neighbour copy of the srcWidth x srcHeight game frame into the
//layout's viewport on a CanvasWidth x CanvasHeight `dst` surface. Viewport
//pixels outside the canvas are skipped (clamping); canvas pixels outside the
//viewport are left untouched.
void BorderDrawGameIntoViewport(uint32_t* dst, const BorderLayout& layout, const uint32_t* src, uint32_t srcWidth, uint32_t srcHeight);

//Full composite of one frame: overlay mode clears `dst` to 0 (transparent
//black), draws the game into the viewport and blends `border` on top;
//underlay mode copies `border` then draws the game over the viewport. `dst` and
//`border` are CanvasWidth * CanvasHeight pixels.
void BorderCompositeFrame(uint32_t* dst, const uint32_t* border, const BorderLayout& layout, const uint32_t* src, uint32_t srcWidth, uint32_t srcHeight);

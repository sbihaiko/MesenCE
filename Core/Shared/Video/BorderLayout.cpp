#include "pch.h"
//ADR-0149 (Phase 8, Slice F8.3b): host-free border layout/compositing math.
//pch.h only satisfies the Windows precompiled-header build; nothing from it is
//used, so `make core-unit-tests` links this file without the Emulator.
#include "Shared/Video/BorderLayout.h"
#include <algorithm>
#include <cstring>

BorderLayout BorderLayout::ForCanvas(uint32_t canvasWidth, uint32_t canvasHeight)
{
	BorderLayout layout;
	layout.CanvasWidth = canvasWidth;
	layout.CanvasHeight = canvasHeight;
	layout.ApplyDefaultViewportIfMissing();
	return layout;
}

bool BorderLayout::ParseScaleMode(const std::string& value, BorderScaleMode& out)
{
	if(value == "fit") {
		out = BorderScaleMode::Fit;
		return true;
	}
	if(value == "stretch") {
		out = BorderScaleMode::Stretch;
		return true;
	}
	return false;
}

void BorderLayout::ApplyDefaultViewportIfMissing()
{
	if(HasViewport()) {
		return;
	}
	//Default 4:3 area inside a (16:9) canvas: full height, centred horizontally
	ViewportHeight = CanvasHeight;
	ViewportWidth = (CanvasHeight * 4) / 3;
	ViewportX = (CanvasWidth > ViewportWidth) ? (int32_t)((CanvasWidth - ViewportWidth) / 2) : 0;
	ViewportY = 0;
}

bool BorderLayout::IsViewportInsideCanvas() const
{
	if(ViewportX < 0 || ViewportY < 0) {
		return false;
	}
	return (uint64_t)ViewportX + ViewportWidth <= CanvasWidth && (uint64_t)ViewportY + ViewportHeight <= CanvasHeight;
}

BorderRect BorderLayout::ClampedViewport() const
{
	int64_t x0 = std::max<int64_t>(ViewportX, 0);
	int64_t y0 = std::max<int64_t>(ViewportY, 0);
	int64_t x1 = std::min<int64_t>((int64_t)ViewportX + ViewportWidth, CanvasWidth);
	int64_t y1 = std::min<int64_t>((int64_t)ViewportY + ViewportHeight, CanvasHeight);
	BorderRect r;
	if(x1 <= x0 || y1 <= y0) {
		return r;
	}
	r.X = (int32_t)x0;
	r.Y = (int32_t)y0;
	r.Width = (uint32_t)(x1 - x0);
	r.Height = (uint32_t)(y1 - y0);
	return r;
}

BorderRect BorderLayout::CanvasRectOnOutput(uint32_t outputWidth, uint32_t outputHeight) const
{
	BorderRect r;
	if(CanvasWidth == 0 || CanvasHeight == 0 || outputWidth == 0 || outputHeight == 0) {
		return r;
	}
	if(ScaleMode == BorderScaleMode::Stretch) {
		r.Width = outputWidth;
		r.Height = outputHeight;
		return r;
	}
	//Fit: largest canvas-aspect rect inside the output, centred.
	//Compare aspects via cross-multiplication to stay in integers.
	uint64_t outByCanvasH = (uint64_t)outputWidth * CanvasHeight;
	uint64_t canvasByOutH = (uint64_t)CanvasWidth * outputHeight;
	if(outByCanvasH >= canvasByOutH) {
		//Output is wider than (or same as) the canvas: full height, pillarbox
		r.Height = outputHeight;
		r.Width = (uint32_t)(canvasByOutH / CanvasHeight);
	} else {
		//Output is taller than the canvas: full width, letterbox
		r.Width = outputWidth;
		r.Height = (uint32_t)(outByCanvasH / CanvasWidth);
	}
	r.X = (int32_t)((outputWidth - r.Width) / 2);
	r.Y = (int32_t)((outputHeight - r.Height) / 2);
	return r;
}

BorderRect BorderLayout::ViewportRectOnOutput(uint32_t outputWidth, uint32_t outputHeight) const
{
	BorderRect canvas = CanvasRectOnOutput(outputWidth, outputHeight);
	BorderRect r;
	if(canvas.Width == 0 || canvas.Height == 0) {
		return r;
	}
	//Map the (clamped) viewport edges through the canvas rect
	BorderRect vp = ClampedViewport();
	if(vp.Width == 0 || vp.Height == 0) {
		return r;
	}
	int64_t x0 = canvas.X + ((int64_t)vp.X * canvas.Width) / CanvasWidth;
	int64_t y0 = canvas.Y + ((int64_t)vp.Y * canvas.Height) / CanvasHeight;
	int64_t x1 = canvas.X + ((int64_t)(vp.X + vp.Width) * canvas.Width) / CanvasWidth;
	int64_t y1 = canvas.Y + ((int64_t)(vp.Y + vp.Height) * canvas.Height) / CanvasHeight;
	r.X = (int32_t)x0;
	r.Y = (int32_t)y0;
	r.Width = (uint32_t)std::max<int64_t>(x1 - x0, 0);
	r.Height = (uint32_t)std::max<int64_t>(y1 - y0, 0);
	return r;
}

uint32_t BorderBlendOver(uint32_t dst, uint32_t src)
{
	uint32_t sa = (src >> 24) & 0xFF;
	if(sa == 255) {
		return src;
	}
	if(sa == 0) {
		return dst;
	}
	uint32_t sr = (src >> 16) & 0xFF;
	uint32_t sg = (src >> 8) & 0xFF;
	uint32_t sb = src & 0xFF;

	uint32_t da = (dst >> 24) & 0xFF;
	uint32_t dr = (dst >> 16) & 0xFF;
	uint32_t dg = (dst >> 8) & 0xFF;
	uint32_t db = dst & 0xFF;

	uint32_t invA = 255 - sa;
	uint32_t outR = (sr * sa + dr * invA) / 255;
	uint32_t outG = (sg * sa + dg * invA) / 255;
	uint32_t outB = (sb * sa + db * invA) / 255;
	uint32_t outA = sa + (da * invA) / 255;
	return (outA << 24) | (outR << 16) | (outG << 8) | outB;
}

void BorderDrawGameIntoViewport(uint32_t* dst, const BorderLayout& layout, const uint32_t* src, uint32_t srcWidth, uint32_t srcHeight)
{
	if(!layout.HasViewport() || srcWidth == 0 || srcHeight == 0) {
		return;
	}
	for(uint32_t vy = 0; vy < layout.ViewportHeight; vy++) {
		int32_t dy = layout.ViewportY + (int32_t)vy;
		if(dy < 0 || dy >= (int32_t)layout.CanvasHeight) {
			continue;
		}
		uint32_t sy = (uint32_t)(((uint64_t)vy * srcHeight) / layout.ViewportHeight);
		const uint32_t* srcRow = src + (size_t)sy * srcWidth;
		uint32_t* dstRow = dst + (size_t)dy * layout.CanvasWidth;
		for(uint32_t vx = 0; vx < layout.ViewportWidth; vx++) {
			int32_t dx = layout.ViewportX + (int32_t)vx;
			if(dx < 0 || dx >= (int32_t)layout.CanvasWidth) {
				continue;
			}
			uint32_t sx = (uint32_t)(((uint64_t)vx * srcWidth) / layout.ViewportWidth);
			dstRow[dx] = srcRow[sx];
		}
	}
}

void BorderCompositeFrame(uint32_t* dst, const uint32_t* border, const BorderLayout& layout, const uint32_t* src, uint32_t srcWidth, uint32_t srcHeight)
{
	size_t totalPixels = (size_t)layout.CanvasWidth * layout.CanvasHeight;
	if(totalPixels == 0) {
		return;
	}
	if(layout.Underlay) {
		//Underlay: border first, then the game strictly over the viewport
		memcpy(dst, border, totalPixels * sizeof(uint32_t));
		BorderDrawGameIntoViewport(dst, layout, src, srcWidth, srcHeight);
	} else {
		//Overlay (default): clear, draw the game into the viewport, blend border.png on top
		memset(dst, 0, totalPixels * sizeof(uint32_t));
		BorderDrawGameIntoViewport(dst, layout, src, srcWidth, srcHeight);
		for(size_t i = 0; i < totalPixels; i++) {
			dst[i] = BorderBlendOver(dst[i], border[i]);
		}
	}
}

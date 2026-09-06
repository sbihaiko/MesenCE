using System;

namespace Mesen.Logic;

//P.7 ("16:9 stretch"), the on-window half. `Core/Shared/Video/AspectRatioMath.h`
//answers "what ratio should the picture be drawn at"; this answers the question
//the ratio leaves open: given a panel of an arbitrary shape, how large is the
//picture inside it and how much of the panel is left over as letterbox
//(horizontal bands) or pillarbox (vertical bands).
//
//Stateful partner (ADR-0127): `UI/Windows/MainWindow.axaml.cs`, whose
//`RendererPanel_LayoutUpdated` owns the Avalonia layout pass, the panel bounds,
//`_rendererSize`, the DPI scale and the assignment to `_renderer`/the view
//model. Everything it used to compute inline lives here, so the fit can be
//asserted in `UI.Tests` without a window, a display or a native core.
//
//Host-free per ADR-0123: no Avalonia types (Avalonia's `Size` would drag the
//whole framework into the dual-compile), only doubles.
public readonly struct RendererViewport
{
	//Logical (DIP) size of the picture inside the panel - what the renderer
	//control is sized to.
	public double Width { get; init; }
	public double Height { get; init; }

	//Physical size handed to the core via EmuApi.SetRendererSize, i.e. the
	//logical size in device pixels, rounded.
	public uint RealWidth { get; init; }
	public uint RealHeight { get; init; }

	//What is left over on each axis, in logical units, split evenly between the
	//two bands the picture is centred in. Pillarbox = vertical bands on the
	//left/right; letterbox = horizontal bands on the top/bottom. Exactly one of
	//the two is non-zero for a picture that does not match the panel's shape.
	public double PillarboxWidth { get; init; }
	public double LetterboxHeight { get; init; }
}

public static class RendererViewportFit
{
	//`availableWidth/Height` is the space the picture may occupy (the renderer
	//panel's bounds, or the size the window forced on it in fullscreen);
	//`aspectRatio` is EmuApi.GetAspectRatio(); `dpiScale` is the layout scale;
	//`baseHeight` is EmuApi.GetBaseScreenSize().Height, used only by the
	//integer-scale rule; `forceIntegerScale` is
	//Config.Video.FullscreenForceIntegerScale AND a maximized/fullscreen window
	//- the caller resolves that conjunction, since window state is its business.
	public static RendererViewport Fit(double availableWidth, double availableHeight, double aspectRatio, double dpiScale, bool forceIntegerScale, double baseHeight)
	{
		if(!IsUsable(aspectRatio) || !IsUsable(dpiScale) || !IsUsable(availableWidth) || !IsUsable(availableHeight)) {
			//Degenerate inputs (an unknown aspect-ratio setting returns 0.0 from
			//AspectRatioMath, and the panel has no bounds before its first
			//layout pass). Fill what we were given rather than propagating a
			//NaN/Infinity into the control's Width/Height.
			return Fill(availableWidth, availableHeight, IsUsable(dpiScale) ? dpiScale : 1.0);
		}

		//Fit by height first, then fall back to fitting by width when that
		//would crop horizontally. Rounded comparison, so a sub-pixel excess
		//does not flip the axis the fit is driven by.
		double height = availableHeight;
		double width = availableHeight * aspectRatio;
		if(Math.Round(width) > Math.Round(availableWidth)) {
			width = availableWidth;
			height = width / aspectRatio;
		}

		if(forceIntegerScale && baseHeight > 0) {
			//Only ever shrinks: a fractional scale is floored to the next whole
			//one (never below 1), which is what makes every emulated pixel the
			//same size on screen. The picture keeps its aspect ratio, so the
			//floored height widens the letterbox rather than distorting it.
			double scale = height * dpiScale / baseHeight;
			if(scale != Math.Floor(scale)) {
				height = baseHeight * Math.Max(1, Math.Floor(scale / dpiScale));
				width = height * aspectRatio;
			}
		}

		return new RendererViewport {
			Width = width,
			Height = height,
			RealWidth = (uint)Math.Round(width * dpiScale),
			RealHeight = (uint)Math.Round(height * dpiScale),
			PillarboxWidth = Math.Max(0, (availableWidth - width) / 2),
			LetterboxHeight = Math.Max(0, (availableHeight - height) / 2)
		};
	}

	private static RendererViewport Fill(double width, double height, double dpiScale)
	{
		double safeWidth = IsUsable(width) ? width : 0;
		double safeHeight = IsUsable(height) ? height : 0;
		return new RendererViewport {
			Width = safeWidth,
			Height = safeHeight,
			RealWidth = (uint)Math.Round(safeWidth * dpiScale),
			RealHeight = (uint)Math.Round(safeHeight * dpiScale)
		};
	}

	private static bool IsUsable(double value) => value > 0 && !double.IsNaN(value) && !double.IsInfinity(value);
}

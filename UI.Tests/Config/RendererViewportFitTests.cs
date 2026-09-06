using System;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Config;

//P.7 "16:9 stretch", the half that was still listed as manual in
//docs/validation/manual-validation-automation-plan.md: the on-window letterbox
//fit and FullscreenForceIntegerScale, previously inline in
//MainWindow.RendererPanel_LayoutUpdated and therefore untestable. The
//aspect-ratio *math* is Core/Shared/Video/AspectRatioMath.h + core_unit_tests
//Bloco N; this is what the window does with that ratio.
public class RendererViewportFitTests
{
	private const double Nes4x3 = 4.0 / 3.0;
	private const double Wide = 16.0 / 9.0;

	private static RendererViewport Fit(double w, double h, double ratio, double dpi = 1.0, bool integer = false, double baseHeight = 240)
	{
		return RendererViewportFit.Fit(w, h, ratio, dpi, integer, baseHeight);
	}

	[Fact]
	public void A_panel_wider_than_the_picture_pillarboxes_it()
	{
		//1920x1080 panel, 4:3 picture: height is the binding axis, so the
		//picture is 1440 wide and 240 units of pillar are left on each side.
		RendererViewport viewport = Fit(1920, 1080, Nes4x3);
		Assert.Equal(1440, viewport.Width, 3);
		Assert.Equal(1080, viewport.Height, 3);
		Assert.Equal(240, viewport.PillarboxWidth, 3);
		Assert.Equal(0, viewport.LetterboxHeight, 3);
	}

	[Fact]
	public void A_panel_taller_than_the_picture_letterboxes_it()
	{
		//800x900 panel, 16:9 picture: fitting by height would need 1600px of
		//width, so the fit flips to the width axis and 450 rows are left over.
		RendererViewport viewport = Fit(800, 900, Wide);
		Assert.Equal(800, viewport.Width, 3);
		Assert.Equal(450, viewport.Height, 3);
		Assert.Equal(0, viewport.PillarboxWidth, 3);
		Assert.Equal(225, viewport.LetterboxHeight, 3);
	}

	[Fact]
	public void The_picture_never_exceeds_the_panel_on_either_axis()
	{
		//The property that letterboxing exists for: no crop, whatever the shape.
		double[] ratios = { Nes4x3, Wide, 1.0, 8.0 / 7.0, 2.35 };
		double[] widths = { 100, 640, 1366, 1920, 3840 };
		double[] heights = { 100, 480, 768, 1080, 2160 };
		foreach(double ratio in ratios) {
			foreach(double w in widths) {
				foreach(double h in heights) {
					RendererViewport viewport = Fit(w, h, ratio);
					Assert.True(viewport.Width <= w + 0.5, $"width {viewport.Width} > panel {w} (ratio {ratio})");
					Assert.True(viewport.Height <= h + 0.5, $"height {viewport.Height} > panel {h} (ratio {ratio})");
					//And it is a genuine fit, not an arbitrary shrink: the
					//picture touches the panel on its binding axis.
					Assert.True(Math.Abs(viewport.Width - w) < 0.5 || Math.Abs(viewport.Height - h) < 0.5,
						$"neither axis is bound: {viewport.Width}x{viewport.Height} in {w}x{h} (ratio {ratio})");
				}
			}
		}
	}

	[Fact]
	public void The_fit_keeps_the_aspect_ratio_it_was_given()
	{
		//The 16:9 check the plan called "the on-window letterbox fit": whatever
		//the window's shape, the picture drawn inside it is 16:9.
		foreach(double w in new double[] { 640, 1280, 1920, 700 }) {
			foreach(double h in new double[] { 480, 720, 1080, 1000 }) {
				RendererViewport viewport = Fit(w, h, Wide);
				Assert.Equal(Wide, viewport.Width / viewport.Height, 6);
			}
		}
	}

	[Fact]
	public void Force_integer_scale_floors_a_fractional_scale()
	{
		//1000 rows of panel over a 240-row picture is 4.16x - floored to 4x,
		//i.e. 960 rows, and the width follows so the ratio is preserved.
		RendererViewport viewport = Fit(1920, 1000, Nes4x3, integer: true, baseHeight: 240);
		Assert.Equal(960, viewport.Height, 3);
		Assert.Equal(1280, viewport.Width, 3);
		Assert.Equal(4.0, viewport.Height / 240, 6);
		//The rows the flooring gave up are letterbox, not crop.
		Assert.Equal(20, viewport.LetterboxHeight, 3);
	}

	[Fact]
	public void Force_integer_scale_leaves_an_exact_scale_alone()
	{
		//Already 4x: the rule must be a no-op, not a re-round.
		RendererViewport exact = Fit(1920, 960, Nes4x3, integer: true, baseHeight: 240);
		Assert.Equal(960, exact.Height, 3);
		Assert.Equal(Fit(1920, 960, Nes4x3).Width, exact.Width, 3);
	}

	[Fact]
	public void Force_integer_scale_never_goes_below_one()
	{
		//A panel shorter than one emulated screen would floor to 0 and blank
		//the renderer; the rule clamps to 1x and lets the picture overflow.
		RendererViewport viewport = Fit(400, 200, Nes4x3, integer: true, baseHeight: 240);
		Assert.Equal(240, viewport.Height, 3);
	}

	[Fact]
	public void Force_integer_scale_is_off_by_default()
	{
		//Same panel as the flooring case, without the flag: no flooring.
		RendererViewport viewport = Fit(1920, 1000, Nes4x3, integer: false, baseHeight: 240);
		Assert.Equal(1000, viewport.Height, 3);
	}

	[Fact]
	public void The_real_size_is_the_logical_size_in_device_pixels()
	{
		//What EmuApi.SetRendererSize is handed. At 2x DPI a 1440x1080 logical
		//picture is 2880x2160 physical pixels.
		RendererViewport viewport = Fit(1920, 1080, Nes4x3, dpi: 2.0);
		Assert.Equal(1440, viewport.Width, 3);
		Assert.Equal(2880u, viewport.RealWidth);
		Assert.Equal(2160u, viewport.RealHeight);
	}

	[Fact]
	public void Force_integer_scale_floors_in_device_pixels_at_high_dpi()
	{
		//At 2x DPI a 1000-unit panel is 2000 device rows over a 240-row
		//picture; the rule floors the scale it computes in device pixels and
		//the result stays a whole multiple of the emulated screen.
		RendererViewport viewport = Fit(1920, 1000, Nes4x3, dpi: 2.0, integer: true, baseHeight: 240);
		Assert.Equal(0, viewport.Height % 240, 6);
		Assert.True(viewport.Height <= 1000);
		Assert.Equal(0u, viewport.RealHeight % 240);
	}

	[Theory]
	[InlineData(0.0)]
	[InlineData(double.NaN)]
	[InlineData(double.PositiveInfinity)]
	[InlineData(-1.5)]
	public void A_degenerate_aspect_ratio_fills_instead_of_producing_NaN(double ratio)
	{
		//AspectRatioMath returns 0.0 for an unknown setting; a NaN width would
		//reach an Avalonia control's Width and silently mean "auto".
		RendererViewport viewport = Fit(1920, 1080, ratio);
		Assert.Equal(1920, viewport.Width, 3);
		Assert.Equal(1080, viewport.Height, 3);
		Assert.False(double.IsNaN(viewport.Width) || double.IsNaN(viewport.Height));
	}

	[Fact]
	public void A_panel_with_no_bounds_yet_produces_a_zero_viewport()
	{
		//Before the first layout pass the panel has no size; the fit must not
		//divide by it.
		RendererViewport viewport = Fit(0, 0, Nes4x3);
		Assert.Equal(0, viewport.Width, 3);
		Assert.Equal(0u, viewport.RealWidth);
	}
}

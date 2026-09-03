using System.Linq;
using System.Reflection;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Shapes;
using Avalonia.Headless.XUnit;
using Avalonia.Threading;
using Mesen.ViewModels;
using Mesen.Views;
using Xunit;

namespace Mesen.HeadlessTests;

//Slice I.3, plan subsection 2B: "the circularity ring in the Test tab"
//(Settings -> Input -> Test). The ring geometry and the circularity math live
//host-free in UI/Logic (GamepadCircularity, GamepadDriftDetector, covered in
//UI.Tests); this covers the markup in InputConfigView.axaml - that selecting the
//Test tab realizes one section per pad, that the deadzone ring and the live dot
//take their size/offset from the view-model, and that the circularity readout
//replaces its hint once a result exists.
//
//The pad itself is injected into GamepadTesterViewModel.Gamepads: the real
//source is InputApi.GetConnectedGamepadCount(), which needs both the native
//core and a physical pad, so an end-to-end "plug a pad in" check stays manual.
public class GamepadTestTabTests
{
	private static (Window Window, GamepadTestItem Pad) ShowTestTabWithOnePad()
	{
		InputConfigViewModel model = new();
		Window window = new() { Width = 800, Height = 600, Content = new InputConfigView() { DataContext = model } };
		window.Show();

		//Selecting the tab (two-way bound to IsTestTabVisible) is what realizes
		//its content and starts the ~16 ms poll.
		model.GamepadTester.IsTestTabVisible = true;
		Dispatcher.UIThread.RunJobs();

		//Freeze the poll: its Refresh() asks InputApi for the connected pad count
		//(0 on a machine with no pad) and trims the collection back to it, which
		//would delete the injected pad on the next dispatcher pass. Stopping the
		//timer is the only way to hold the tab still; leaving the tab selected is
		//what keeps its content realized.
		DispatcherTimer? poll = (DispatcherTimer?)typeof(GamepadTesterViewModel)
			.GetField("_pollTimer", BindingFlags.Instance | BindingFlags.NonPublic)!
			.GetValue(model.GamepadTester);
		Assert.NotNull(poll);
		poll.Stop();

		GamepadTestItem pad = new(0) {
			Name = "Test Pad",
			LeftStickDeadzoneSize = 24,
			LeftStickDotMargin = new Thickness(11, 5, 0, 0),
			LeftStickReadout = "x 0.30 y -0.10 | r 0.32"
		};
		model.GamepadTester.Gamepads.Add(pad);
		Dispatcher.UIThread.RunJobs();
		return (window, pad);
	}

	[AvaloniaFact]
	public void Deadzone_ring_and_dot_follow_the_view_model()
	{
		Assert.SkipWhen(!NativeCore.IsAvailable, NativeCore.SkipReason ?? "");

		(Window window, GamepadTestItem pad) = ShowTestTabWithOnePad();

		//Outer ring (full travel, no explicit size) + inner deadzone ring.
		Ellipse[] rings = window.FindAll<Ellipse>().ToArray();
		Assert.Equal(2, rings.Length);
		Assert.Equal(pad.LeftStickDeadzoneSize, rings[1].Width);
		Assert.Equal(pad.LeftStickDeadzoneSize, rings[1].Height);
		//The outer ring is the item's ring size, so the dot margin is in scale.
		Grid ring = Assert.IsType<Grid>(rings[0].Parent);
		Assert.Equal(pad.LeftStickRingSize, ring.Width);

		//The live dot: position comes from the margin the view-model computes.
		Border dot = ring.FindAll<Border>().Single(b => b.Width == pad.LeftStickDotSize);
		Assert.Equal(pad.LeftStickDotMargin, dot.Margin);

		Assert.Contains(window.FindAll<TextBlock>(), t => t.Text == pad.LeftStickReadout);
	}

	[AvaloniaFact]
	public void Circularity_result_replaces_its_hint_once_measured()
	{
		Assert.SkipWhen(!NativeCore.IsAvailable, NativeCore.SkipReason ?? "");

		(Window window, GamepadTestItem pad) = ShowTestTabWithOnePad();

		//Nothing measured yet: the hint is up, no result text.
		Assert.DoesNotContain(window.FindAll<TextBlock>(), t => t.Text == "Coverage 100% · radial 0.98");

		pad.CircularityText = "Coverage 100% · radial 0.98";
		pad.HasCircularityResult = true;
		Dispatcher.UIThread.RunJobs();

		TextBlock result = window.FindAll<TextBlock>().Single(t => t.Text == "Coverage 100% · radial 0.98");
		Assert.True(result.IsOnScreen());
	}
}

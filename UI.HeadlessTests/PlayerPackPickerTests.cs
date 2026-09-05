using System.Linq;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Threading;
using Mesen.Config;
using Mesen.Logic;
using Mesen.ViewModels;
using Mesen.Windows;
using Xunit;

namespace Mesen.HeadlessTests;

//P.5 / PRD Part B §5, plan subsection 2B: "pack picker keyboard navigation".
//`PlayerPackPicker.ShouldOpen`/`DistinctPackIdCount` and `PackPreferenceResolver`
//are covered host-free in UI.Tests; what is covered here is the XAML side - the
//ItemsControl realizes one focusable Button per choice, the first one is focused
//when the picker opens (MainWindow's IsPlayerPackPickerVisible handler), and
//focus moves between them from the keyboard alone (no pointer).
//
//#154 (filed from an earlier revision): the *arrow* keys did not move that
//focus - Avalonia's XY focus navigation is off for keyboard input unless a
//container opts in with `XYFocus.NavigationModes`, which MainWindow.axaml did
//not set, so ArrowDown left the focus on the first choice while Tab moved it.
//Fixed by adding XYFocus.NavigationModes="Enabled" to the PackPickerList
//ItemsControl; the arrows below are the regression test for that fix.
public class PlayerPackPickerTests
{
	//Container, Name, Version, Author, License, Sections, Enabled, Origin(0=folder),
	//PackId, ContentId - see MepPackListParser.
	private const string TwoPacks =
		"/packs/aaa\tAaa Pack\t1.0\t\t\ttextures\t1\t0\tissue-1\tc1\n" +
		"/packs/bbb\tBbb Pack\t1.0\t\t\ttextures\t1\t0\tissue-2\tc2\n";

	[AvaloniaFact]
	public void Keyboard_focus_moves_between_the_pack_choices()
	{
		Assert.SkipWhen(!NativeCore.IsAvailable, NativeCore.SkipReason ?? "");

		ConfigManager.Config.Preferences.UiMode = UiMode.Player;
		MainWindow window = new();
		window.Show();
		MainWindowViewModel model = Assert.IsType<MainWindowViewModel>(window.DataContext);

		Assert.True(model.EvaluatePlayerPackPicker(TwoPacks, "0000000000000000000000000000000000000000"));
		Dispatcher.UIThread.RunJobs();

		Border picker = window.FindNamed<Border>("PlayerPackPicker");
		Assert.True(picker.IsOnScreen());

		Button[] choices = window.FindNamed<ItemsControl>("PackPickerList").FindAll<Button>().ToArray();
		Assert.Equal(2, choices.Length);
		Assert.Equal("Aaa Pack", choices[0].FindAll<TextBlock>().First().Text);

		//Opening the picker focuses the first choice (posted, so RunJobs above
		//is what makes it happen) - no pointer needed.
		Assert.True(choices[0].IsFocused);

		window.KeyPressQwerty(PhysicalKey.ArrowDown, RawInputModifiers.None);
		Dispatcher.UIThread.RunJobs();
		Assert.True(choices[1].IsFocused);

		window.KeyPressQwerty(PhysicalKey.ArrowUp, RawInputModifiers.Shift);
		Dispatcher.UIThread.RunJobs();
		Assert.True(choices[0].IsFocused);
	}

	//ADR-0152: a row whose artifact carries reviewed known-missing declarations
	//says so in the picker, attributing the gap to MesenCE validation rather than
	//to the author. The row without an errata shows no such line at all - the
	//marker has to stay rare enough to mean something.
	[AvaloniaFact]
	public void A_known_missing_declaration_is_shown_on_its_own_row()
	{
		Assert.SkipWhen(!NativeCore.IsAvailable, NativeCore.SkipReason ?? "");

		ConfigManager.Config.Preferences.UiMode = UiMode.Player;
		MainWindow window = new();
		window.Show();
		MainWindowViewModel model = Assert.IsType<MainWindowViewModel>(window.DataContext);

		CommunityPackErrata errata = new() {
			DeclaredBy = "MesenCE validation",
			KnownMissing = new[] { new CommunityPackKnownMissing { Manifest = "hires.txt", Tag = "background", Target = "selectscreen.png" } }
		};
		model.PlayerPackChoices = new() {
			new PlayerPackChoice(new PackPreferenceResolver.Candidate { Container = "/packs/aaa", Name = "Aaa Pack", PackId = "issue-1", Enabled = true }, null, 0, errata),
			new PlayerPackChoice(new PackPreferenceResolver.Candidate { Container = "/packs/bbb", Name = "Bbb Pack", PackId = "issue-2", Enabled = true }, null)
		};
		model.IsPlayerPackPickerVisible = true;
		Dispatcher.UIThread.RunJobs();

		Button[] choices = window.FindNamed<ItemsControl>("PackPickerList").FindAll<Button>().ToArray();
		Assert.Equal(2, choices.Length);

		string[] declaredRow = choices[0].FindAll<TextBlock>().Where(t => t.IsVisible).Select(t => t.Text ?? "").ToArray();
		Assert.Contains(declaredRow, t => t == "1 known-missing asset — declared by MesenCE validation, not by the author");

		string[] cleanRow = choices[1].FindAll<TextBlock>().Where(t => t.IsVisible).Select(t => t.Text ?? "").ToArray();
		Assert.DoesNotContain(cleanRow, t => t.Contains("known-missing"));
	}
}

using System.IO;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Mesen.Config;
using Mesen.Logic;
using Mesen.ViewModels;
using Mesen.Windows;
using Xunit;

namespace Mesen.HeadlessTests;

//P.7 / PRD Part B §6.2, plan subsection 2B: "Welcome/Continue cards on screen".
//`PlayerEnhancementsToggle.ShouldShowWelcomeCard/ShouldShowContinueCard` are
//covered host-free in UI.Tests; this covers the step after them - that the two
//Borders in MainWindow.axaml's RecentGamesViewModel DataTemplate are in the
//realized visual tree, that their IsVisible follows those predicates, and that
//the Welcome card's single CTA is wired to the handler that dismisses it.
//
//These need a MainWindow, whose constructor calls EmuApi.InitDll() before the
//XAML is loaded, so they run only where the native core is built (NativeCore).
public class PlayerHomeCardsTests
{
	private static (MainWindow Window, MainWindowViewModel Model) ShowPlayerHome(bool welcomeDismissed, params string[] recentGames)
	{
		ConfigManager.Config.Preferences.UiMode = UiMode.Player;
		ConfigManager.Config.PlayerEnhancements.WelcomeCardDismissed = welcomeDismissed;

		string folder = ConfigManager.RecentGamesFolder;
		foreach(string stale in Directory.GetFiles(folder, "*.rgd")) {
			File.Delete(stale);
		}
		foreach(string game in recentGames) {
			File.WriteAllText(Path.Combine(folder, game + ".rgd"), "");
		}

		MainWindow window = new();
		window.Show();
		MainWindowViewModel model = Assert.IsType<MainWindowViewModel>(window.DataContext);
		//The same call MainWindow makes whenever it returns to the home screen.
		model.RecentGames.Init(GameScreenMode.RecentGames);
		Dispatcher.UIThread.RunJobs();
		return (window, model);
	}

	//The Welcome card must be genuinely on screen on a first boot. #153 (filed
	//from an earlier revision of this test) was that with an empty recents list
	//`RecentGamesViewModel.Init` ended with `Visible = false`, so the ContentControl
	//hosting this whole DataTemplate collapsed and took the card down with it -
	//the Welcome card never appeared for the very first-boot user it exists for.
	//Fixed by keeping the Player home host visible with zero entries; these are
	//on-screen assertions so a regression of that host visibility fails here.
	[AvaloniaFact]
	public void Welcome_card_is_shown_on_the_first_player_boot()
	{
		Assert.SkipWhen(!NativeCore.IsAvailable, NativeCore.SkipReason ?? "");

		(MainWindow window, _) = ShowPlayerHome(welcomeDismissed: false);

		Assert.True(window.FindNamed<Border>("PlayerWelcomeCard").IsOnScreen());
		Assert.False(window.FindNamed<Border>("PlayerContinueCard").IsVisible);
	}

	[AvaloniaFact]
	public void Welcome_card_is_hidden_once_it_was_dismissed()
	{
		Assert.SkipWhen(!NativeCore.IsAvailable, NativeCore.SkipReason ?? "");

		(MainWindow window, _) = ShowPlayerHome(welcomeDismissed: true);

		Assert.False(window.FindNamed<Border>("PlayerWelcomeCard").IsVisible);
	}

	[AvaloniaFact]
	public void Continue_card_is_on_screen_once_a_game_was_played()
	{
		Assert.SkipWhen(!NativeCore.IsAvailable, NativeCore.SkipReason ?? "");

		(MainWindow window, _) = ShowPlayerHome(welcomeDismissed: true, "Zelda");

		Assert.False(window.FindNamed<Border>("PlayerWelcomeCard").IsOnScreen());
		Border continueCard = window.FindNamed<Border>("PlayerContinueCard");
		Assert.True(continueCard.IsOnScreen());
		//The label is bound, not hardcoded: it names the most recent game.
		Button resume = continueCard.FindAll<Button>().Single();
		Assert.Contains("Zelda", resume.Content?.ToString() ?? "");
	}

	//The CTA's Click="OnWelcomeCardLoadRom" wiring. The click is raised on the
	//button rather than clicked with the headless pointer; the CTA is also the
	//card's own dismissal, so this exercises the whole "shown once" contract.
	[AvaloniaFact]
	public void Welcome_cta_dismisses_the_card_for_good()
	{
		Assert.SkipWhen(!NativeCore.IsAvailable, NativeCore.SkipReason ?? "");

		(MainWindow window, MainWindowViewModel model) = ShowPlayerHome(welcomeDismissed: false);
		Button cta = window.FindNamed<Border>("PlayerWelcomeCard").FindAll<Button>().Single();

		cta.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
		Dispatcher.UIThread.RunJobs();

		Assert.True(ConfigManager.Config.PlayerEnhancements.WelcomeCardDismissed);
		//...and the card is gone on the next visit to the home screen.
		model.RecentGames.Init(GameScreenMode.RecentGames);
		Dispatcher.UIThread.RunJobs();
		Assert.False(window.FindNamed<Border>("PlayerWelcomeCard").IsVisible);
	}
}

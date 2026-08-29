using Avalonia;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using Mesen.Config;
using Mesen.Controls;
using Mesen.Interop;
using Mesen.Localization;
using Mesen.Logic;
using Mesen.Utilities;
using Mesen.Windows;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Mesen.ViewModels
{
	public partial class MainWindowViewModel : DisposableViewModel
	{
		public static MainWindowViewModel Instance { get; private set; } = null!;

		[ObservableProperty] public partial MainMenuViewModel MainMenu { get; set; }
		[ObservableProperty] public partial RomInfo RomInfo { get; set; }
		[ObservableProperty] public partial AudioPlayerViewModel? AudioPlayer { get; private set; }
		[ObservableProperty] public partial RecentGamesViewModel RecentGames { get; private set; }

		[ObservableProperty] public partial string WindowTitle { get; private set; } = "MesenCE";
		[ObservableProperty] public partial Size RendererSize { get; set; }

		[ObservableProperty] public partial bool IsMenuVisible { get; set; }

		//P.4 (PRD-player-shell §6): the thin Player-mode overlay panel (Resume,
		//Save/Load slot, Pack, Settings, Advanced GUI, Quit), shown on top of the
		//game while UiMode == Player. Opening it pauses the game so the couch
		//user can navigate; closing never auto-resumes - Resume is an overlay item.
		[ObservableProperty] public partial bool IsPlayerOverlayVisible { get; set; }

		[ObservableProperty] public partial bool IsNativeRendererVisible { get; private set; }
		[ObservableProperty] public partial bool IsSoftwareRendererVisible { get; private set; }

		public SoftwareRendererViewModel SoftwareRenderer { get; } = new();

		public Configuration Config { get; }
		public NativeRenderer? Renderer { get; internal set; }

		public MainWindowViewModel()
		{
			Instance = this;

			Config = ConfigManager.Config;
			MainMenu = new MainMenuViewModel(this);
			RomInfo = new RomInfo();
			RecentGames = new RecentGamesViewModel();

			UpdateMenuVisibility();
		}

		//P.4 (PRD-player-shell §6): Player hides the menu bar entirely (AutoHideMenu
		//is ignored in Player - there is no menu bar); Advanced keeps the classic
		//AutoHideMenu rule. Re-evaluated whenever UiMode changes (the Advanced GUI
		//overlay item / the Preferences combo flip it, instant and persisted).
		private void UpdateMenuVisibility()
		{
			IsMenuVisible = Config.Preferences.UiMode != UiMode.Player && !Config.Preferences.AutoHideMenu;
		}

		//P.4 (PRD-player-shell §6): the overlay shortcut toggles the thin Player
		//overlay. Opening pauses the game (so the couch user can navigate with
		//D-pad/A/B); closing never auto-resumes - Resume is an overlay item. The
		//overlay only exists in Player mode; in Advanced the press is ignored
		//(ShortcutHandler checks the mode before acting).
		public void TogglePlayerOverlay()
		{
			if(IsPlayerOverlayVisible) {
				IsPlayerOverlayVisible = false;
			} else {
				IsPlayerOverlayVisible = true;
				EmuApi.Pause();
			}
		}

		//P.4: "Advanced GUI" overlay item - switches to Advanced mode, instant and
		//persisted. The chrome re-applies via the UiMode observer (menu bar back,
		//overlay hidden).
		public void SwitchToAdvancedMode()
		{
			Config.Preferences.UiMode = UiMode.Advanced;
			Config.ApplyConfig();
			Config.Save();
		}

		public void Init(MainWindow wnd)
		{
			MainMenu.Initialize(wnd);
			RecentGames.Init(GameScreenMode.RecentGames);

			AddDisposable(RecentGames.ObserveProp(nameof(RecentGamesViewModel.Visible), () => {
				UpdateRendererVisibility();
			}));

			AddDisposable(SoftwareRenderer.ObserveProp(nameof(SoftwareRendererViewModel.FrameSurface), () => {
				UpdateRendererVisibility();
			}));

			AddDisposable(this.ObserveProp(nameof(MainWindowViewModel.RendererSize), UpdateWindowTitle));

			AddDisposable(ReactiveHelper.RegisterForeignObserver([(() => Config, nameof(Configuration.Video)), (() => Config.Video, nameof(VideoConfig.AspectRatio))], UpdateWindowTitle));
			AddDisposable(ReactiveHelper.RegisterForeignObserver([(() => Config, nameof(Configuration.Video)), (() => Config.Video, nameof(VideoConfig.VideoFilter))], UpdateWindowTitle));
			AddDisposable(ReactiveHelper.RegisterForeignObserver([(() => Config, nameof(Configuration.Preferences)), (() => Config.Preferences, nameof(PreferencesConfig.ShowTitleBarInfo))], UpdateWindowTitle));
			//P.4: UiMode switches (overlay "Advanced GUI" item or the Preferences
			//combo) re-evaluate the chrome immediately - menu bar on/off, and the
			//overlay hides when leaving Player.
			AddDisposable(ReactiveHelper.RegisterForeignObserver([(() => Config.Preferences, nameof(PreferencesConfig.UiMode))], () => {
				UpdateMenuVisibility();
				if(Config.Preferences.UiMode != UiMode.Player) {
					IsPlayerOverlayVisible = false;
				}
			}));

			UpdateWindowTitle();
		}

		private void UpdateRendererVisibility()
		{
			IsNativeRendererVisible = !RecentGames.Visible && SoftwareRenderer.FrameSurface == null;
			IsSoftwareRendererVisible = !RecentGames.Visible && SoftwareRenderer.FrameSurface != null;

			if(Renderer != null) {
				Dispatcher.UIThread.Post(() => {
					Renderer.IsVisible = IsNativeRendererVisible;
				});
			}
		}

		partial void OnRomInfoChanged(RomInfo value)
		{
			bool showAudioPlayer = RomInfo.Format == RomFormat.Nsf || RomInfo.Format == RomFormat.Spc || RomInfo.Format == RomFormat.Gbs || RomInfo.Format == RomFormat.PceHes;
			AudioPlayer?.Dispose();
			if(AudioPlayer == null && showAudioPlayer) {
				AudioPlayer = new AudioPlayerViewModel();
			} else if(!showAudioPlayer) {
				AudioPlayer = null;
			}

			UpdateWindowTitle();
		}

		private void UpdateWindowTitle()
		{
			string title = "MesenCE";
			string romName = RomInfo.GetRomName();
			if(!string.IsNullOrWhiteSpace(romName)) {
				title += " - " + romName;
				if(ConfigManager.Config.Preferences.ShowTitleBarInfo) {
					FrameInfo baseSize = EmuApi.GetBaseScreenSize();
					double scale = (double)RendererSize.Height / baseSize.Height;
					title += string.Format(" - {0}x{1} ({2:0.###}x, {3})",
						Math.Round(RendererSize.Width),
						Math.Round(RendererSize.Height),
						scale,
						ResourceHelper.GetEnumText(ConfigManager.Config.Video.VideoFilter));
				}
			}
			WindowTitle = title;
		}
	}
}

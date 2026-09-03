using CommunityToolkit.Mvvm.ComponentModel;
using Mesen.Config;
using Mesen.Interop;
using Mesen.Localization;
using Mesen.Logic;
using Mesen.Utilities;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Mesen.ViewModels
{
	public partial class RecentGamesViewModel : ViewModelBase
	{
		[ObservableProperty] public partial bool Visible { get; set; }
		[ObservableProperty] public partial bool NeedResume { get; private set; }
		[ObservableProperty] public partial string Title { get; private set; } = "";
		[ObservableProperty] public partial GameScreenMode Mode { get; private set; }
		[ObservableProperty] public partial List<RecentGameInfo> GameEntries { get; private set; } = new List<RecentGameInfo>();

		//P.7 (PRD Part B §6.2): Welcome/Continue cards, Player-home only (never
		//shown on the Advanced game-selection screen, nor on the Save/Load
		//state screens that reuse this same ViewModel/DataTemplate - both are
		//gated on Mode == RecentGames below). Welcome is not gated on having
		//any entries - recents are necessarily empty the first time it shows.
		[ObservableProperty] public partial bool ShowWelcomeCard { get; private set; }
		[ObservableProperty] public partial bool ShowContinueCard { get; private set; }
		[ObservableProperty] public partial string ContinueLabel { get; private set; } = "";

		public RecentGamesViewModel()
		{
			//P.4 (PRD Part B §6): in Player mode the recent-games grid is the
			//home screen and is always shown when no ROM runs - GameSelectionScreenMode
			//keeps its current meaning (ResumeState/PowerOn/Disabled) only in Advanced.
			Visible = ConfigManager.Config.Preferences.UiMode == UiMode.Player || ConfigManager.Config.Preferences.GameSelectionScreenMode != GameSelectionMode.Disabled;
		}

		public void Init(GameScreenMode mode)
		{
			if(mode == GameScreenMode.RecentGames && ConfigManager.Config.Preferences.UiMode != UiMode.Player && ConfigManager.Config.Preferences.GameSelectionScreenMode == GameSelectionMode.Disabled) {
				Visible = false;
				GameEntries = new List<RecentGameInfo>();
				ShowWelcomeCard = false;
				ShowContinueCard = false;
				return;
			} else if(mode != GameScreenMode.RecentGames && Mode == mode && Visible) {
				Visible = false;
				if(NeedResume) {
					EmuApi.Resume();
				}
				return;
			}

			if(Mode == mode && Visible && GameEntries.Count > 0) {
				//Prevent flickering when closing the config window while no game is running
				//No need to update anything if the game selection screen is already visible
				return;
			}

			Mode = mode;

			List<RecentGameInfo> entries = new();

			//#153: the two Player-home cards live in the same DataTemplate as the
			//recent-games grid and share its host ContentControl's IsVisible. On a
			//genuine first boot the recents list is empty and `Visible = entries.Count > 0`
			//below was collapsing the whole template - taking the Welcome card down
			//with it, for exactly the user it exists for. The Player home (constructor:
			//"the grid is always shown when no ROM runs") must stay up with zero entries
			//so the cards render above an empty grid; Save/Load/game-selection keep the
			//old empty->hidden behaviour.
			bool keepPlayerHomeHostVisible = false;

			if(mode == GameScreenMode.RecentGames) {
				NeedResume = false;
				Title = string.Empty;

				List<string> files = Directory.GetFiles(ConfigManager.RecentGamesFolder, "*.rgd").OrderByDescending((file) => new FileInfo(file).LastWriteTime).ToList();
				for(int i = 0; i < files.Count && entries.Count < 72; i++) {
					entries.Add(new RecentGameInfo() { FileName = files[i], Name = Path.GetFileNameWithoutExtension(files[i]) });
				}

				//P.7 (§6.2): Player-home only - Advanced's own game-selection
				//screen (GameSelectionScreenMode) reuses this same ViewModel/mode
				//but is not the "Player home" these cards belong to.
				bool isPlayerHome = ConfigManager.Config.Preferences.UiMode == UiMode.Player;
				keepPlayerHomeHostVisible = isPlayerHome;
				ShowWelcomeCard = isPlayerHome && PlayerEnhancementsToggle.ShouldShowWelcomeCard(ConfigManager.Config.PlayerEnhancements.WelcomeCardDismissed);
				ShowContinueCard = isPlayerHome && PlayerEnhancementsToggle.ShouldShowContinueCard(entries.Count > 0);
				ContinueLabel = entries.Count > 0 ? ResourceHelper.GetMessage("ContinueCardLabel", entries[0].Name) : "";
			} else {
				ShowWelcomeCard = false;
				ShowContinueCard = false;
				if(!Visible) {
					NeedResume = Pause();
				}

				Title = mode == GameScreenMode.LoadState ? ResourceHelper.GetMessage("LoadStateDialog") : ResourceHelper.GetMessage("SaveStateDialog");

				string romName = EmuApi.GetRomInfo().GetRomName();
				for(int i = 0; i < (mode == GameScreenMode.LoadState ? 11 : 10); i++) {
					entries.Add(new RecentGameInfo() {
						FileName = Path.Combine(ConfigManager.SaveStateFolder, romName + "_" + (i + 1) + "." + FileDialogHelper.MesenSaveStateExt),
						StateIndex = i + 1,
						Name = i == 10 ? ResourceHelper.GetMessage("AutoSave") : ResourceHelper.GetMessage("SlotNumber", i + 1),
						SaveMode = mode == GameScreenMode.SaveState
					});
				}
				if(mode == GameScreenMode.LoadState) {
					entries.Add(new RecentGameInfo() {
						FileName = Path.Combine(ConfigManager.RecentGamesFolder, romName + ".rgd"),
						Name = ResourceHelper.GetMessage("LastSession")
					});
				}
			}

			Visible = keepPlayerHomeHostVisible || entries.Count > 0;
			GameEntries = entries;
		}

		private bool Pause()
		{
			if(!EmuApi.IsPaused()) {
				EmuApi.Pause();
				return true;
			}
			return false;
		}
	}

	public enum GameScreenMode
	{
		RecentGames,
		LoadState,
		SaveState
	}

	public class RecentGameInfo
	{
		public string FileName { get; set; } = "";
		public int StateIndex { get; set; } = -1;
		public string Name { get; set; } = "";
		public bool SaveMode { get; set; } = false;

		public bool IsEnabled()
		{
			return SaveMode || File.Exists(FileName);
		}

		public void Load()
		{
			if(StateIndex > 0) {
				Task.Run(() => {
					//Run in another thread to prevent deadlocks etc. when emulator notifications are processed UI-side
					if(SaveMode) {
						EmuApi.SaveState((uint)StateIndex);
					} else {
						EmuApi.LoadState((uint)StateIndex);
					}
					EmuApi.Resume();
				});
			} else {
				LoadRomHelper.LoadRecentGame(FileName, false);
				EmuApi.Resume();
			}
		}
	}
}

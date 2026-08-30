using Avalonia;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using Mesen.Config;
using Mesen.Controls;
using Mesen.Interop;
using Mesen.Localization;
using Mesen.Logic;
using Mesen.Services;
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

		//P.4 (PRD Part B §6): the thin Player-mode overlay panel (Resume,
		//Save/Load slot, Pack, Settings, Advanced GUI, Quit), shown on top of the
		//game while UiMode == Player. Opening it pauses the game so the couch
		//user can navigate; closing never auto-resumes - Resume is an overlay item.
		[ObservableProperty] public partial bool IsPlayerOverlayVisible { get; set; }

		//P.5 (PRD Part B §5): the Player-mode pack picker. Opens once over
		//the un-enhanced game when 2+ competing pack_ids exist and no effective
		//per-ROM preference is stored; picking stores the choice (P.3) and power
		//cycles to apply it; dismissing stores nothing, so the next launch asks
		//again. A sibling-folder pack always suppresses it (§4).
		[ObservableProperty] public partial bool IsPlayerPackPickerVisible { get; set; }
		[ObservableProperty] public partial List<PlayerPackChoice> PlayerPackChoices { get; set; } = new();

		//P.5 (PRD Part B §6): the currently-applied pack's name/layers for
		//the overlay chip and the "Applied ..." toast.
		[ObservableProperty] public partial string CurrentPackName { get; private set; } = "";
		[ObservableProperty] public partial string CurrentPackLayers { get; private set; } = "";

		[ObservableProperty] public partial bool IsNativeRendererVisible { get; private set; }
		[ObservableProperty] public partial bool IsSoftwareRendererVisible { get; private set; }

		public SoftwareRendererViewModel SoftwareRenderer { get; } = new();

		public Configuration Config { get; }
		public NativeRenderer? Renderer { get; internal set; }

		//P.5: the ROM sha1 the current picker evaluation ran against (the key of
		//the stored per-ROM preference, §4 step 1 - before any patches[] apply).
		private string _pickerRomSha1 = "";

		public MainWindowViewModel()
		{
			Instance = this;

			Config = ConfigManager.Config;
			MainMenu = new MainMenuViewModel(this);
			RomInfo = new RomInfo();
			RecentGames = new RecentGamesViewModel();

			UpdateMenuVisibility();
		}

		//P.4 (PRD Part B §6): Player hides the menu bar entirely (AutoHideMenu
		//is ignored in Player - there is no menu bar); Advanced keeps the classic
		//AutoHideMenu rule. Re-evaluated whenever UiMode changes (the Advanced GUI
		//overlay item / the Preferences combo flip it, instant and persisted).
		private void UpdateMenuVisibility()
		{
			IsMenuVisible = Config.Preferences.UiMode != UiMode.Player && !Config.Preferences.AutoHideMenu;
		}

		//P.4 (PRD Part B §6): the overlay shortcut toggles the thin Player
		//overlay. Opening pauses the game (so the couch user can navigate with
		//D-pad/A/B); closing never auto-resumes - Resume is an overlay item. The
		//overlay only exists in Player mode; in Advanced the press is ignored
		//(ShortcutHandler checks the mode before acting).
		public void TogglePlayerOverlay()
		{
			//P.5: while the pack picker is up, Esc dismisses it (un-enhanced this
			//session) instead of toggling the overlay.
			if(IsPlayerPackPickerVisible) {
				IsPlayerPackPickerVisible = false;
				return;
			}
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

		//P.5 (PRD Part B §5): decides whether the Player picker opens for
		//the loaded ROM and, when it does, fills the competing choices. Data is
		//injected (pack list + ROM sha1 from the code-behind) so the decision
		//stays host-free: MepPackListParser -> PackPreferenceResolver (content_id
		//merge + preference) -> PlayerPackPicker.ShouldOpen. Returns true when
		//the picker is showing. Also refreshes the current-pack chip/toast data.
		public bool EvaluatePlayerPackPicker(string packListText, string romSha1)
		{
			_pickerRomSha1 = romSha1;

			if(Config.Preferences.UiMode != UiMode.Player) {
				IsPlayerPackPickerVisible = false;
				return false;
			}

			BuildPackPickerData(packListText, romSha1, out PackPreferenceResolver.Resolution resolution, out bool hasSibling);
			UpdateCurrentPack(resolution);

			bool open = PlayerPackPicker.ShouldOpen(hasSibling, PlayerPackPicker.DistinctPackIdCount(resolution.Candidates), resolution.PreferredContainer != null);
			if(open) {
				IsPlayerPackPickerVisible = true;
			} else {
				IsPlayerPackPickerVisible = false;
			}
			return open;
		}

		//P.5 §5: the overlay chip click ("changing the choice later") - always
		//offers to change the current pick, so it opens the picker whenever 2+
		//distinct pack_ids exist, even with a stored preference. Returns true
		//when the picker is showing.
		public bool OpenPlayerPackPickerForChange(string packListText, string romSha1)
		{
			_pickerRomSha1 = romSha1;

			if(Config.Preferences.UiMode != UiMode.Player) {
				return false;
			}

			BuildPackPickerData(packListText, romSha1, out PackPreferenceResolver.Resolution resolution, out bool hasSibling);
			UpdateCurrentPack(resolution);

			int distinct = PlayerPackPicker.DistinctPackIdCount(resolution.Candidates);
			if(hasSibling || distinct < 2) {
				return false;
			}
			IsPlayerPackPickerVisible = true;
			return true;
		}

		//Shared: parse the pack list, run the §5 content_id merge + preference,
		//and refresh the picker choices. Sibling detection comes from the parser
		//(origin column 2).
		private void BuildPackPickerData(string packListText, string romSha1, out PackPreferenceResolver.Resolution resolution, out bool hasSibling)
		{
			MepPackListResult parsed = MepPackListParser.Parse(packListText);
			List<PackPreferenceResolver.Candidate> candidates = parsed.Packs.Select(e => new PackPreferenceResolver.Candidate {
				Container = e.Container,
				Name = e.Name,
				PackId = e.PackId,
				ContentId = e.ContentId,
				Version = e.Version,
				Enabled = e.Enabled
			}).ToList();

			Dictionary<string, MepPackListEntry> entriesByContainer = new(StringComparer.OrdinalIgnoreCase);
			foreach(MepPackListEntry e in parsed.Packs) {
				entriesByContainer[e.Container] = e;
			}

			resolution = PackPreferenceResolver.Resolve(candidates, Config.EnhancementPacks.GetRomPackPreference(romSha1));
			hasSibling = parsed.Packs.Any(e => e.Source == "sibling");

			//P.6 §5: the picker sorts by community 👍 (catalog MEI votes) first,
			//then by name - local-only packs (votes 0) fall back to name order.
			PlayerPackChoices = resolution.Candidates
				.Select(c => new PlayerPackChoice(c, entriesByContainer.TryGetValue(c.Container, out MepPackListEntry? entry) ? entry : null,
					CommunityPackInstallService.GetVotes(PackPreferenceResolver.DerivePackId(c))))
				.OrderByDescending(c => c.Votes)
				.ThenBy(c => c.Name, StringComparer.OrdinalIgnoreCase)
				.ToList();
		}

		//The current pack (chip/toast): the preferred container, else the
		//lexicographic default (the first content-merged candidate).
		private void UpdateCurrentPack(PackPreferenceResolver.Resolution resolution)
		{
			CurrentPackName = "";
			CurrentPackLayers = "";

			PlayerPackChoice? current = null;
			if(resolution.PreferredContainer != null) {
				current = PlayerPackChoices.FirstOrDefault(c => c.Container == resolution.PreferredContainer);
			} else if(PlayerPackChoices.Count > 0) {
				current = PlayerPackChoices[0];
			}
			if(current != null) {
				CurrentPackName = current.Name;
				CurrentPackLayers = current.Layers;
			}
		}

		//P.5: the picker's "Apply" - stores the per-ROM-sha1 choice (P.3) and
		//power-cycles so the chosen pack applies on the reload. The next load
		//sees the stored preference and never re-opens the picker (silent).
		public void PickPlayerPack(string container)
		{
			PlayerPackChoice? choice = PlayerPackChoices.FirstOrDefault(c => c.Container.Equals(container, StringComparison.OrdinalIgnoreCase));
			if(choice == null || string.IsNullOrEmpty(_pickerRomSha1)) {
				return;
			}

			Config.EnhancementPacks.SetRomPackPreference(_pickerRomSha1, choice.PackId);
			Config.ApplyConfig();
			Config.Save();
			IsPlayerPackPickerVisible = false;
			LoadRomHelper.PowerCycle();
		}

		//P.5: dismissing stores nothing - the game keeps playing un-enhanced this
		//session and, with no preference on disk, the picker asks again next launch.
		public void DismissPlayerPackPicker()
		{
			IsPlayerPackPickerVisible = false;
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

	//P.5 (PRD Part B §5): one row of the Player pack picker - a
	//content-merged competing pack. Name/author/version/license/layers come
	//from the core's GetPackListText columns; PackId is the effective pack_id
	//(ADR-0140 id, else the local:<container> rule-4 fallback) that P.3 stores.
	public sealed class PlayerPackChoice
	{
		public string Container { get; }
		public string PackId { get; }
		public string Name { get; }
		public string Author { get; }
		public string Version { get; }
		public string License { get; }
		public string Layers { get; }
		//P.6 §5: community 👍 count (catalog MEI `votes`); 0 for local-only packs,
		//which sort by name. Not a download ranking - it only orders the picker.
		public int Votes { get; }
		//One-line metadata row for the picker: "v1.0 · Author · textures, audio · MIT"
		public string Detail { get; }

		public PlayerPackChoice(PackPreferenceResolver.Candidate candidate, MepPackListEntry? entry, int votes = 0)
		{
			Container = candidate.Container;
			PackId = PackPreferenceResolver.DerivePackId(candidate);
			Name = candidate.Name;
			Version = candidate.Version;
			Author = entry?.Author ?? "";
			License = entry?.License ?? "";
			Layers = string.IsNullOrEmpty(entry?.Sections) ? "" : entry.Sections.Replace(",", ", ");
			Votes = Math.Max(0, votes);

			List<string> detail = new();
			if(!string.IsNullOrEmpty(Version)) {
				detail.Add("v" + Version);
			}
			if(!string.IsNullOrEmpty(Author)) {
				detail.Add(Author);
			}
			if(!string.IsNullOrEmpty(Layers)) {
				detail.Add(Layers);
			}
			if(!string.IsNullOrEmpty(License)) {
				detail.Add(License);
			}
			Detail = string.Join(" · ", detail);
		}

		public override string ToString() => Name;
	}
}

using CommunityToolkit.Mvvm.ComponentModel;
using HarfBuzzSharp;
using Mesen.Config;
using Mesen.Logic;
using Mesen.Utilities;
using System;

namespace Mesen.ViewModels
{
	public partial class ConfigViewModel : DisposableViewModel
	{
		[ObservableProperty] public partial AudioConfigViewModel? Audio { get; set; }
		[ObservableProperty] public partial InputConfigViewModel? Input { get; set; }
		[ObservableProperty] public partial VideoConfigViewModel? Video { get; set; }
		[ObservableProperty] public partial PreferencesConfigViewModel? Preferences { get; set; }
		[ObservableProperty] public partial EmulationConfigViewModel? Emulation { get; set; }

		[ObservableProperty] public partial NesConfigViewModel? Nes { get; set; }
		[ObservableProperty] public partial GameboyConfigViewModel? Gameboy { get; set; }
		[ObservableProperty] public partial GbaConfigViewModel? Gba { get; set; }
		[ObservableProperty] public partial SmsConfigViewModel? Sms { get; set; }

		[ObservableProperty] public partial ConfigWindowTab SelectedIndex { get; set; }
		//PRD Part B §6: Player mode's Settings page shows only the
		//essentials tabs (video / audio / input); the window hides the rest.
		[ObservableProperty] public partial bool PlayerMode { get; set; }
		public bool AlwaysOnTop { get; }

		[Obsolete("For designer only")]
		public ConfigViewModel() : this(ConfigWindowTab.Audio) { }

		public ConfigViewModel(ConfigWindowTab selectedTab) : this(selectedTab, playerMode: false) { }

		public ConfigViewModel(ConfigWindowTab selectedTab, bool playerMode = false)
		{
			AlwaysOnTop = ConfigManager.Config.Preferences.AlwaysOnTop;
			PlayerMode = playerMode;
			//§6: Player starts on one of the essentials tabs; a non-essentials
			//selection (e.g. Preferences from the Advanced GUI) clamps to Audio.
			SelectTab(playerMode ? PlayerSettingsEssentials.ClampToEssentials(selectedTab) : selectedTab);
		}

		partial void OnSelectedIndexChanged(ConfigWindowTab value)
		{
			SelectTab(value);
		}

		public void SelectTab(ConfigWindowTab tab)
		{
			//Create each view model when the corresponding tab is clicked, for performance
			switch(tab) {
				case ConfigWindowTab.Audio: Audio ??= AddDisposable(new AudioConfigViewModel()); break;
				case ConfigWindowTab.Emulation: Emulation ??= AddDisposable(new EmulationConfigViewModel()); break;
				case ConfigWindowTab.Input: Input ??= AddDisposable(new InputConfigViewModel()); break;
				case ConfigWindowTab.Video: Video ??= AddDisposable(new VideoConfigViewModel()); break;

				case ConfigWindowTab.Nes:
					//TODOv2 fix this patch
					Preferences ??= AddDisposable(new PreferencesConfigViewModel());
					Nes ??= AddDisposable(new NesConfigViewModel(Preferences.Config));
					break;

				case ConfigWindowTab.Gameboy: Gameboy ??= AddDisposable(new GameboyConfigViewModel()); break;
				case ConfigWindowTab.Gba: Gba ??= AddDisposable(new GbaConfigViewModel()); break;
				case ConfigWindowTab.Sms: Sms ??= AddDisposable(new SmsConfigViewModel()); break;

				case ConfigWindowTab.Preferences: Preferences ??= AddDisposable(new PreferencesConfigViewModel()); break;
			}

			SelectedIndex = tab;
		}

		public void SaveConfig()
		{
			ConfigManager.Config.ApplyConfig();
			ConfigManager.Config.Save();
			ConfigManager.Config.Preferences.UpdateFileAssociations();
		}

		public void RevertConfig()
		{
			ConfigManager.Config.Audio = Audio?.OriginalConfig ?? ConfigManager.Config.Audio;
			ConfigManager.Config.Input = Input?.OriginalConfig ?? ConfigManager.Config.Input;
			ConfigManager.Config.Video = Video?.OriginalConfig ?? ConfigManager.Config.Video;
			ConfigManager.Config.Preferences = Preferences?.OriginalConfig ?? ConfigManager.Config.Preferences;
			ConfigManager.Config.Emulation = Emulation?.OriginalConfig ?? ConfigManager.Config.Emulation;
			ConfigManager.Config.Nes = Nes?.OriginalConfig ?? ConfigManager.Config.Nes;
			ConfigManager.Config.Gameboy = Gameboy?.OriginalConfig ?? ConfigManager.Config.Gameboy;
			ConfigManager.Config.Gba = Gba?.OriginalConfig ?? ConfigManager.Config.Gba;
			ConfigManager.Config.Sms = Sms?.OriginalConfig ?? ConfigManager.Config.Sms;
			ConfigManager.Config.ApplyConfig();
			ConfigManager.Config.Save();
		}

		public bool IsDirty()
		{
			return (
				Audio?.OriginalConfig.IsIdentical(ConfigManager.Config.Audio) == false ||
				Input?.OriginalConfig.IsIdentical(ConfigManager.Config.Input) == false ||
				Video?.OriginalConfig.IsIdentical(ConfigManager.Config.Video) == false ||
				Preferences?.OriginalConfig.IsIdentical(ConfigManager.Config.Preferences) == false ||
				Emulation?.OriginalConfig.IsIdentical(ConfigManager.Config.Emulation) == false ||
				Nes?.OriginalConfig.IsIdentical(ConfigManager.Config.Nes) == false ||
				Gameboy?.OriginalConfig.IsIdentical(ConfigManager.Config.Gameboy) == false ||
				Gba?.OriginalConfig.IsIdentical(ConfigManager.Config.Gba) == false ||
				Sms?.OriginalConfig.IsIdentical(ConfigManager.Config.Sms) == false
			);
		}
	}
}

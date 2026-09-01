using CommunityToolkit.Mvvm.ComponentModel;
using Mesen.Interop;
using Mesen.Logic;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Mesen.Config;

//MEP enhancement packs (F3 - docs/specs/MEP-v1.md): global switch, one toggle
//per section and the list of packs the user disabled by container name.
//Everything applies on the next ROM load / power cycle (like EnableHdPacks).
public partial class EnhancementPackConfig : BaseConfig<EnhancementPackConfig>
{
	[ObservableProperty] public partial bool EnableMepPacks { get; set; } = true;
	[ObservableProperty] public partial bool EnableTextures { get; set; } = true;
	[ObservableProperty] public partial bool EnableAudio { get; set; } = true;
	[ObservableProperty] public partial bool EnableSynth { get; set; } = true;
	[ObservableProperty] public partial bool EnablePatches { get; set; } = true;
	[ObservableProperty] public partial bool ApplyPatchOnHashMismatch { get; set; } = false;
	[ObservableProperty] public partial bool BootstrapEnhancementFolder { get; set; } = true;
	//ADR-0138 (F6.4): auto-install a matching community pack found via the
	//MEP recipe catalog. No UI toggle yet - that's F6.4b's job; this just
	//keeps the by-value marshaled struct in sync with the native side.
	[ObservableProperty] public partial bool AutoInstallCommunityPacks { get; set; } = true;
	//ADR-0146: the former first-run consent flag (CommunityPackAutoInstallConsentGiven)
	//was removed; AutoInstallCommunityPacks is the single master switch.

	//Container names (folder / zip base name) of packs the user turned off
	public List<string> DisabledPacks { get; set; } = new();

	//P.3 (PRD Part B §5): per-ROM-sha1 preferred pack_id (ADR-0140 id or
	//"local:<container>"), keyed by the No-Intro sha1 of the ROM as loaded.
	//An entry maps to the container the UI resolver picks for that ROM; the
	//core consults it per load (MepPackManager::FindPreferredPack). An empty
	//value is never stored - removing the choice deletes the key.
	public Dictionary<string, string> RomPackPreference { get; set; } = new();

	public void ApplyConfig()
	{
		ConfigApi.SetEnhancementPackConfig(new InteropEnhancementPackConfig() {
			EnableMepPacks = EnableMepPacks,
			EnableTextures = EnableTextures,
			EnableAudio = EnableAudio,
			EnableSynth = EnableSynth,
			EnablePatches = EnablePatches,
			ApplyPatchOnHashMismatch = ApplyPatchOnHashMismatch,
			BootstrapEnhancementFolder = BootstrapEnhancementFolder,
			AutoInstallCommunityPacks = AutoInstallCommunityPacks
		});

		foreach(string container in DisabledPacks) {
			EmuApi.SetMepPackEnabled(container, false);
		}

		//P.3: authoritative reset-then-push - a choice removed from the config
		//(key absent) must also be dropped from the core's per-ROM map.
		EmuApi.ClearPreferredMepPacks();
		foreach(KeyValuePair<string, string> entry in RomPackPreference) {
			EmuApi.SetPreferredMepPack(entry.Key, entry.Value);
		}
	}

	public void SetPackEnabled(string container, bool enabled)
	{
		DisabledPackList.Set(DisabledPacks, container, enabled);
		EmuApi.SetMepPackEnabled(container, enabled);
	}

	public string? GetRomPackPreference(string romSha1)
	{
		return RomPackPreference.TryGetValue(romSha1, out string? packId) ? packId : null;
	}

	public void SetRomPackPreference(string romSha1, string packId)
	{
		if(string.IsNullOrEmpty(packId)) {
			RomPackPreference.Remove(romSha1);
		} else {
			RomPackPreference[romSha1] = packId;
		}
	}
}

[StructLayout(LayoutKind.Sequential)]
public struct InteropEnhancementPackConfig
{
	[MarshalAs(UnmanagedType.I1)] public bool EnableMepPacks;
	[MarshalAs(UnmanagedType.I1)] public bool EnableTextures;
	[MarshalAs(UnmanagedType.I1)] public bool EnableAudio;
	[MarshalAs(UnmanagedType.I1)] public bool EnableSynth;
	[MarshalAs(UnmanagedType.I1)] public bool EnablePatches;
	[MarshalAs(UnmanagedType.I1)] public bool ApplyPatchOnHashMismatch;
	[MarshalAs(UnmanagedType.I1)] public bool BootstrapEnhancementFolder;
	[MarshalAs(UnmanagedType.I1)] public bool AutoInstallCommunityPacks;
}

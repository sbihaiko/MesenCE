using CommunityToolkit.Mvvm.ComponentModel;
using Mesen.Interop;
using System;
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
	[ObservableProperty] public partial bool ApplyPatchOnHashMismatch { get; set; } = false;
	[ObservableProperty] public partial bool BootstrapEnhancementFolder { get; set; } = true;

	//Container names (folder / zip base name) of packs the user turned off
	public List<string> DisabledPacks { get; set; } = new();

	public void ApplyConfig()
	{
		ConfigApi.SetEnhancementPackConfig(new InteropEnhancementPackConfig() {
			EnableMepPacks = EnableMepPacks,
			EnableTextures = EnableTextures,
			EnableAudio = EnableAudio,
			EnableSynth = EnableSynth,
			ApplyPatchOnHashMismatch = ApplyPatchOnHashMismatch,
			BootstrapEnhancementFolder = BootstrapEnhancementFolder
		});

		foreach(string container in DisabledPacks) {
			EmuApi.SetMepPackEnabled(container, false);
		}
	}

	public void SetPackEnabled(string container, bool enabled)
	{
		DisabledPacks.RemoveAll(x => string.Equals(x, container, StringComparison.OrdinalIgnoreCase));
		if(!enabled) {
			DisabledPacks.Add(container);
		}
		EmuApi.SetMepPackEnabled(container, enabled);
	}
}

[StructLayout(LayoutKind.Sequential)]
public struct InteropEnhancementPackConfig
{
	[MarshalAs(UnmanagedType.I1)] public bool EnableMepPacks;
	[MarshalAs(UnmanagedType.I1)] public bool EnableTextures;
	[MarshalAs(UnmanagedType.I1)] public bool EnableAudio;
	[MarshalAs(UnmanagedType.I1)] public bool EnableSynth;
	[MarshalAs(UnmanagedType.I1)] public bool ApplyPatchOnHashMismatch;
	[MarshalAs(UnmanagedType.I1)] public bool BootstrapEnhancementFolder;
}

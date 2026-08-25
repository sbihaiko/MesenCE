using Avalonia.Controls;
using CommunityToolkit.Mvvm.ComponentModel;
using Mesen.Config;
using Mesen.Interop;
using Mesen.Utilities;
using Mesen.Windows;
using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Threading.Tasks;

namespace Mesen.ViewModels
{
	//"Enhancement Packs" window (F3.3): lists the MEP packs matching the loaded
	//ROM (as resolved by the core's MepPackManager), lets the user toggle each
	//pack and each section, and installs .zip packs into EnhancementPacks/.
	public partial class EnhancementPacksViewModel : DisposableViewModel
	{
		[ObservableProperty] public partial MesenList<MepPackEntry> Packs { get; private set; } = new();
		[ObservableProperty] public partial EnhancementPackConfig Config { get; set; }
		[ObservableProperty] public partial string RomSha1 { get; set; } = "";
		[ObservableProperty] public partial string RejectedInfo { get; set; } = "";
		[ObservableProperty] public partial bool HasRejected { get; set; }
		[ObservableProperty] public partial bool HasPacks { get; set; }
		[ObservableProperty] public partial string SiblingFolder { get; set; } = "";
		[ObservableProperty] public partial bool HasSiblingFolder { get; set; }

		public string PacksFolder => ConfigManager.EnhancementPackFolder;

		public EnhancementPacksViewModel()
		{
			Config = ConfigManager.Config.EnhancementPacks;
			Refresh();
		}

		public void Refresh()
		{
			RomSha1 = EmuApi.GetMepRomSha1();
			SiblingFolder = EmuApi.GetMepSiblingFolder();
			HasSiblingFolder = SiblingFolder.Length > 0;

			var packs = new MesenList<MepPackEntry>();
			var rejected = new System.Text.StringBuilder();
			foreach(string line in EmuApi.GetMepPackList().Split('\n', StringSplitOptions.RemoveEmptyEntries)) {
				if(line.StartsWith("!")) {
					rejected.AppendLine(line.Substring(1));
					continue;
				}
				string[] parts = line.Split('\t');
				if(parts.Length < 8) {
					continue;
				}
				packs.Add(new MepPackEntry() {
					Container = parts[0],
					Name = parts[1],
					Version = parts[2],
					Author = parts[3],
					License = parts[4],
					Sections = parts[5].Replace(",", ", "),
					Enabled = parts[6] == "1",
					Source = parts[7] == "2" ? "sibling" : parts[7] == "1" ? "zip" : "folder"
				});
			}
			Packs = packs;
			HasPacks = packs.Count > 0;
			RejectedInfo = rejected.ToString().TrimEnd();
			HasRejected = RejectedInfo.Length > 0;
		}

		//Persists the per-pack toggles + section flags; the core applies them
		//on the next ROM load / power cycle
		public void ApplyChanges()
		{
			foreach(MepPackEntry pack in Packs) {
				Config.SetPackEnabled(pack.Container, pack.Enabled);
			}
			Config.ApplyConfig();
			ConfigManager.Config.Save();
		}

		//<rom dir>/<Game>/ - the artist's workspace (ADR-0049); created on demand
		public void OpenSiblingFolder()
		{
			if(SiblingFolder.Length == 0) {
				return;
			}
			try {
				Directory.CreateDirectory(Path.Combine(SiblingFolder, "textures"));
				Directory.CreateDirectory(Path.Combine(SiblingFolder, "audio"));
				Directory.CreateDirectory(Path.Combine(SiblingFolder, "synth"));
			} catch { }
			OpenFolder(SiblingFolder);
		}

		public void OpenFolder()
		{
			OpenFolder(PacksFolder);
		}

		private void OpenFolder(string folder)
		{
			if(Directory.Exists(folder)) {
				System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo() {
					FileName = folder + Path.DirectorySeparatorChar,
					UseShellExecute = true,
					Verb = "open"
				});
			}
		}

		//Copies a .zip pack into EnhancementPacks/ after a light validation
		//(pack.json at the zip root). The core extracts it to .cache/ on the
		//next scan (ADR-0040). Returns null on success, a message ID otherwise.
		public async Task<string?> InstallPack(Window wnd)
		{
			string? filename = await FileDialogHelper.OpenFile(null, wnd, FileDialogHelper.ZipExt);
			if(filename == null) {
				return null;
			}

			try {
				using(ZipArchive zip = ZipFile.OpenRead(filename)) {
					//pack.json, or the folder convention (ADR-0049) - any layer file
					bool hasLayer = zip.GetEntry("pack.json") != null;
					foreach(string probe in new[] { "textures/hires.txt", "audio/hires.txt", "synth/preset.cfg" }) {
						hasLayer |= zip.GetEntry(probe) != null || zip.GetEntry("auto/" + probe) != null;
					}
					if(!hasLayer) {
						return "InstallMepPackInvalidPack";
					}
					foreach(ZipArchiveEntry entry in zip.Entries) {
						string normalized = entry.FullName.Replace('\\', '/');
						if(normalized.StartsWith("/") || normalized.Split('/').Contains("..") || normalized.Contains(':')) {
							return "InstallMepPackInvalidPack";
						}
					}
				}

				string target = Path.Combine(PacksFolder, Path.GetFileName(filename));
				File.Copy(filename, target, true);
			} catch {
				return "InstallMepPackInvalidZipFile";
			}

			return "";
		}
	}

	public partial class MepPackEntry : ViewModelBase
	{
		[ObservableProperty] public partial bool Enabled { get; set; } = true;
		[ObservableProperty] public partial string Container { get; set; } = "";
		[ObservableProperty] public partial string Name { get; set; } = "";
		[ObservableProperty] public partial string Version { get; set; } = "";
		[ObservableProperty] public partial string Author { get; set; } = "";
		[ObservableProperty] public partial string License { get; set; } = "";
		[ObservableProperty] public partial string Sections { get; set; } = "";
		[ObservableProperty] public partial string Source { get; set; } = "";
	}
}

using Avalonia.Controls;
using CommunityToolkit.Mvvm.ComponentModel;
using Mesen.Config;
using Mesen.Interop;
using Mesen.Logic;
using Mesen.Utilities;
using Mesen.Windows;
using System.Collections.Generic;
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
		//P.3 (PRD-player-shell §5): the container the per-ROM preference picks,
		//resolved via PackPreferenceResolver; "" when no preference/stale.
		[ObservableProperty] public partial string PreferredContainer { get; set; } = "";
		[ObservableProperty] public partial bool HasPreferredContainer { get; set; }
		//"Preferred pack for this ROM" choices: content-merged candidates (a
		//container duplicating another's content_id is not a new entry) + a
		//"(default)" entry that clears the choice.
		[ObservableProperty] public partial MesenList<PreferredChoice> PreferredChoices { get; private set; } = new();
		[ObservableProperty] public partial PreferredChoice? SelectedPreferredChoice { get; set; }
		private bool _suppressPreferenceApply;

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

			MepPackListResult parsed = MepPackListParser.Parse(EmuApi.GetMepPackList());

			var packs = new MesenList<MepPackEntry>();
			foreach(MepPackListEntry entry in parsed.Packs) {
				packs.Add(new MepPackEntry() {
					Container = entry.Container,
					Name = entry.Name,
					Version = entry.Version,
					Author = entry.Author,
					License = entry.License,
					//Display-only formatting stays here, not in MepPackListParser
					//(the parser hands back the raw Sections string).
					Sections = entry.Sections.Replace(",", ", "),
					Enabled = entry.Enabled,
					Source = entry.Source,
					//P.3: identity the preference resolver + picker read.
					PackId = entry.PackId,
					ContentId = entry.ContentId
				});
			}
			Packs = packs;
			HasPacks = packs.Count > 0;
			RejectedInfo = parsed.RejectedInfo;
			HasRejected = parsed.HasRejected;
			RefreshPreference(packs);
		}

		//P.3: resolves the stored per-ROM preference against the current
		//candidates (content_id merge + `local:` fallback) and rebuilds the
		//window's "Preferred pack for this ROM" choices.
		private void RefreshPreference(MesenList<MepPackEntry> packs)
		{
			List<PackPreferenceResolver.Candidate> candidates = packs.Select(p => new PackPreferenceResolver.Candidate() {
				Container = p.Container,
				Name = p.Name,
				PackId = p.PackId,
				ContentId = p.ContentId,
				Version = p.Version,
				Enabled = p.Enabled
			}).ToList();

			string? preference = Config.GetRomPackPreference(RomSha1);
			PackPreferenceResolver.Resolution resolution = PackPreferenceResolver.Resolve(candidates, preference);
			PreferredContainer = resolution.PreferredContainer ?? "";
			HasPreferredContainer = PreferredContainer.Length > 0;

			var choices = new MesenList<PreferredChoice>();
			choices.Add(new PreferredChoice { PackId = "", Display = "(default)" });
			foreach(PackPreferenceResolver.Candidate candidate in resolution.Candidates) {
				choices.Add(new PreferredChoice {
					PackId = PackPreferenceResolver.DerivePackId(candidate),
					Display = candidate.Name + " (" + candidate.Container + ")"
				});
			}
			PreferredChoices = choices;
			SelectedPreferredChoice = choices.FirstOrDefault(c => c.PackId == (preference ?? "")) ?? choices[0];
		}

		partial void OnSelectedPreferredChoiceChanged(PreferredChoice? value)
		{
			if(_suppressPreferenceApply || value == null) {
				return;
			}
			ApplyPreferredPackId(value.PackId);
		}

		//Persists the chosen pack_id ("" clears) for the loaded ROM and pushes
		//it to the core; takes effect on the next load / power cycle.
		public void ApplyPreferredPackId(string packId)
		{
			Config.SetRomPackPreference(RomSha1, packId);
			Config.ApplyConfig();
			ConfigManager.Config.Save();
			_suppressPreferenceApply = true;
			Refresh();
			_suppressPreferenceApply = false;
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

		//Copies a .zip pack into EnhancementPacks/ after validating its layer
		//and entry paths via MepZipValidator (pack.json, or any convention
		//probe per ADR-0049/ADR-0047, zip-slip rejected). The core extracts
		//it to .cache/ on the next scan (ADR-0040). Returns null on success,
		//a message ID otherwise.
		public async Task<string?> InstallPack(Window wnd)
		{
			string? filename = await FileDialogHelper.OpenFile(null, wnd, FileDialogHelper.ZipExt);
			if(filename == null) {
				return null;
			}

			try {
				string? error;
				using(ZipArchive zip = ZipFile.OpenRead(filename)) {
					error = MepZipValidator.Validate(zip);
				}
				if(error != null) {
					return error;
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
		//P.3: identity from .mep-install.json ("" for a stamp-less container)
		[ObservableProperty] public partial string PackId { get; set; } = "";
		[ObservableProperty] public partial string ContentId { get; set; } = "";
	}

	//P.3: one entry of the "Preferred pack for this ROM" ComboBox. PackId is
	//the ADR-0140 pack_id stored in the config ("" = the "(default)" entry
	//that clears the choice); Display is what the combo shows.
	public sealed class PreferredChoice
	{
		public string PackId { get; init; } = "";
		public string Display { get; init; } = "";
		public override string ToString() => Display;
	}
}

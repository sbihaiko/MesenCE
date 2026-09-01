using Mesen.Config;
using Mesen.Interop;
using Mesen.Logic;
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

namespace Mesen.Services
{
	//Host-aware orchestrator for F6.4b's client-side MEP-recipe auto-install
	//(ADR-0138 clarifications 37/38/43/45-47). Install() takes exactly
	//CommunityPackCatalogFetcher's output shape (matched entry, verified
	//primary path, dep-id -> verified path map), drives the host-free
	//UI/Logic decision helpers plus the File/EmuApi calls those can't make
	//themselves, and hands the recipe's raw JSON text (never re-interpreted
	//client-side, clarification 45) to EmuApi.InstallMepRecipe.
	public static class CommunityPackInstallCoordinator
	{
		public static CommunityPackInstallOutcome Install(
			CommunityPackCatalogEntry entry, string primaryPackPath, IReadOnlyDictionary<string, string> resolvedDepPaths)
		{
			EnhancementPackConfig config = ConfigManager.Config.EnhancementPacks;
			string containerName = GetContainerName(entry);
			EmuApi.WriteLogEntry("[CommunityPackInstall] containerName=" + containerName);
			(CommunityPackInstallOutcome? gate, string outFolder) = EvaluateGates(config, entry, containerName);
			if(gate != null) {
				EmuApi.WriteLogEntry("[CommunityPackInstall] gated: Status=" + gate.Status + " Message=" + gate.Message);
				return gate;
			}
			EmuApi.WriteLogEntry("[CommunityPackInstall] gates passed, outFolder=" + outFolder);

			(Dictionary<string, string> depPaths, List<CommunityPackDepPrompt> pending) = ResolveDeps(entry, resolvedDepPaths, outFolder);

			if(entry.IsHdLegacy) {
				//MEI-v1.md §2.3: an hd-legacy entry is a plain HD/texture pack
				//with no MEP recipe - InstallMepRecipe cannot parse one. Extract
				//the zip's pack root straight into HdPacks/<rom>/ instead, the
				//classic loose pack location (ADR-0040 §5 - a loose HD pack
				//wins over MEP textures).
				EmuApi.WriteLogEntry("[CommunityPackInstall] hd-legacy entry - installing as a loose HD pack");
				CommunityPackInstallOutcome outcome = InstallHdLegacy(entry, primaryPackPath, outFolder, containerName);
				//A legacy install has no recipe deps, but unresolved user_supplied
				//prompts still get surfaced so the user knows what to drop where.
				if(outcome.Status == CommunityPackInstallStatus.Installed) {
					RecordInstall(entry, outFolder);
				}
				return pending.Count == 0 || outcome.Status != CommunityPackInstallStatus.Installed
					? outcome
					: new CommunityPackInstallOutcome(outcome.Status, outcome.ContainerName, outcome.Message, outcome.Withheld, pending);
			}

			EmuApi.WriteLogEntry("[CommunityPackInstall] calling EmuApi.InstallMepRecipe: recipeLen=" + (entry.Recipe?.GetRawText()?.Length ?? 0) +
				" primaryPackPath=" + primaryPackPath + " depPaths=" + depPaths.Count + " pendingDeps=" + pending.Count);
			bool success = EmuApi.InstallMepRecipe(
				entry.Recipe?.GetRawText() ?? "", primaryPackPath, BuildDepPathsBlob(depPaths),
				EmuApi.GetRomInfo().GetRomName(), outFolder, out string resultText);
			EmuApi.WriteLogEntry("[CommunityPackInstall] InstallMepRecipe returned success=" + success + " resultText=" + resultText.Replace("\n", "\\n"));
			if(success) {
				RecordInstall(entry, outFolder);
				return CommunityPackInstallOutcome.Installed(containerName, ParseWithheld(resultText), pending);
			}
			return CommunityPackInstallOutcome.Failed(ParseError(resultText));
		}

		//Legacy HD pack install (kind: "hd-legacy", no MEP recipe - MEI-v1
		//§2.3): the classic loose-pack location is HdPacks/<rom>/hires.txt
		//(FolderUtilities.GetHdPackFolder()), which HdTilePack::LoadForRom and
		//the NES HdPackLoader read and which takes precedence over MEP textures
		//(ADR-0040 §5). We extract the zip's pack root (the folder holding
		//hires.txt) flattened to the loaded ROM's file name, and stamp the MEP
		//container so the P.6 update decision sees the install on the next load.
		private static CommunityPackInstallOutcome InstallHdLegacy(
			CommunityPackCatalogEntry entry, string primaryPackPath, string outFolder, string containerName)
		{
			string romName = EmuApi.GetRomInfo().GetRomName();
			if(string.IsNullOrWhiteSpace(romName)) {
				EmuApi.WriteLogEntry("[CommunityPackInstall] hd-legacy install failed: no loaded ROM name");
				return CommunityPackInstallOutcome.Failed("no loaded ROM name for legacy HD pack install");
			}

			//ADR-0147: MEP-ize the legacy pack on install - the pack root goes to
			//mep/textures/ and a pack.json is written, so it loads through the
			//MEP textures section (GetSectionPath) instead of the separate
			//HdPacks/<rom>/ path; the pack stays visible and editable in mep/.
			string texturesFolder = Path.Combine(outFolder, "textures");
			string stampPath = Path.Combine(outFolder, ".mep-install.json");
			if(File.Exists(stampPath) && Directory.Exists(outFolder)) {
				EmuApi.WriteLogEntry("[CommunityPackInstall] hd-legacy reinstall - clearing " + outFolder);
				ClearFolderForReinstall(outFolder);
			}

			if(!TryExtractLegacyPack(primaryPackPath, texturesFolder, romName, out string error)) {
				EmuApi.WriteLogEntry("[CommunityPackInstall] hd-legacy extract failed: " + error);
				return CommunityPackInstallOutcome.Failed(error);
			}

			Directory.CreateDirectory(outFolder);
			File.WriteAllText(Path.Combine(outFolder, "pack.json"), BuildLegacyPackJson(entry, EmuApi.GetMepRomSha1(), romName));
			File.WriteAllText(stampPath, BuildLegacyInstallStamp(entry, entry.Sha256));
			EmuApi.WriteLogEntry("[CommunityPackInstall] hd-legacy installed (MEP-ized): " + outFolder);
			return CommunityPackInstallOutcome.Installed(containerName, Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		}

		//Finds the pack root (the folder that holds hires.txt) inside a legacy
		//HD pack zip and extracts its contents into targetFolder, preserving
		//relative paths. Files outside the pack root (banner art, READMEs, ...)
		//are skipped - the classic loader only reads what hires.txt references.
		//A wrapper zip holding exactly one root-level nested zip (the
		//"UnZipMeFirst"-style release, e.g. Zelda Remastered), or a GitHub
		//repo archive with one pack zip in the matching game folder
		//(LiQuiDz HDnes: HDnes-main/1942/1942audio.zip), is unwrapped
		//in-memory and extracted while that inner ZipArchive is still open
		//(ZipArchiveEntry.Open throws ObjectDisposedException after Dispose).
		//Root discovery + zip-slip + extract live in host-free
		//LegacyHdPackInstall (UI/Logic, unit-tested); this opens the file.
		private static bool TryExtractLegacyPack(string zipPath, string targetFolder, string romName, out string error)
		{
			error = "";
			try {
				Directory.CreateDirectory(targetFolder);
				using ZipArchive outer = ZipFile.OpenRead(zipPath);
				return LegacyHdPackInstall.ExtractToFolder(outer, targetFolder, romName, out error);
			} catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or InvalidDataException or ObjectDisposedException) {
				error = "cannot extract legacy HD pack: " + ex.Message;
				return false;
			}
		}

		//Minimal .mep-install.json for a legacy pack (no recipe_hash/deps): the
		//fields CommunityCatalogUpdateDecision.ReadStampFields reads (content_id
		//+ source.sha256) plus pack_id/installed_at for inspection.
		private static string BuildLegacyInstallStamp(CommunityPackCatalogEntry entry, string primarySha256)
		{
			StringBuilder sb = new();
			sb.Append("{\n");
			if(!string.IsNullOrWhiteSpace(entry.PackId)) {
				sb.Append("  \"pack_id\": \"").Append(JsonEscape(entry.PackId)).Append("\",\n");
			}
			if(!string.IsNullOrWhiteSpace(entry.ContentId)) {
				sb.Append("  \"content_id\": \"").Append(JsonEscape(entry.ContentId)).Append("\",\n");
			}
			sb.Append("  \"source\": { \"sha256\": \"").Append(primarySha256).Append("\" },\n");
			sb.Append("  \"installed_at\": \"").Append(DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")).Append("\"\n");
			sb.Append("}\n");
			return sb.ToString();
		}

		//MEP-ized pack.json for a legacy HD pack (ADR-0147): the pack root is
		//extracted to mep/textures/, so it loads as a MEP `textures` section.
		//Location is identity (MEP-v1 §2.1 rule 8) - the target records the
		//loaded ROM's No-Intro SHA-1 (or the catalog's) for reference only.
		private static string BuildLegacyPackJson(CommunityPackCatalogEntry entry, string romSha1, string romName)
		{
			string system = string.IsNullOrWhiteSpace(entry.System) ? "nes" : entry.System;
			string version = string.IsNullOrWhiteSpace(entry.Version) ? "1.0.0" : entry.Version;
			string sha1 = string.IsNullOrWhiteSpace(romSha1) ? (entry.Rom.Sha1 ?? "") : romSha1;
			StringBuilder sb = new();
			sb.Append("{\n");
			sb.Append("  \"mep\": \"1.0.0\",\n");
			sb.Append("  \"name\": \"").Append(JsonEscape(entry.Name)).Append("\",\n");
			sb.Append("  \"version\": \"").Append(JsonEscape(version)).Append("\",\n");
			sb.Append("  \"license\": \"").Append(JsonEscape(entry.LicenseOrUnknown)).Append("\",\n");
			sb.Append("  \"targets\": [\n");
			sb.Append("    { \"system\": \"").Append(JsonEscape(system)).Append("\", \"sha1\": \"").Append(JsonEscape(sha1)).Append("\", \"name\": \"").Append(JsonEscape(romName)).Append("\" }\n");
			sb.Append("  ],\n");
			sb.Append("  \"sections\": { \"textures\": { \"path\": \"textures/\" } }\n");
			sb.Append("}\n");
			return sb.ToString();
		}

		private static string JsonEscape(string value) =>
			value.Replace("\\", "\\\\").Replace("\"", "\\\"");

		//AutoInstallCommunityPacks master switch (ADR-0146) + 43(c) DisabledPacks gate, then the 43(a)/(b)
		//reinstall verdict: Reinstall means our own prior install, safe to clear.
		private static (CommunityPackInstallOutcome? Gate, string OutFolder) EvaluateGates(
			EnhancementPackConfig config, CommunityPackCatalogEntry entry, string containerName)
		{
			//ADR-0146: no consent dialog - the master switch alone decides.
			if(!config.AutoInstallCommunityPacks) {
				return (CommunityPackInstallOutcome.Skipped("AutoInstallCommunityPacks is off"), "");
			}
			if(config.DisabledPacks.Contains(containerName, StringComparer.OrdinalIgnoreCase)) {
				return (CommunityPackInstallOutcome.Skipped("pack disabled by user"), "");
			}

			string outFolder = ResolveOutFolder(containerName);
			//P.6 (PRD Part B §3.6, amends ADR-0138 §37): the update trigger
			//is the installed content_id vs the slot's, not source.sha256 - a
			//different content_id reinstalls (unless the installed semver is
			//newer, no auto-downgrade); an unchanged content_id never reinstalls
			//(wrapper-only repack); a removed slot keeps the install. The
			//container name is unchanged by an update, so DisabledPacks and the
			//per-section flags survive the reinstall.
			InstallStampFields? stamp = CommunityCatalogUpdateDecision.ReadStampFields(ReadInstallStamp(outFolder));
			CommunityCatalogUpdateVerdict verdict = CommunityCatalogUpdateDecision.Decide(
				entry.ContentId, entry.Version, entry.Sha256, entry.IsHdLegacy, stamp, GetInstalledVersion(containerName));
			EmuApi.WriteLogEntry("[CommunityPackInstall] update verdict=" + verdict + " installStampExists=" + (stamp != null) +
				" entryContentId=" + entry.ContentId + " entrySha256=" + entry.Sha256);

			switch(verdict) {
				case CommunityCatalogUpdateVerdict.UpToDate:
				case CommunityCatalogUpdateVerdict.WrapperOnly:
				case CommunityCatalogUpdateVerdict.NoDowngrade:
				case CommunityCatalogUpdateVerdict.RemovedFromCatalog:
					//Silent by §3.6: these keep the install (no toast).
					return (CommunityPackInstallOutcome.Skipped(verdict.ToString()), "");
				case CommunityCatalogUpdateVerdict.Updated:
					//ADR-0147: never silently clobber a locally-edited mep/ - offer
					//Restore instead so the user's customization survives an update.
					if(IsPackEdited(EmuApi.GetMepRomSha1(), outFolder)) {
						return (CommunityPackInstallOutcome.UpdateAvailable("The catalog pack was updated - use Restore pack to apply it."), "");
					}
					ClearFolderForReinstall(outFolder);
					return (null, outFolder);
				default: //NotInstalled - a fresh install proceeds
					return (null, outFolder);
			}
		}

		//The installed pack's declared version (GetMepPackList column 3) for the
		//no-downgrade guard - the .mep-install.json stamp carries no version.
		private static string? GetInstalledVersion(string containerName)
		{
			MepPackListResult parsed = MepPackListParser.Parse(EmuApi.GetMepPackList());
			return parsed.Packs.FirstOrDefault(p => p.Container.Equals(containerName, StringComparison.OrdinalIgnoreCase))?.Version;
		}

		//Clarification 46 scratch folder; downloaded/user-supplied deps live here by sha256.
		public static string GetDownloadsCacheFolder() => Path.Combine(ConfigManager.EnhancementPackFolder, ".cache", "downloads");

		//Resolves deps not already in resolvedDepPaths; unresolved becomes a prompt.
		private static (Dictionary<string, string>, List<CommunityPackDepPrompt>) ResolveDeps(
			CommunityPackCatalogEntry entry, IReadOnlyDictionary<string, string> resolvedDepPaths, string outFolder)
		{
			Dictionary<string, string> depPaths = new(resolvedDepPaths, StringComparer.Ordinal);
			List<CommunityPackDepPrompt> pending = new();
			if(entry.Deps == null || entry.Deps.Length == 0) {
				return (depPaths, pending);
			}

			List<CommunityPackLocalFile> packFiles = HashFolder(outFolder);
			List<CommunityPackLocalFile> cacheFiles = HashFolder(GetDownloadsCacheFolder());

			foreach(CommunityPackDep dep in entry.Deps) {
				if(string.IsNullOrEmpty(dep.Id) || depPaths.ContainsKey(dep.Id) || string.IsNullOrEmpty(dep.Sha256)) {
					continue;
				}

				CommunityPackDepResolution resolution = CommunityPackDepResolver.Resolve(
					dep.Sha256, packFiles, cacheFiles, dep.Hints != null ? string.Join(", ", dep.Hints) : null, dep.License);

				if(resolution.ResolvedPath != null) {
					depPaths[dep.Id] = resolution.ResolvedPath;
				} else {
					//Unresolved: MepRecipeInstaller withholds the dependent patch (§6).
					pending.Add(new CommunityPackDepPrompt(dep.Id, resolution.Hints, resolution.License, GetDownloadsCacheFolder()));
				}
			}
			return (depPaths, pending);
		}

		//Clarification 47 row grammar: "depId\tlocalPath" per line, empty means no deps.
		private static string BuildDepPathsBlob(Dictionary<string, string> depPaths) =>
			string.Join("\n", depPaths.Select(kv => kv.Key + "\t" + kv.Value));

		//outResult rows (EmuApiWrapperMep.cpp): 0 = "1"/"0", 1 = error, rest = Withheld.
		private static string ParseError(string resultText)
		{
			string[] rows = resultText.Split('\n');
			return rows.Length > 1 ? rows[1] : resultText;
		}

		private static List<string> ParseWithheld(string resultText)
		{
			string[] rows = resultText.Split('\n');
			return rows.Length > 2 ? rows.Skip(2).Where(r => r.Length > 0).ToList() : new List<string>();
		}

		private static string? ReadInstallStamp(string outFolder)
		{
			string stampPath = Path.Combine(outFolder, ".mep-install.json");
			try {
				return File.Exists(stampPath) ? File.ReadAllText(stampPath) : null;
			} catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {
				return null;
			}
		}

		//ADR-0147: after a successful install, record the ROM -> pack mapping in
		//the central cache (outside mep/) so Restore can recover the original
		//even when the user has edited or removed the editable mep/ folder.
		private static void RecordInstall(CommunityPackCatalogEntry entry, string outFolder)
		{
			string cacheRoot = Path.Combine(ConfigManager.EnhancementPackFolder, ".cache");
			CommunityPackInstallRegistry.Write(cacheRoot, EmuApi.GetMepRomSha1(), new CommunityPackInstallRecord {
				PackId = entry.PackId ?? "",
				ContentId = entry.ContentId ?? "",
				SourceSha256 = entry.Sha256,
				Container = GetContainerName(entry),
				MepPath = outFolder,
				InstalledAt = DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"),
				BaselineContentId = EmuApi.GetMepContentId(outFolder),
			});
		}

		//ADR-0147: true when the installed mep/ tree differs from the baseline
		//recorded at install time (a local edit), or when no baseline exists -
		//conservative: an unknown state never gets silently clobbered by an update.
		private static bool IsPackEdited(string romSha1, string outFolder)
		{
			string cacheRoot = Path.Combine(ConfigManager.EnhancementPackFolder, ".cache");
			CommunityPackInstallRecord? record = CommunityPackInstallRegistry.Read(cacheRoot, romSha1);
			if(record == null || string.IsNullOrWhiteSpace(record.BaselineContentId)) {
				return true; //no baseline - be safe
			}
			string current = EmuApi.GetMepContentId(outFolder);
			return !string.Equals(current, record.BaselineContentId, StringComparison.Ordinal);
		}

		//ADR-0147: explicit user action - discard a locally-edited mep/ and
		//re-materialize it from the original catalog artifact (Restore). Unlike
		//Install(), this ignores the update verdict (it is a "undo my edits",
		//not an update check) and always rewrites the pack from the supplied
		//artifact. The install registry is refreshed so the next Restore/update
		//still knows the pack and its source sha256.
		public static bool Restore(CommunityPackCatalogEntry entry, string primaryPackPath, out string error)
		{
			string containerName = GetContainerName(entry);
			string outFolder = ResolveOutFolder(containerName);
			if(entry.IsHdLegacy) {
				//InstallHdLegacy clears a prior install (stamp exists) and rewrites it
				CommunityPackInstallOutcome outcome = InstallHdLegacy(entry, primaryPackPath, outFolder, containerName);
				if(outcome.Status != CommunityPackInstallStatus.Installed) {
					error = outcome.Message;
					return false;
				}
			} else {
				ClearFolderForReinstall(outFolder);
				if(!EmuApi.InstallMepRecipe(
					entry.Recipe?.GetRawText() ?? "", primaryPackPath, "",
					EmuApi.GetRomInfo().GetRomName(), outFolder, out string resultText)) {
					error = ParseError(resultText);
					return false;
				}
			}
			RecordInstall(entry, outFolder);
			error = "";
			return true;
		}

		private static void ClearFolderForReinstall(string outFolder)
		{
			try {
				if(Directory.Exists(outFolder)) {
					Directory.Delete(outFolder, true);
				}
			} catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {
			}
		}

		private static List<CommunityPackLocalFile> HashFolder(string folder)
		{
			List<CommunityPackLocalFile> files = new();
			if(!Directory.Exists(folder)) {
				return files;
			}
			foreach(string path in Directory.EnumerateFiles(folder, "*", SearchOption.AllDirectories)) {
				try {
					using FileStream stream = File.OpenRead(path);
					files.Add(new CommunityPackLocalFile(path, Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant()));
				} catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {
				}
			}
			return files;
		}

		//Destination-folder/DisabledPacks-key name (ADR-0040): the sanitization is the host-free
		//CommunityPackContainerName (UI/Logic, pinned by UI.Tests); ResolveOutFolder roots it.
		private static string GetContainerName(CommunityPackCatalogEntry entry) =>
			CommunityPackContainerName.Sanitize(entry.Name, entry.Game);

		//Defense in depth on GetContainerName's sanitization: asserts the folder is still rooted under EnhancementPackFolder.
		private static string ResolveOutFolder(string containerName)
		{
			//ADR-0147: the installed pack lives at the ROM's sibling mep/ so it stays
			//visible and editable beside the game (auto/ = recorder, mep/ = pack).
			//Fall back to the central EnhancementPacks/<container> when the sibling
			//is absent or not writable (ADR-0049's read-only-ROM-folder fallback).
			string sibling = EmuApi.GetMepSiblingFolder();
			if(!string.IsNullOrWhiteSpace(sibling)) {
				string siblingMep = Path.GetFullPath(Path.Combine(sibling, "mep"));
				try {
					Directory.CreateDirectory(siblingMep);
					return siblingMep;
				} catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {
					//ROM folder not writable - fall through to the central folder
				}
			}
			string root = Path.GetFullPath(ConfigManager.EnhancementPackFolder);
			string outFolder = Path.GetFullPath(Path.Combine(root, containerName));
			if(outFolder != root && !outFolder.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal)) {
				throw new InvalidOperationException("Community pack container name escaped the enhancement pack folder: " + containerName);
			}
			return outFolder;
		}
	}

	public enum CommunityPackInstallStatus { Skipped, Installed, Failed, UpdateAvailable }

	//Verdict-carrying result of Install(); the caller decides how to surface each case.
	public sealed record CommunityPackInstallOutcome(
		CommunityPackInstallStatus Status, string ContainerName, string Message,
		IReadOnlyList<string> Withheld, IReadOnlyList<CommunityPackDepPrompt> PendingDeps)
	{
		public static CommunityPackInstallOutcome Skipped(string reason) => new(CommunityPackInstallStatus.Skipped, "", reason, Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome Failed(string error) => new(CommunityPackInstallStatus.Failed, "", error, Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome UpdateAvailable(string message) => new(CommunityPackInstallStatus.UpdateAvailable, "", message, Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome Installed(string containerName, IReadOnlyList<string> withheld, IReadOnlyList<CommunityPackDepPrompt> pendingDeps) =>
			new(CommunityPackInstallStatus.Installed, containerName, "", withheld, pendingDeps);
	}

	//Unresolved user_supplied dep (MEI-v1.md §2.3): caller prompts with Hints/License/DropFolder.
	public sealed record CommunityPackDepPrompt(string DepId, string Hints, string License, string DropFolder);
}

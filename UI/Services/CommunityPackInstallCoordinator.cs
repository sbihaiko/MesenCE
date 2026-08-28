using Mesen.Config;
using Mesen.Interop;
using Mesen.Logic;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;

namespace Mesen.Services
{
	//Host-aware orchestrator for F6.4b's client-side MEP-recipe auto-install
	//(ADR-0138 clarifications 37/38/43/45-47). Install() takes exactly
	//CommunityPackCatalogFetcher's output shape (matched entry, verified
	//primary path, dep-id -> verified path map), drives the host-free
	//UI/Logic decision helpers plus the File/EmuApi calls those can't make
	//themselves (UI/Logic firewall, UI/AGENTS.md), and hands the recipe's
	//raw JSON text - never re-interpreted client-side (clarification 45) -
	//to EmuApi.InstallMepRecipe. Outside the firewall's scope on purpose.
	public static class CommunityPackInstallCoordinator
	{
		public static CommunityPackInstallOutcome Install(
			CommunityPackCatalogEntry entry, string primaryPackPath, IReadOnlyDictionary<string, string> resolvedDepPaths)
		{
			EnhancementPackConfig config = ConfigManager.Config.EnhancementPacks;

			//Clarification 38: first automatic download of a session is gated
			//behind a one-time consent, on top of the toggle.
			CommunityPackConsentDecision consent = CommunityPackConsentState.Evaluate(
				config.AutoInstallCommunityPacks, config.CommunityPackAutoInstallConsentGiven);
			if(consent.MustShowConsentDialog) {
				return CommunityPackInstallOutcome.NeedsConsent();
			}
			if(!consent.CanDownloadNow) {
				return CommunityPackInstallOutcome.Skipped("AutoInstallCommunityPacks is off");
			}

			string containerName = GetContainerName(entry);
			if(config.DisabledPacks.Contains(containerName, StringComparer.OrdinalIgnoreCase)) {
				return CommunityPackInstallOutcome.Skipped("pack disabled by user"); //clarification 43(c)
			}

			string outFolder = Path.Combine(ConfigManager.EnhancementPackFolder, containerName);
			CommunityPackReinstallVerdict verdict = CommunityPackReinstallDecision.Decide(entry.Sha256, ReadInstallStamp(outFolder));
			if(verdict == CommunityPackReinstallVerdict.UpToDate) {
				return CommunityPackInstallOutcome.Skipped("already up to date");
			}
			if(verdict == CommunityPackReinstallVerdict.Reinstall) {
				//43(a)/(b) held, (c) just checked above: this folder is our own
				//prior install (its stamp is what got us here) - safe to clear.
				//The native installer refuses to write into a non-empty folder.
				ClearFolderForReinstall(outFolder);
			}
			//NotInstalled + stampless-but-non-empty outFolder (user-owned): left
			//alone, the native non-empty-folder guard fails it below instead.

			(Dictionary<string, string> depPaths, List<CommunityPackDepPrompt> pending) = ResolveDeps(entry, resolvedDepPaths, outFolder);

			bool success = EmuApi.InstallMepRecipe(
				entry.Recipe?.GetRawText() ?? "", primaryPackPath, BuildDepPathsBlob(depPaths),
				EmuApi.GetRomInfo().GetRomName(), outFolder, out string resultText);

			return success
				? CommunityPackInstallOutcome.Installed(containerName, ParseWithheld(resultText), pending)
				: CommunityPackInstallOutcome.Failed(ParseError(resultText));
		}

		//ADR-0138 clarification 46 scratch folder; downloaded/user-supplied
		//deps are looked up here by sha256.
		public static string GetDownloadsCacheFolder() => Path.Combine(ConfigManager.EnhancementPackFolder, ".cache", "downloads");

		//Resolves deps not already in resolvedDepPaths via CommunityPackDepResolver;
		//an unresolved dep becomes a prompt (this class never opens a dialog itself).
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
				if(depPaths.ContainsKey(dep.Id) || string.IsNullOrEmpty(dep.Sha256)) {
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

		//Clarification 47 row grammar ("depId\tlocalPath" per line, matching
		//GetMepPackList); empty blob means no deps (EmuApiWrapperMep.cpp).
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
				string? sha256 = TryHashFile(path);
				if(sha256 != null) {
					files.Add(new CommunityPackLocalFile(path, sha256));
				}
			}
			return files;
		}

		private static string? TryHashFile(string path)
		{
			try {
				using FileStream stream = File.OpenRead(path);
				return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
			} catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {
				return null;
			}
		}

		//Destination-folder/DisabledPacks-key name (ADR-0040): sanitized
		//entry.Name (fallback Game) - matched by ROM sha1, not by this name.
		private static string GetContainerName(CommunityPackCatalogEntry entry)
		{
			string raw = string.IsNullOrWhiteSpace(entry.Name) ? entry.Game : entry.Name;
			char[] invalid = Path.GetInvalidFileNameChars();
			string sanitized = new string(raw.Select(c => invalid.Contains(c) ? '_' : c).ToArray()).Trim();
			return sanitized.Length > 0 ? sanitized : "community-pack";
		}
	}

	public enum CommunityPackInstallStatus { NeedsConsent, Skipped, Installed, Failed }

	//Verdict-carrying result of Install(); the caller decides how to surface each case.
	public sealed record CommunityPackInstallOutcome(
		CommunityPackInstallStatus Status, string ContainerName, string Message,
		IReadOnlyList<string> Withheld, IReadOnlyList<CommunityPackDepPrompt> PendingDeps)
	{
		public static CommunityPackInstallOutcome NeedsConsent() =>
			new(CommunityPackInstallStatus.NeedsConsent, "", "", Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome Skipped(string reason) =>
			new(CommunityPackInstallStatus.Skipped, "", reason, Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome Failed(string error) =>
			new(CommunityPackInstallStatus.Failed, "", error, Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome Installed(
			string containerName, IReadOnlyList<string> withheld, IReadOnlyList<CommunityPackDepPrompt> pendingDeps) =>
			new(CommunityPackInstallStatus.Installed, containerName, "", withheld, pendingDeps);
	}

	//Unresolved user_supplied dep (MEI-v1.md §2.3): caller prompts with
	//Hints/License and DropFolder (clarification 46 downloads cache).
	public sealed record CommunityPackDepPrompt(string DepId, string Hints, string License, string DropFolder);
}

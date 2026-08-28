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
	//themselves, and hands the recipe's raw JSON text (never re-interpreted
	//client-side, clarification 45) to EmuApi.InstallMepRecipe.
	public static class CommunityPackInstallCoordinator
	{
		public static CommunityPackInstallOutcome Install(
			CommunityPackCatalogEntry entry, string primaryPackPath, IReadOnlyDictionary<string, string> resolvedDepPaths)
		{
			EnhancementPackConfig config = ConfigManager.Config.EnhancementPacks;
			string containerName = GetContainerName(entry);
			(CommunityPackInstallOutcome? gate, string outFolder) = EvaluateGates(config, entry, containerName);
			if(gate != null) {
				return gate;
			}

			(Dictionary<string, string> depPaths, List<CommunityPackDepPrompt> pending) = ResolveDeps(entry, resolvedDepPaths, outFolder);
			bool success = EmuApi.InstallMepRecipe(
				entry.Recipe?.GetRawText() ?? "", primaryPackPath, BuildDepPathsBlob(depPaths),
				EmuApi.GetRomInfo().GetRomName(), outFolder, out string resultText);

			return success
				? CommunityPackInstallOutcome.Installed(containerName, ParseWithheld(resultText), pending)
				: CommunityPackInstallOutcome.Failed(ParseError(resultText));
		}

		//Clarification 38 consent + 43(c) DisabledPacks gate, then the 43(a)/(b)
		//reinstall verdict: Reinstall means our own prior install, safe to clear.
		private static (CommunityPackInstallOutcome? Gate, string OutFolder) EvaluateGates(
			EnhancementPackConfig config, CommunityPackCatalogEntry entry, string containerName)
		{
			CommunityPackConsentDecision consent = CommunityPackConsentState.Evaluate(
				config.AutoInstallCommunityPacks, config.CommunityPackAutoInstallConsentGiven);
			if(consent.MustShowConsentDialog) {
				return (CommunityPackInstallOutcome.NeedsConsent(), "");
			}
			if(!consent.CanDownloadNow) {
				return (CommunityPackInstallOutcome.Skipped("AutoInstallCommunityPacks is off"), "");
			}
			if(config.DisabledPacks.Contains(containerName, StringComparer.OrdinalIgnoreCase)) {
				return (CommunityPackInstallOutcome.Skipped("pack disabled by user"), "");
			}

			string outFolder = ResolveOutFolder(containerName);
			CommunityPackReinstallVerdict verdict = CommunityPackReinstallDecision.Decide(entry.Sha256, ReadInstallStamp(outFolder));
			if(verdict == CommunityPackReinstallVerdict.UpToDate) {
				return (CommunityPackInstallOutcome.Skipped("already up to date"), "");
			}
			if(verdict == CommunityPackReinstallVerdict.Reinstall) {
				ClearFolderForReinstall(outFolder);
			}
			return (null, outFolder);
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

		//Destination-folder/DisabledPacks-key name (ADR-0040): entry.Name (fallback
		//Game) is remote, submitter-influenced data (MEI-v1.md §2.2) reaching a
		//path sink, so beyond swapping invalid chars this rejects dot-only names
		//('.'/'..'), strips trailing dots/spaces (Windows), and caps length.
		private static string GetContainerName(CommunityPackCatalogEntry entry)
		{
			string raw = string.IsNullOrWhiteSpace(entry.Name) ? entry.Game : entry.Name;
			char[] invalid = Path.GetInvalidFileNameChars();
			string sanitized = new string(raw.Select(c => invalid.Contains(c) ? '_' : c).ToArray()).Trim().TrimEnd('.', ' ');
			if(sanitized.Length > 96) {
				sanitized = sanitized.Substring(0, 96).TrimEnd('.', ' '); //truncation can re-expose a trailing dot/space
			}
			return sanitized.Length == 0 || sanitized.All(c => c == '.') ? "community-pack" : sanitized;
		}

		//Defense in depth on GetContainerName's sanitization: asserts the folder is still rooted under EnhancementPackFolder.
		private static string ResolveOutFolder(string containerName)
		{
			string root = Path.GetFullPath(ConfigManager.EnhancementPackFolder);
			string outFolder = Path.GetFullPath(Path.Combine(root, containerName));
			if(outFolder != root && !outFolder.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.Ordinal)) {
				throw new InvalidOperationException("Community pack container name escaped the enhancement pack folder: " + containerName);
			}
			return outFolder;
		}
	}

	public enum CommunityPackInstallStatus { NeedsConsent, Skipped, Installed, Failed }

	//Verdict-carrying result of Install(); the caller decides how to surface each case.
	public sealed record CommunityPackInstallOutcome(
		CommunityPackInstallStatus Status, string ContainerName, string Message,
		IReadOnlyList<string> Withheld, IReadOnlyList<CommunityPackDepPrompt> PendingDeps)
	{
		public static CommunityPackInstallOutcome NeedsConsent() => new(CommunityPackInstallStatus.NeedsConsent, "", "", Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome Skipped(string reason) => new(CommunityPackInstallStatus.Skipped, "", reason, Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome Failed(string error) => new(CommunityPackInstallStatus.Failed, "", error, Array.Empty<string>(), Array.Empty<CommunityPackDepPrompt>());
		public static CommunityPackInstallOutcome Installed(string containerName, IReadOnlyList<string> withheld, IReadOnlyList<CommunityPackDepPrompt> pendingDeps) =>
			new(CommunityPackInstallStatus.Installed, containerName, "", withheld, pendingDeps);
	}

	//Unresolved user_supplied dep (MEI-v1.md §2.3): caller prompts with Hints/License/DropFolder.
	public sealed record CommunityPackDepPrompt(string DepId, string Hints, string License, string DropFolder);
}

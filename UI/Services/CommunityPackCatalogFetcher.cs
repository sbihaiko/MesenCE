using Mesen.Config;
using Mesen.Interop;
using Mesen.Logic;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading.Tasks;

namespace Mesen.Services
{
	//Network-facing half of F6.4b-2 (ADR-0138 §37/§38/§41/§42/§46): fetches the MEI v1.1 catalog,
	//matches the loaded ROM by No-Intro sha1 (EmuApi.GetMepRomSha1) then, if that misses, by
	//game identity (GetRomName vs entry.game) for entries that already carry a sha1, downloads+verifies the
	//matched entry's primary artifact and its directly-downloadable deps. Only class in UI/
	//issuing HTTP for community packs - Core/ stays HTTP-free (§37), UI/Logic/*.cs stays
	//host-free (UI/AGENTS.md firewall), hence UI/Services/. CONTRACT (shared with
	//CommunityPackInstallCoordinator, T2): FetchMatchingPackAsync returns exactly a matched
	//Mesen.Logic catalog-entry DTO plus the verified primary path and a dep-id -> verified path
	//map for deps downloaded directly - never resolves a `user_supplied` dep (§4), never gates
	//on CommunityPackReinstallDecision/CommunityPackConsentState (§43/§38), never calls
	//EmuApi.InstallMepRecipe (the coordinator owns everything downstream). §41 (PRIORITY 1):
	//allow-list loaded ONLY via Assembly.GetExecutingAssembly().GetManifestResourceStream, never
	//the on-disk file-path overload or a repo-relative path (verify_fetcher_no_filesystem_allowlist_load.sh).
	public static class CommunityPackCatalogFetcher
	{
		private const string CatalogUrl = "https://raw.githubusercontent.com/sbihaiko/MesenCE/main/docs/community-packs.json";
		private const string AllowlistResourceName = "Mesen.pack_host_allowlist.json";
		//§46: <EnhancementPackFolder>/.cache/downloads/ (ADR-0040 scratch space, safe to delete).
		private static string CacheFolder => Path.Combine(ConfigManager.EnhancementPackFolder, ".cache");
		private static string DownloadsFolder => Path.Combine(CacheFolder, "downloads");
		private static string CatalogCachePath => Path.Combine(CacheFolder, "community-packs.json");
		private static string CatalogEtagPath => Path.Combine(CacheFolder, "community-packs.etag");

		public static async Task<CommunityPackFetchResult?> FetchMatchingPackAsync()
		{
			string romSha1 = EmuApi.GetMepRomSha1();
			if(string.IsNullOrWhiteSpace(romSha1)) {
				EmuApi.WriteLogEntry("[CommunityPackFetch] no ROM sha1 available");
				return null;
			}
			string romName = EmuApi.GetRomInfo().GetRomName();

			IReadOnlyList<CommunityPackHostEntry> allowedHosts = LoadAllowlist();
			EmuApi.WriteLogEntry("[CommunityPackFetch] allow-listed hosts: " + allowedHosts.Count +
				" (" + string.Join(", ", allowedHosts.Select(h => h.Host)) + ")");
			CommunityPackCatalog? catalog = await LoadCatalogAsync(allowedHosts);
			EmuApi.WriteLogEntry("[CommunityPackFetch] catalog loaded: " + (catalog == null ? "null" : catalog.Packs?.Length + " packs"));
			CommunityPackCatalogEntry? entry = catalog == null ? null : CommunityPackCatalogMatcher.FindMatchingEntry(catalog, romSha1, romName);
			string via = "none";
			if(entry != null) {
				via = CommunityPackCatalogMatcher.Matches(entry.Rom, romSha1) ? "sha1" : "game";
			}
			EmuApi.WriteLogEntry("[CommunityPackFetch] matching entry for romSha1=" + romSha1 +
				" romName=" + romName + " via=" + via + ": " +
				(entry == null ? "none" : entry.PackId + " url=" + entry.Url + " sha256=" + entry.Sha256));
			if(entry == null) {
				return null;
			}

			string? primaryPath = await DownloadAndVerifyAsync(entry.Url, entry.Sha256, allowedHosts);
			EmuApi.WriteLogEntry("[CommunityPackFetch] primary download+verify: " + (primaryPath ?? "FAILED (see [CommunityPackDownload] lines above)"));
			if(primaryPath == null) {
				return null;
			}

			Dictionary<string, string> depPaths = await DownloadDepsAsync(entry, allowedHosts);
			return new CommunityPackFetchResult(entry, primaryPath, depPaths);
		}

		//Downloads deps with a URL+sha256 that aren't `user_supplied`; the rest are left for CommunityPackInstallCoordinator/CommunityPackDepResolver to resolve instead (§4).
		private static async Task<Dictionary<string, string>> DownloadDepsAsync(
			CommunityPackCatalogEntry entry, IReadOnlyList<CommunityPackHostEntry> allowedHosts)
		{
			Dictionary<string, string> depPaths = new();
			if(entry.Deps == null) {
				return depPaths;
			}
			foreach(CommunityPackDep dep in entry.Deps) {
				if(dep.UserSupplied == true || string.IsNullOrWhiteSpace(dep.Id) || string.IsNullOrWhiteSpace(dep.Url) || string.IsNullOrWhiteSpace(dep.Sha256)) {
					continue;
				}
				string? depPath = await DownloadAndVerifyAsync(dep.Url, dep.Sha256, allowedHosts);
				if(depPath != null) {
					depPaths[dep.Id] = depPath;
				}
			}
			return depPaths;
		}

		//§41: strictly the assembly manifest, never the filesystem.
		private static IReadOnlyList<CommunityPackHostEntry> LoadAllowlist()
		{
			using Stream? stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(AllowlistResourceName);
			return stream == null ? Array.Empty<CommunityPackHostEntry>() : CommunityPackHostAllowlist.LoadFromStream(stream);
		}

		//ETag/If-None-Match caching (§37/§41): CommunityCatalogCacheDecision is the pure decision; this does the I/O.
		//Never persists/returns a body that hasn't parsed as a real catalog - a non-JSON 200, or an explicit JSON "packs": null, degrades to null like any other failure, never an unhandled throw or a bad body cached for replay.
		private static async Task<CommunityPackCatalog?> LoadCatalogAsync(IReadOnlyList<CommunityPackHostEntry> allowedHosts)
		{
			try {
				Directory.CreateDirectory(CacheFolder);
				string? cachedBody = File.Exists(CatalogCachePath) ? await File.ReadAllTextAsync(CatalogCachePath) : null;
				string? cachedETag = File.Exists(CatalogEtagPath) ? await File.ReadAllTextAsync(CatalogEtagPath) : null;
				bool cacheUsable = CommunityCatalogCacheDecision.IsCacheUsable(cachedETag, cachedBody);

				CommunityCatalogFetchOutcome outcome = await FetchCatalogOutcomeAsync(cacheUsable ? cachedETag : null, allowedHosts);
				CommunityCatalogCacheResult resolved = CommunityCatalogCacheDecision.Resolve(outcome, cachedETag, cachedBody);
				EmuApi.WriteLogEntry("[CommunityPackFetch] catalog HTTP status=" + outcome.StatusCode + " cacheUsable=" + cacheUsable +
					" resolvedBodyLen=" + (resolved.Body?.Length ?? 0));
				CommunityPackCatalog? catalog = string.IsNullOrWhiteSpace(resolved.Body) ? null :
					(CommunityPackCatalog?)JsonSerializer.Deserialize(resolved.Body, typeof(CommunityPackCatalog), MesenSerializerContext.Default);
				if(catalog?.Packs == null) {
					EmuApi.WriteLogEntry("[CommunityPackFetch] catalog parse failed or empty (Packs==null)");
					return null;
				}
				if(resolved.ShouldWriteCache && resolved.Body != null) {
					await WriteCatalogCacheAsync(resolved.Body, outcome.ETag);
				}
				return catalog;
			} catch(Exception ex) {
				EmuApi.WriteLogEntry("[CommunityPackFetch] LoadCatalogAsync threw: " + ex);
				return null;
			}
		}

		//§50: the catalog GET goes through the same allow-list/no-redirect/size-capped primitive as the artifacts.
		private static async Task<CommunityCatalogFetchOutcome> FetchCatalogOutcomeAsync(string? ifNoneMatchETag, IReadOnlyList<CommunityPackHostEntry> allowedHosts)
		{
			CommunityPackDownloader.Response? response = await CommunityPackDownloader.GetAsync(CatalogUrl, allowedHosts, CommunityPackDownloader.MaxCatalogBytes, ifNoneMatchETag);
			if(response == null) {
				//Network failure or refused hop: same as "nothing new" - Resolve() falls back to the disk cache, or Cold.
				return new CommunityCatalogFetchOutcome(0, null, null);
			}
			string? body = response.Body == null ? null : System.Text.Encoding.UTF8.GetString(response.Body);
			return new CommunityCatalogFetchOutcome(response.StatusCode, response.ETag, body);
		}

		private static async Task WriteCatalogCacheAsync(string body, string? etag)
		{
			await File.WriteAllTextAsync(CatalogCachePath, body);
			if(etag != null) {
				await File.WriteAllTextAsync(CatalogEtagPath, etag);
			}
		}

		//Verifies SHA256 against the declared hash (an existing .cache/downloads/ copy is reused only if it still matches);
		//the GET itself is allow-list-gated per hop and size-capped by CommunityPackDownloader (§41/§50).
		//The declared hash doubles as the cache file name, so it must be exactly 64 hex chars before touching the filesystem - a catalog is network data, never a path.
		private static async Task<string?> DownloadAndVerifyAsync(
			string url, string expectedSha256, IReadOnlyList<CommunityPackHostEntry> allowedHosts)
		{
			if(string.IsNullOrWhiteSpace(url) || !IsSha256Hex(expectedSha256)) {
				EmuApi.WriteLogEntry("[CommunityPackDownload] invalid url or sha256: url=" + url + " sha256=" + expectedSha256);
				return null;
			}
			bool mutableRepoArchive = IsMutableRepoArchiveUrl(url);
			try {
				Directory.CreateDirectory(DownloadsFolder);
				string destPath = Path.Combine(DownloadsFolder, expectedSha256.ToLowerInvariant());
				//ADR-0146: a whole-repo `archive/refs/heads/<branch>.zip` (or its
				//codeload twin) is mutable, so the catalog's declared hash is a
				//validation-time snapshot, not a guarantee. Reuse whatever was last
				//fetched for it rather than re-verifying against the now-stale declared
				//hash — avoids a re-download on every load.
				if(mutableRepoArchive && File.Exists(destPath)) {
					EmuApi.WriteLogEntry("[CommunityPackDownload] cache hit (mutable repo archive): " + destPath);
					return destPath;
				}
				if(File.Exists(destPath)) {
					string cachedSha = ComputeSha256(File.ReadAllBytes(destPath));
					if(string.Equals(cachedSha, expectedSha256, StringComparison.OrdinalIgnoreCase)) {
						EmuApi.WriteLogEntry("[CommunityPackDownload] cache hit: " + destPath);
						return destPath;
					}
					EmuApi.WriteLogEntry("[CommunityPackDownload] cache file present but sha256 mismatch (cached=" + cachedSha + " expected=" + expectedSha256 + ") - re-downloading");
				}
				EmuApi.WriteLogEntry("[CommunityPackDownload] downloading url=" + url);
				CommunityPackDownloader.Response? response = await CommunityPackDownloader.GetAsync(url, allowedHosts, CommunityPackDownloader.MaxArtifactBytes);
				if(response?.Body == null) {
					EmuApi.WriteLogEntry("[CommunityPackDownload] GetAsync returned null body (host not allowed, redirect rejected, size cap, or network error)");
					return null;
				}
				string actualSha256 = ComputeSha256(response.Body);
				if(!string.Equals(actualSha256, expectedSha256, StringComparison.OrdinalIgnoreCase)) {
					if(mutableRepoArchive) {
						//Optimistic install per ADR-0146: the artifact is the repo's current
						//head, which legitimately differs from the recorded snapshot. Content
						//still bounded by the host allow-list; a wrong pack self-heals via the
						//ADR-0145 health signal / tile fall-through.
						EmuApi.WriteLogEntry("[CommunityPackDownload] sha256 mismatch on mutable repo archive (expected=" + expectedSha256 + " actual=" + actualSha256 + ") - installing optimistically per ADR-0146");
					} else {
						EmuApi.WriteLogEntry("[CommunityPackDownload] sha256 MISMATCH: expected=" + expectedSha256 + " actual=" + actualSha256 + " bytes=" + response.Body.Length);
						return null;
					}
				}
				await File.WriteAllBytesAsync(destPath, response.Body);
				EmuApi.WriteLogEntry("[CommunityPackDownload] downloaded+verified, wrote " + destPath);
				return destPath;
			} catch(Exception ex) {
				EmuApi.WriteLogEntry("[CommunityPackDownload] threw: " + ex);
				return null;
			}
		}

		//ADR-0146: a whole-repo `archive/refs/heads/<branch>.zip` (or its codeload
		//twin `codeload.github.com/<owner>/<repo>/zip/refs/heads/<branch>`) tracks a
		//moving branch head, so the artifact legitimately changes between loads and
		//the catalog's declared sha256 is only a validation-time snapshot. Commit
		//(`archive/<sha>`) and tag (`refs/tags/`) archives are immutable and keep the
		//strict check. The URL is catalog network data (never a path), so substring
		//detection is safe here.
		private static bool IsMutableRepoArchiveUrl(string? url) =>
			url != null && (url.Contains("/archive/refs/heads/", StringComparison.OrdinalIgnoreCase)
				|| url.Contains("/zip/refs/heads/", StringComparison.OrdinalIgnoreCase));

		private static bool IsSha256Hex(string? value) =>
			value != null && value.Length == 64 && value.All(Uri.IsHexDigit);

		private static string ComputeSha256(byte[] data)
		{
			using SHA256 sha256 = SHA256.Create();
			return BitConverter.ToString(sha256.ComputeHash(data)).Replace("-", "");
		}
	}

	//Shared shape with CommunityPackInstallCoordinator (T2): matched entry, verified primary path, and a dep-id -> path map covering only deps downloaded directly (never `user_supplied`).
	public sealed record CommunityPackFetchResult(
		CommunityPackCatalogEntry Entry,
		string PrimaryPackPath,
		IReadOnlyDictionary<string, string> ResolvedDepPaths
	);
}

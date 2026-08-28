using Mesen.Config;
using Mesen.Interop;
using Mesen.Logic;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading.Tasks;

namespace Mesen.Services
{
	//Network-facing half of F6.4b-2 (ADR-0138 §37/§38/§41/§42/§46): fetches the MEI v1.1 catalog,
	//matches the loaded ROM by No-Intro sha1 (EmuApi.GetMepRomSha1), downloads+verifies the
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
				return null;
			}

			CommunityPackCatalog? catalog = await LoadCatalogAsync();
			CommunityPackCatalogEntry? entry = catalog == null ? null : FindMatchingEntry(catalog, romSha1);
			if(entry == null) {
				return null;
			}

			IReadOnlyList<CommunityPackHostEntry> allowedHosts = LoadAllowlist();
			string? primaryPath = await DownloadAndVerifyAsync(entry.Url, entry.Sha256, allowedHosts);
			if(primaryPath == null) {
				return null;
			}

			Dictionary<string, string> depPaths = await DownloadDepsAsync(entry, allowedHosts);
			return new CommunityPackFetchResult(entry, primaryPath, depPaths);
		}

		private static CommunityPackCatalogEntry? FindMatchingEntry(CommunityPackCatalog catalog, string romSha1)
		{
			foreach(CommunityPackCatalogEntry entry in catalog.Packs) {
				if(!string.IsNullOrWhiteSpace(entry.Rom?.Sha1) &&
					string.Equals(entry.Rom!.Sha1, romSha1, StringComparison.OrdinalIgnoreCase)) {
					return entry;
				}
			}
			return null;
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
		private static async Task<CommunityPackCatalog?> LoadCatalogAsync()
		{
			try {
				Directory.CreateDirectory(CacheFolder);
				string? cachedBody = File.Exists(CatalogCachePath) ? await File.ReadAllTextAsync(CatalogCachePath) : null;
				string? cachedETag = File.Exists(CatalogEtagPath) ? await File.ReadAllTextAsync(CatalogEtagPath) : null;
				bool cacheUsable = CommunityCatalogCacheDecision.IsCacheUsable(cachedETag, cachedBody);

				CommunityCatalogFetchOutcome outcome = await FetchCatalogOutcomeAsync(cacheUsable ? cachedETag : null);
				CommunityCatalogCacheResult resolved = CommunityCatalogCacheDecision.Resolve(outcome, cachedETag, cachedBody);
				CommunityPackCatalog? catalog = string.IsNullOrWhiteSpace(resolved.Body) ? null :
					(CommunityPackCatalog?)JsonSerializer.Deserialize(resolved.Body, typeof(CommunityPackCatalog), MesenSerializerContext.Default);
				if(catalog?.Packs == null) {
					return null;
				}
				if(resolved.ShouldWriteCache) {
					await WriteCatalogCacheAsync(resolved.Body, outcome.ETag);
				}
				return catalog;
			} catch(Exception) {
				return null;
			}
		}

		private static async Task<CommunityCatalogFetchOutcome> FetchCatalogOutcomeAsync(string? ifNoneMatchETag)
		{
			try {
				using HttpClient client = new();
				using HttpRequestMessage request = new(HttpMethod.Get, CatalogUrl);
				if(ifNoneMatchETag != null) {
					request.Headers.TryAddWithoutValidation("If-None-Match", ifNoneMatchETag);
				}
				using HttpResponseMessage response = await client.SendAsync(request);
				string? etag = response.Headers.ETag?.Tag;
				string? body = response.StatusCode == HttpStatusCode.OK ? await response.Content.ReadAsStringAsync() : null;
				return new CommunityCatalogFetchOutcome((int)response.StatusCode, etag, body);
			} catch(Exception) {
				//Network failure: same as "nothing new" - Resolve() falls back to the disk cache, or Cold.
				return new CommunityCatalogFetchOutcome(0, null, null);
			}
		}

		private static async Task WriteCatalogCacheAsync(string body, string? etag)
		{
			await File.WriteAllTextAsync(CatalogCachePath, body);
			if(etag != null) {
				await File.WriteAllTextAsync(CatalogEtagPath, etag);
			}
		}

		//Gates through the host allow-list (§41, MatchHost), verifies SHA256 against the declared hash (an existing .cache/downloads/ copy is reused only if it still matches).
		//The declared hash doubles as the cache file name, so it must be exactly 64 hex chars before touching the filesystem - a catalog is network data, never a path.
		private static async Task<string?> DownloadAndVerifyAsync(
			string url, string expectedSha256, IReadOnlyList<CommunityPackHostEntry> allowedHosts)
		{
			if(string.IsNullOrWhiteSpace(url) || !IsSha256Hex(expectedSha256)) {
				return null;
			}
			if(CommunityPackHostAllowlist.MatchHost(url, allowedHosts) == null) {
				return null;
			}
			try {
				Directory.CreateDirectory(DownloadsFolder);
				string destPath = Path.Combine(DownloadsFolder, expectedSha256.ToLowerInvariant());
				if(File.Exists(destPath) && string.Equals(ComputeSha256(File.ReadAllBytes(destPath)), expectedSha256, StringComparison.OrdinalIgnoreCase)) {
					return destPath;
				}
				using HttpClient client = new();
				byte[] data = await client.GetByteArrayAsync(url);
				if(!string.Equals(ComputeSha256(data), expectedSha256, StringComparison.OrdinalIgnoreCase)) {
					return null;
				}
				await File.WriteAllBytesAsync(destPath, data);
				return destPath;
			} catch(Exception) {
				return null;
			}
		}

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

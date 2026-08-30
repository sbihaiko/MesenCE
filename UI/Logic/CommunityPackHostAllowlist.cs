using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Mesen.Logic
{
	//Host-free client-side counterpart to scripts/fetch_pack.py:match_host
	//(ADR-0138 SS37, F6.4b). scripts/pack_host_allowlist.json is the single
	//source of truth for which hosts a community pack's primary artifact may
	//be downloaded from - the same file backs both the
	//community-pack-validate.yml CI workflow (via fetch_pack.py) and this
	//client. This class only ever reads that JSON at runtime: there is no
	//second, hand-maintained copy of the host list anywhere in C#.
	//
	//Kept free of Avalonia/EmuApi (BCL + System.Text.Json only) so it can be
	//dual-compiled into UI.Tests (see UI.Tests/UI.Tests.csproj) and unit
	//tested without the native MesenCore library, per the UI/Logic firewall
	//(UI/AGENTS.md).
	public static class CommunityPackHostAllowlist
	{
		//Repo-relative path to the shared allow-list, mirroring
		//fetch_pack.py's DEFAULT_ALLOWLIST constant.
		public const string RepoRelativePath = "scripts/pack_host_allowlist.json";

		//Parses the allow-list JSON body into entries. Pure: no I/O. Mirrors
		//load_allowlist()'s shape in fetch_pack.py - only the top-level
		//"hosts" array is read; "_comment" is ignored.
		public static IReadOnlyList<CommunityPackHostEntry> Parse(string json)
		{
			CommunityPackHostAllowlistFile? file = JsonSerializer.Deserialize(
				json,
				CommunityPackHostAllowlistSerializerContext.Default.CommunityPackHostAllowlistFile
			);
			return file?.Hosts ?? new List<CommunityPackHostEntry>();
		}

		//Reads and parses the allow-list from an already-open stream. The
		//caller owns the stream's lifetime (it is left open here).
		public static IReadOnlyList<CommunityPackHostEntry> LoadFromStream(Stream stream)
		{
			using StreamReader reader = new(stream, leaveOpen: true);
			return Parse(reader.ReadToEnd());
		}

		//Reads and parses the allow-list from a file path (typically
		//RepoRelativePath, resolved by the caller against wherever the repo
		//checkout / packaged app locates its scripts/ tree).
		public static IReadOnlyList<CommunityPackHostEntry> LoadFromFile(string path)
		{
			using FileStream stream = File.OpenRead(path);
			return LoadFromStream(stream);
		}

		//Mirrors scripts/fetch_pack.py:match_host exactly:
		//  1. HTTPS-only scheme check (Python lower-cases the scheme before
		//     comparing, so this does too);
		//  2. host match: exact netloc equality against "host" (no
		//     case-folding, no port defaulting - a byte-for-byte match of
		//     the URL's authority component, same as urlparse().netloc)
		//     OR netloc.EndsWith("host_ends_with") when that field is set
		//     (MediaFire CDN hops are downloadN.mediafire.com);
		//  3. when the entry declares "path_contains_any", a substring gate
		//     over the URL's path component alone (query/fragment excluded),
		//     same as `any(s in parsed.path for s in substrings)`.
		//Returns the first matching entry, or null when none match - same
		//contract as the Python function returning None.
		public static CommunityPackHostEntry? MatchHost(string url, IReadOnlyList<CommunityPackHostEntry> hosts)
		{
			(string scheme, string netloc, string path) = SplitUrl(url);
			if(scheme != "https") {
				return null;
			}

			foreach(CommunityPackHostEntry entry in hosts) {
				bool hostMatch = !string.IsNullOrEmpty(entry.Host) && netloc == entry.Host;
				bool suffixMatch = !string.IsNullOrEmpty(entry.HostEndsWith) &&
					netloc.EndsWith(entry.HostEndsWith, StringComparison.Ordinal);
				if(!hostMatch && !suffixMatch) {
					continue;
				}
				if(entry.PathContainsAny != null && entry.PathContainsAny.Count > 0 &&
					!entry.PathContainsAny.Any(s => path.Contains(s, StringComparison.Ordinal))) {
					continue;
				}
				return entry;
			}
			return null;
		}

		//Minimal, literal mirror of urllib.parse.urlparse's scheme/netloc/path
		//split for the "scheme://netloc/path[?query][#fragment]" shape this
		//matcher cares about - deliberately not System.Uri, whose host
		//normalization (lower-casing, IDN handling, trailing-dot removal)
		//would silently diverge from Python's raw-string netloc comparison.
		private static (string Scheme, string Netloc, string Path) SplitUrl(string url)
		{
			int schemeEnd = url.IndexOf("://", StringComparison.Ordinal);
			if(schemeEnd < 0) {
				return ("", "", "");
			}

			string scheme = url.Substring(0, schemeEnd).ToLowerInvariant();
			string rest = url.Substring(schemeEnd + 3);
			int pathStart = rest.IndexOfAny(PathBoundaryChars);
			string netloc = pathStart < 0 ? rest : rest.Substring(0, pathStart);
			string afterNetloc = pathStart < 0 ? "" : rest.Substring(pathStart);
			int queryStart = afterNetloc.IndexOfAny(QueryBoundaryChars);
			string path = queryStart < 0 ? afterNetloc : afterNetloc.Substring(0, queryStart);
			return (scheme, netloc, path);
		}

		private static readonly char[] PathBoundaryChars = { '/', '?', '#' };
		private static readonly char[] QueryBoundaryChars = { '?', '#' };

		//Internal (not private): the source-gen context below,
		//CommunityPackHostAllowlistSerializerContext, needs to reference this
		//type from outside the class to generate its (de)serializer - a
		//private nested type is invisible to the [JsonSerializable] attribute
		//on a sibling top-level type.
		internal sealed class CommunityPackHostAllowlistFile
		{
			[JsonPropertyName("hosts")]
			public List<CommunityPackHostEntry> Hosts { get; set; } = new();
		}
	}

	//Source-generated (de)serialization context for the allow-list DTOs.
	//Required because UI/UI.csproj sets JsonSerializerIsReflectionEnabledByDefault=false
	//and IsAotCompatible=true: a reflection-based JsonSerializer.Deserialize<T>() call
	//throws InvalidOperationException at runtime in the shipped app (verified against
	//that exact property). Every other JSON deserialize in UI/ already goes through a
	//source-generated context (see UI/Utilities/JsonHelper.cs's MesenSerializerContext /
	//MesenCamelCaseSerializerContext) - this follows the same convention, kept local to
	//this host-free file so UI/Logic stays free of a dependency on JsonHelper.cs's
	//Avalonia-adjacent siblings. Explicit [JsonPropertyName] on every DTO property means
	//the default (PascalCase-preserving) naming policy below never needs to change.
	[JsonSerializable(typeof(CommunityPackHostAllowlist.CommunityPackHostAllowlistFile))]
	internal sealed partial class CommunityPackHostAllowlistSerializerContext : JsonSerializerContext { }

	//One entry of scripts/pack_host_allowlist.json's "hosts" array.
	public sealed class CommunityPackHostEntry
	{
		[JsonPropertyName("host")]
		public string Host { get; init; } = "";

		//Optional suffix match on the URL netloc (e.g. ".mediafire.com" for
		//downloadN.mediafire.com CDN hops). Empty means unused. Mirrors
		//fetch_pack.py's host_ends_with field.
		[JsonPropertyName("host_ends_with")]
		public string HostEndsWith { get; init; } = "";

		//Substring gate over the URL path; null/empty means "no gate - any
		//path under this host is allowed" (e.g. codeload.github.com).
		[JsonPropertyName("path_contains_any")]
		public List<string>? PathContainsAny { get; init; }

		//"direct" (plain HTTPS GET), "google-drive" (two-step confirm-token
		//dance), or "mediafire" (share page then CDN hop) - see fetch_pack.py.
		[JsonPropertyName("kind")]
		public string Kind { get; init; } = "";
	}
}

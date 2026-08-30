using Mesen.Interop;
using Mesen.Logic;
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading.Tasks;

namespace Mesen.Services
{
	//Client-side download trust contract (ADR-0138 §50), the one HTTP GET primitive every
	//community-pack request in UI/Services goes through. Mirrors scripts/fetch_pack.py's
	//open_validated on the controls a client can apply: redirects are never followed
	//automatically - every hop is re-checked against the host allow-list (MatchHost, https
	//only) with the same 5-hop cap - and the body is capped in bytes before it is buffered,
	//so a hostile redirect from an allow-listed URL can neither leave the allow-list nor
	//exhaust memory. DNS/private-range checks stay CI-only: the allow-listed hosts are
	//public CDNs, and a client cannot pin DNS the way the runner does.
	//
	//A `kind: "google-drive"` entry (MEI-v1 §2.4) does NOT go through the plain GET loop:
	//the share URL is mapped to the two-step dance (uc?export=download, then the
	//drive.usercontent.google.com confirm hop when the first response is the virus-scan
	//HTML page) - a plain GET on a large Drive file returns that HTML, so the sha256
	//verification would never match. Both hops are still allow-listed and capped.
	public static class CommunityPackDownloader
	{
		public const int MaxRedirects = 5;
		//Same ceiling as the CI validator (community-pack-validate.yml, 300MB).
		public const long MaxArtifactBytes = 300L * 1024 * 1024;
		public const long MaxCatalogBytes = 16L * 1024 * 1024;

		public sealed record Response(int StatusCode, string? ETag, byte[]? Body);

		//Returns null when the entry is outside the allow-list, the redirect chain is too
		//long, the body exceeds maxBytes, or any network/IO error occurs - never throws.
		//A google-drive-kind URL is downloaded via the two-step dance; everything else via
		//the redirect-checked GET loop.
		public static async Task<Response?> GetAsync(string url, IReadOnlyList<CommunityPackHostEntry> allowedHosts, long maxBytes, string? ifNoneMatchETag = null)
		{
			CommunityPackHostEntry? matched = CommunityPackHostAllowlist.MatchHost(url, allowedHosts);
			if(matched == null) {
				EmuApi.WriteLogEntry("[CommunityPackDownloader] REJECTED (host not allow-listed): " + url);
				return null;
			}
			return string.Equals(matched.Kind, "google-drive", StringComparison.OrdinalIgnoreCase)
				? await GetGoogleDriveAsync(url, allowedHosts, maxBytes, ifNoneMatchETag)
				: await GetDirectAsync(url, allowedHosts, maxBytes, ifNoneMatchETag);
		}

		private static async Task<Response?> GetDirectAsync(string url, IReadOnlyList<CommunityPackHostEntry> allowedHosts, long maxBytes, string? ifNoneMatchETag)
		{
			FetchResult? result = await FetchAsync(url, allowedHosts, maxBytes, ifNoneMatchETag);
			return result == null ? null : new Response(result.StatusCode, result.ETag, result.Body);
		}

		//Mirror of scripts/fetch_pack.py::fetch_google_drive: try the canonical
		//uc?export=download first; when the response is the large-file virus-scan HTML
		//page, one more hop to drive.usercontent.google.com with a confirm token fetches
		//the real bytes. Small files come straight back from the first request.
		private static async Task<Response?> GetGoogleDriveAsync(string url, IReadOnlyList<CommunityPackHostEntry> allowedHosts, long maxBytes, string? ifNoneMatchETag)
		{
			string? fileId = CommunityPackDrive.ExtractFileId(url);
			if(fileId == null) {
				EmuApi.WriteLogEntry("[CommunityPackDownloader] google-drive URL has no file id: " + url);
				return null;
			}
			string firstUrl = "https://drive.google.com/uc?export=download&id=" + fileId;
			FetchResult? first = await FetchAsync(firstUrl, allowedHosts, maxBytes, ifNoneMatchETag);
			if(first == null) {
				return null;
			}
			string contentType = first.ContentType ?? "";
			if(contentType.Contains("text/html", StringComparison.OrdinalIgnoreCase)) {
				string secondUrl = "https://drive.usercontent.google.com/download?id=" + fileId + "&export=download&confirm=t";
				FetchResult? second = await FetchAsync(secondUrl, allowedHosts, maxBytes, ifNoneMatchETag);
				if(second == null) {
					return null;
				}
				return new Response(second.StatusCode, second.ETag, second.Body);
			}
			return new Response(first.StatusCode, first.ETag, first.Body);
		}

		private sealed record FetchResult(int StatusCode, string? ContentType, string? ETag, byte[]? Body);

		private static async Task<FetchResult?> FetchAsync(string url, IReadOnlyList<CommunityPackHostEntry> allowedHosts, long maxBytes, string? ifNoneMatchETag)
		{
			try {
				using HttpClientHandler handler = new() { AllowAutoRedirect = false };
				using HttpClient client = new(handler) { MaxResponseContentBufferSize = maxBytes };
				string current = url;
				for(int hop = 0; hop <= MaxRedirects; hop++) {
					CommunityPackHostEntry? matched = CommunityPackHostAllowlist.MatchHost(current, allowedHosts);
					if(matched == null) {
						EmuApi.WriteLogEntry("[CommunityPackDownloader] hop " + hop + " REJECTED (host not allow-listed): " + current);
						return null;
					}
					using HttpRequestMessage request = new(HttpMethod.Get, current);
					if(ifNoneMatchETag != null) {
						request.Headers.TryAddWithoutValidation("If-None-Match", ifNoneMatchETag);
					}
					using HttpResponseMessage response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
					int status = (int)response.StatusCode;
					EmuApi.WriteLogEntry("[CommunityPackDownloader] hop " + hop + " GET " + current + " -> " + status);
					if(status is >= 300 and < 400) {
						Uri? location = response.Headers.Location;
						if(location == null) {
							EmuApi.WriteLogEntry("[CommunityPackDownloader] redirect with no Location header");
							return null;
						}
						current = location.IsAbsoluteUri ? location.ToString() : new Uri(new Uri(current), location).ToString();
						EmuApi.WriteLogEntry("[CommunityPackDownloader] redirect -> " + current);
						continue;
					}
					if(response.Content.Headers.ContentLength is long declared && declared > maxBytes) {
						EmuApi.WriteLogEntry("[CommunityPackDownloader] declared Content-Length " + declared + " exceeds cap " + maxBytes);
						return null;
					}
					byte[]? body = status == (int)HttpStatusCode.OK ? await ReadCappedAsync(response, maxBytes) : null;
					if(status == (int)HttpStatusCode.OK && body == null) {
						EmuApi.WriteLogEntry("[CommunityPackDownloader] body read failed or exceeded cap mid-transfer");
						return null;
					}
					EmuApi.WriteLogEntry("[CommunityPackDownloader] final response status=" + status + " bodyBytes=" + (body?.Length.ToString() ?? "null"));
					return new FetchResult(status, response.Content.Headers.ContentType?.MediaType, response.Headers.ETag?.Tag, body);
				}
				EmuApi.WriteLogEntry("[CommunityPackDownloader] too many redirects (>" + MaxRedirects + ")");
				return null; //too many redirects
			} catch(Exception ex) {
				EmuApi.WriteLogEntry("[CommunityPackDownloader] GetAsync threw: " + ex);
				return null;
			}
		}

		private static async Task<byte[]?> ReadCappedAsync(HttpResponseMessage response, long maxBytes)
		{
			using Stream stream = await response.Content.ReadAsStreamAsync();
			using MemoryStream buffer = new();
			byte[] chunk = new byte[81920];
			int read;
			while((read = await stream.ReadAsync(chunk, 0, chunk.Length)) > 0) {
				if(buffer.Length + read > maxBytes) {
					return null;
				}
				buffer.Write(chunk, 0, read);
			}
			return buffer.ToArray();
		}
	}
}

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
	public static class CommunityPackDownloader
	{
		public const int MaxRedirects = 5;
		//Same ceiling as the CI validator (community-pack-validate.yml, 300MB).
		public const long MaxArtifactBytes = 300L * 1024 * 1024;
		public const long MaxCatalogBytes = 16L * 1024 * 1024;

		public sealed record Response(int StatusCode, string? ETag, byte[]? Body);

		//Returns null when a hop is outside the allow-list, the redirect chain is too long,
		//the body exceeds maxBytes, or any network/IO error occurs - never throws.
		public static async Task<Response?> GetAsync(string url, IReadOnlyList<CommunityPackHostEntry> allowedHosts, long maxBytes, string? ifNoneMatchETag = null)
		{
			try {
				using HttpClientHandler handler = new() { AllowAutoRedirect = false };
				using HttpClient client = new(handler) { MaxResponseContentBufferSize = maxBytes };
				string current = url;
				for(int hop = 0; hop <= MaxRedirects; hop++) {
					if(CommunityPackHostAllowlist.MatchHost(current, allowedHosts) == null) {
						return null;
					}
					using HttpRequestMessage request = new(HttpMethod.Get, current);
					if(ifNoneMatchETag != null) {
						request.Headers.TryAddWithoutValidation("If-None-Match", ifNoneMatchETag);
					}
					using HttpResponseMessage response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
					int status = (int)response.StatusCode;
					if(status is >= 300 and < 400) {
						Uri? location = response.Headers.Location;
						if(location == null) {
							return null;
						}
						current = location.IsAbsoluteUri ? location.ToString() : new Uri(new Uri(current), location).ToString();
						continue;
					}
					if(response.Content.Headers.ContentLength is long declared && declared > maxBytes) {
						return null;
					}
					byte[]? body = status == (int)HttpStatusCode.OK ? await ReadCappedAsync(response, maxBytes) : null;
					if(status == (int)HttpStatusCode.OK && body == null) {
						return null;
					}
					return new Response(status, response.Headers.ETag?.Tag, body);
				}
				return null; //too many redirects
			} catch(Exception) {
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

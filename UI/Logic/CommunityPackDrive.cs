using System;
using System.Text.RegularExpressions;

namespace Mesen.Logic
{
	//Host-free parsing of Google Drive share URLs (MEI-v1 §2.4 allow-list
	//`kind: "google-drive"`): the client must map the catalog's drive URL to
	//the two-step download dance instead of a plain GET (which returns the
	//virus-scan HTML page for large files, so the sha256 never matches).
	//BCL only, so this file dual-compiles into UI.Tests. Mirrors
	//scripts/fetch_pack.py::extract_drive_id exactly: the canonical `/d/<id>`
	//path segment wins, otherwise the `?id=` query parameter.
	public static class CommunityPackDrive
	{
		private static readonly Regex FileIdPathPattern = new("/d/([a-zA-Z0-9_-]+)", RegexOptions.CultureInvariant);

		//The file id for a Google Drive share URL, or null when the URL is not
		//a file share (folders, invalid links, non-Drive hosts). An id is
		//alphanumeric/underscore/dash only, so no url-decoding is needed on the
		//path; the query fallback is decoded the way parse_qs would ('+' = space).
		public static string? ExtractFileId(string url)
		{
			if(string.IsNullOrEmpty(url)) {
				return null;
			}
			//Strip query and fragment before the path match, so an 'id' query
			//value can never be confused with a '/d/<id>' path segment.
			int queryIdx = url.IndexOf('?');
			int hashIdx = url.IndexOf('#');
			int cut = url.Length;
			if(queryIdx >= 0) {
				cut = Math.Min(cut, queryIdx);
			}
			if(hashIdx >= 0) {
				cut = Math.Min(cut, hashIdx);
			}
			string path = url.Substring(0, cut);
			Match m = FileIdPathPattern.Match(path);
			if(m.Success) {
				return m.Groups[1].Value;
			}

			string query = queryIdx < 0 ? "" : url.Substring(queryIdx + 1);
			foreach(string pair in query.Split('&')) {
				if(pair.Length == 0) {
					continue;
				}
				int eq = pair.IndexOf('=');
				string key = eq < 0 ? pair : pair.Substring(0, eq);
				if(!string.Equals(UrlDecode(key), "id", StringComparison.OrdinalIgnoreCase)) {
					continue;
				}
				return eq < 0 ? "" : UrlDecode(pair.Substring(eq + 1));
			}
			return null;
		}

		private static string UrlDecode(string s)
		{
			//'+' means space in a query string; Uri.UnescapeDataString leaves it.
			return Uri.UnescapeDataString(s.Replace("+", "%20"));
		}
	}
}

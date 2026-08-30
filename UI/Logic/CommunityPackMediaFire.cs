using System;
using System.Net;
using System.Text.RegularExpressions;

namespace Mesen.Logic
{
	//Host-free parsing of a MediaFire share page (allow-list kind
	//"mediafire"): the /file/ URL is an HTML page, and the real zip is on
	//downloadN.mediafire.com. Mirrors scripts/fetch_pack.py::
	//extract_mediafire_download_url. BCL only; dual-compiled into UI.Tests.
	public static class CommunityPackMediaFire
	{
		private static readonly Regex DownloadHref = new(
			"href=[\"'](https://download\\d+\\.mediafire\\.com/[^\"'<>]+)[\"']",
			RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

		public static string? ExtractDownloadUrl(string html)
		{
			if(string.IsNullOrEmpty(html)) {
				return null;
			}
			Match m = DownloadHref.Match(html);
			return m.Success ? WebUtility.HtmlDecode(m.Groups[1].Value) : null;
		}
	}
}

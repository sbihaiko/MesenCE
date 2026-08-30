namespace Mesen.Logic
{
	//Host-free HTTP status helpers for CommunityPackDownloader (ADR-0138
	//§50). The downloader follows a hop only when it is a real redirect
	//(301/302/303/307/308). HTTP 304 Not Modified is not a redirect - it
	//is the catalog cache-reuse status CommunityCatalogCacheDecision
	//already models - so treating the whole 3xx class as "follow Location"
	//makes a 304 look like "redirect with no Location" and collapses it
	//into a network failure. BCL only; dual-compiled into UI.Tests.
	public static class CommunityPackHttpStatus
	{
		public static bool IsFollowableRedirect(int statusCode) =>
			statusCode is 301 or 302 or 303 or 307 or 308;
	}
}

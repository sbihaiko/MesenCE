using Mesen.Config;
using System.IO;

namespace Mesen.Services
{
	//The one place that spells out the community-pack scratch roots under
	//<EnhancementPackFolder> (ADR-0040 §.cache convention, ADR-0138 §46):
	//`.cache/` holds the catalog copy, its ETag and the ADR-0147 install
	//registry; `.cache/downloads/` holds verified artifacts (and user-dropped
	//deps) keyed by sha256. Everything under it is safe to delete.
	public static class CommunityPackPaths
	{
		public static string CacheRoot => Path.Combine(ConfigManager.EnhancementPackFolder, ".cache");
		public static string DownloadsFolder => Path.Combine(CacheRoot, "downloads");
	}
}

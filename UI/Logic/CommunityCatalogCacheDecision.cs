namespace Mesen.Logic
{
	//Pure decision logic for the MEP catalog's HTTP ETag cache (ADR-0138
	//SS37, F6.4b): docs/community-packs.json is fetched with
	//If-None-Match when a usable cached ETag exists, and this class turns
	//one round trip's outcome (plus whatever was already on disk) into
	//"which body is authoritative" and "does the on-disk cache need
	//rewriting". No HTTP, no file I/O happens here - the caller (the
	//network-facing service, not UI/Logic) performs the actual GET and
	//reads/writes the cache file under the MEP ".cache" convention.
	//
	//Kept free of Avalonia/EmuApi (BCL only) so it can be dual-compiled into
	//UI.Tests (see UI.Tests/UI.Tests.csproj) and unit tested without the
	//native MesenCore library, per the UI/Logic firewall (UI/AGENTS.md).
	public static class CommunityCatalogCacheDecision
	{
		//Whether an on-disk cache entry is usable for a conditional
		//(If-None-Match) request. A cache is usable only when it carries
		//BOTH a non-empty ETag and a non-empty body - a missing file, an
		//empty/whitespace ETag, or a body that failed to read/parse are all
		//treated identically to "no cache at all": cold. The caller checks
		//this BEFORE issuing the HTTP request, to decide whether to send
		//If-None-Match at all.
		public static bool IsCacheUsable(string? cachedETag, string? cachedBody)
		{
			return !string.IsNullOrWhiteSpace(cachedETag) && !string.IsNullOrWhiteSpace(cachedBody);
		}

		//Resolves the body to use, and whether the on-disk cache must be
		//(re)written, from one HTTP round trip's outcome plus whatever was
		//already on disk.
		//  - 200 with a body: Fresh - the new body wins and must be persisted.
		//  - 304: Reused when the disk cache was usable (the conditional
		//    request that produced this 304 could only have been sent
		//    because a usable cache existed); otherwise Cold - a 304 over a
		//    cache we don't actually hold is a server/proxy anomaly, not a
		//    normal reuse, so nothing is trusted.
		//  - anything else (network/server error, or a 200 with no body):
		//    falls back to the disk cache when it is usable, otherwise Cold
		//    with no body to offer the caller.
		public static CommunityCatalogCacheResult Resolve(
			CommunityCatalogFetchOutcome outcome, string? cachedETag, string? cachedBody)
		{
			bool cacheUsable = IsCacheUsable(cachedETag, cachedBody);

			//Same body test as IsCacheUsable: a 200 whose body is empty/whitespace
			//(HttpContent yields "" for a zero-length response, never null) is
			//"a 200 with no body" and must not overwrite a usable cache.
			if(outcome.StatusCode == 200 && !string.IsNullOrWhiteSpace(outcome.Body)) {
				return new CommunityCatalogCacheResult(CommunityCatalogCacheVerdict.Fresh, outcome.Body, true);
			}

			if(outcome.StatusCode == 304 && cacheUsable) {
				return new CommunityCatalogCacheResult(CommunityCatalogCacheVerdict.Reused, cachedBody!, false);
			}

			if(outcome.StatusCode != 304 && cacheUsable) {
				return new CommunityCatalogCacheResult(CommunityCatalogCacheVerdict.Reused, cachedBody!, false);
			}

			return new CommunityCatalogCacheResult(CommunityCatalogCacheVerdict.Cold, "", false);
		}
	}

	//Fresh: a new 200 body was fetched and must be written to the cache.
	//Reused: the server said 304 (or errored) and a usable cached body
	//stands in for it, unchanged on disk.
	//Cold: no usable cache existed and no fresh body was obtained either -
	//callers have nothing to show and nothing to write.
	public enum CommunityCatalogCacheVerdict
	{
		Fresh,
		Reused,
		Cold
	}

	//One HTTP round trip's outcome, as reported by the caller after
	//actually performing the GET. ETag is the response's new ETag header
	//(only meaningful on a 200; unused by this decision but carried through
	//for the caller to persist alongside Body).
	public readonly record struct CommunityCatalogFetchOutcome(int StatusCode, string? ETag, string? Body);

	//The resolved verdict: which Body is authoritative, and whether the
	//caller must (re)write the on-disk cache file.
	public readonly record struct CommunityCatalogCacheResult(
		CommunityCatalogCacheVerdict Verdict, string Body, bool ShouldWriteCache);
}

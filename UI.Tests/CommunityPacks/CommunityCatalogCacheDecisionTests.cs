using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	// F6.4b (ADR-0138 SS37): coverage for the pure ETag-cache decision that
	// backs the community-packs.json catalog fetch. No HTTP/file I/O here -
	// every case feeds a CommunityCatalogFetchOutcome plus a cached
	// ETag/body pair straight into CommunityCatalogCacheDecision.
	public class CommunityCatalogCacheDecisionTests
	{
		[Fact]
		public void IsCacheUsable_BothEtagAndBodyPresent_ReturnsTrue()
		{
			Assert.True(CommunityCatalogCacheDecision.IsCacheUsable("\"abc123\"", "{\"packs\":[]}"));
		}

		[Theory]
		[InlineData(null, "{\"packs\":[]}")]
		[InlineData("", "{\"packs\":[]}")]
		[InlineData("   ", "{\"packs\":[]}")]
		[InlineData("\"abc123\"", null)]
		[InlineData("\"abc123\"", "")]
		[InlineData(null, null)]
		public void IsCacheUsable_MissingOrCorruptEtagOrBody_ReturnsFalse(string? etag, string? body)
		{
			Assert.False(CommunityCatalogCacheDecision.IsCacheUsable(etag, body));
		}

		[Fact]
		public void Resolve_Fresh200WithBody_ReturnsFreshAndRequestsWrite()
		{
			CommunityCatalogFetchOutcome outcome = new(200, "\"new-etag\"", "{\"packs\":[{\"id\":1}]}");

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(outcome, null, null);

			Assert.Equal(CommunityCatalogCacheVerdict.Fresh, result.Verdict);
			Assert.Equal("{\"packs\":[{\"id\":1}]}", result.Body);
			Assert.True(result.ShouldWriteCache);
		}

		[Fact]
		public void Resolve_Fresh200_OverwritesAPreviouslyUsableCache()
		{
			// A 200 always wins over whatever was cached before, even when
			// the old cache was itself perfectly usable.
			CommunityCatalogFetchOutcome outcome = new(200, "\"new-etag\"", "{\"packs\":[{\"id\":2}]}");

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(
				outcome, "\"old-etag\"", "{\"packs\":[{\"id\":1}]}");

			Assert.Equal(CommunityCatalogCacheVerdict.Fresh, result.Verdict);
			Assert.Equal("{\"packs\":[{\"id\":2}]}", result.Body);
			Assert.True(result.ShouldWriteCache);
		}

		[Fact]
		public void Resolve_304NotModifiedWithUsableCache_ReturnsReusedCachedBodyNoWrite()
		{
			CommunityCatalogFetchOutcome outcome = new(304, null, null);

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(
				outcome, "\"old-etag\"", "{\"packs\":[{\"id\":1}]}");

			Assert.Equal(CommunityCatalogCacheVerdict.Reused, result.Verdict);
			Assert.Equal("{\"packs\":[{\"id\":1}]}", result.Body);
			Assert.False(result.ShouldWriteCache);
		}

		[Fact]
		public void Resolve_304NotModifiedWithoutUsableCache_TreatedAsCold()
		{
			// A 304 could only be a normal response to a conditional request
			// we actually sent - which requires a usable cache. A 304 arriving
			// over no/corrupt cache is an anomaly, not trusted as a reuse.
			CommunityCatalogFetchOutcome outcome = new(304, null, null);

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(outcome, null, null);

			Assert.Equal(CommunityCatalogCacheVerdict.Cold, result.Verdict);
			Assert.Equal("", result.Body);
			Assert.False(result.ShouldWriteCache);
		}

		[Fact]
		public void Resolve_MissingCacheAndFetchError_TreatedAsCold()
		{
			CommunityCatalogFetchOutcome outcome = new(500, null, null);

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(outcome, null, null);

			Assert.Equal(CommunityCatalogCacheVerdict.Cold, result.Verdict);
			Assert.Equal("", result.Body);
			Assert.False(result.ShouldWriteCache);
		}

		[Fact]
		public void Resolve_CorruptCacheEtagOnlyAndFetchError_TreatedAsCold()
		{
			CommunityCatalogFetchOutcome outcome = new(500, null, null);

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(
				outcome, "\"old-etag\"", null);

			Assert.Equal(CommunityCatalogCacheVerdict.Cold, result.Verdict);
		}

		[Fact]
		public void Resolve_FetchErrorWithUsableCache_FallsBackToReusedCache()
		{
			CommunityCatalogFetchOutcome outcome = new(500, null, null);

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(
				outcome, "\"old-etag\"", "{\"packs\":[{\"id\":1}]}");

			Assert.Equal(CommunityCatalogCacheVerdict.Reused, result.Verdict);
			Assert.Equal("{\"packs\":[{\"id\":1}]}", result.Body);
			Assert.False(result.ShouldWriteCache);
		}

		[Fact]
		public void Resolve_200WithNullBody_FallsBackToUsableCacheRatherThanFresh()
		{
			// A malformed 200 (no body) must not be treated as authoritative
			// just because the status code was 200.
			CommunityCatalogFetchOutcome outcome = new(200, "\"new-etag\"", null);

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(
				outcome, "\"old-etag\"", "{\"packs\":[{\"id\":1}]}");

			Assert.Equal(CommunityCatalogCacheVerdict.Reused, result.Verdict);
			Assert.Equal("{\"packs\":[{\"id\":1}]}", result.Body);
			Assert.False(result.ShouldWriteCache);
		}

		[Theory]
		[InlineData("")]
		[InlineData("   ")]
		public void Resolve_200WithEmptyOrWhitespaceBody_FallsBackToUsableCacheRatherThanFresh(string body)
		{
			// HttpContent.ReadAsStringAsync() returns "" (never null) for a
			// zero-length response: a CDN/proxy answering 200 with an empty
			// body must not destroy a usable cache.
			CommunityCatalogFetchOutcome outcome = new(200, "\"new-etag\"", body);

			CommunityCatalogCacheResult result = CommunityCatalogCacheDecision.Resolve(
				outcome, "\"old-etag\"", "{\"packs\":[{\"id\":1}]}");

			Assert.Equal(CommunityCatalogCacheVerdict.Reused, result.Verdict);
			Assert.Equal("{\"packs\":[{\"id\":1}]}", result.Body);
			Assert.False(result.ShouldWriteCache);
		}
	}
}

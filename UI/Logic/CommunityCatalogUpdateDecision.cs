using System;
using System.Text.Json;

namespace Mesen.Logic
{
	//Verdict of CommunityCatalogUpdateDecision.Decide() (P.6, PRD Part B
	//§3.6 - amends ADR-0138 §37, whose trigger was source.sha256 only).
	public enum CommunityCatalogUpdateVerdict
	{
		//No readable install stamp: a fresh install, not an update.
		NotInstalled,
		//The slot's content_id matches the installed one -> nothing to do.
		UpToDate,
		//The slot's content_id differs -> reinstall (the trigger is content_id,
		//not source.sha256). The toast is "Updated ...".
		Updated,
		//The installed source.sha256 differs but the content_id is unchanged -
		//a wrapper-only repack (ADR-0138 §37's trigger without a content
		//change): do not reinstall.
		WrapperOnly,
		//The installed revision's semver is greater than the slot's (yank /
		//rollback / republished older label): no automatic downgrade - keep
		//the install. hd-legacy has no semver to protect.
		NoDowngrade,
		//The catalog has no slot for the chosen pack_id any more: keep the
		//install, keep the per-ROM choice, no toast. (In the fetch flow this
		//is the "no catalog match" path - the service already leaves it alone.)
		RemovedFromCatalog
	}

	//The installed-state fields a §3.6 decision needs from the container's
	//.mep-install.json (written by MepRecipeInstaller::WriteInstallStamp).
	public sealed record InstallStampFields(string? ContentId, string? SourceSha256);

	//P.6 (PRD Part B §3.6): the client-side catalog update decision for
	//the chosen pack_id of a loaded ROM. The trigger is the installed
	//content_id vs the catalog slot's content_id - not source.sha256 (that
	//amends ADR-0138 §37): a different content_id reinstalls (unless the
	//installed semver is newer - no auto-downgrade), an unchanged content_id
	//never reinstalls even when the artifact sha changed (wrapper-only repack),
	//and a slot that disappeared keeps the install with no toast. hd-legacy
	//has no semver, so any content_id difference updates it.
	//
	//Host-free (BCL only) so UI.Tests dual-compiles it; the caller reads the
	//stamp file and the installed version (GetMepPackList column 3 - the
	//stamp has no version) and passes the raw values in.
	public static class CommunityCatalogUpdateDecision
	{
		public static CommunityCatalogUpdateVerdict Decide(
			string? slotContentId, string? slotVersion, string? slotSourceSha256, bool isHdLegacy,
			InstallStampFields? installed, string? installedVersion)
		{
			if(installed == null) {
				return CommunityCatalogUpdateVerdict.NotInstalled;
			}

			if(string.IsNullOrWhiteSpace(slotContentId)) {
				//§3.6: pack removed from the catalog - keep the install.
				return CommunityCatalogUpdateVerdict.RemovedFromCatalog;
			}

			bool sameContent = string.Equals(installed.ContentId, slotContentId, StringComparison.OrdinalIgnoreCase);
			bool sameSource = string.Equals(installed.SourceSha256, slotSourceSha256, StringComparison.OrdinalIgnoreCase);
			if(sameContent) {
				//Wrapper-only repack (source changed, content did not): no reinstall.
				return sameSource
					? CommunityCatalogUpdateVerdict.UpToDate
					: CommunityCatalogUpdateVerdict.WrapperOnly;
			}

			//content_id differs: would update - unless the installed revision is
			//newer (no automatic downgrade). hd-legacy has no version number to
			//protect, so any content_id difference updates it.
			if(!isHdLegacy && CompareSemver(installedVersion, slotVersion) > 0) {
				return CommunityCatalogUpdateVerdict.NoDowngrade;
			}

			return CommunityCatalogUpdateVerdict.Updated;
		}

		//Reads the installed content_id + source.sha256 from a raw
		//.mep-install.json. Returns null for an unreadable/absent stamp.
		public static InstallStampFields? ReadStampFields(string? installStampJson)
		{
			if(string.IsNullOrWhiteSpace(installStampJson)) {
				return null;
			}
			try {
				using JsonDocument doc = JsonDocument.Parse(installStampJson);
				JsonElement root = doc.RootElement;
				string? contentId = root.TryGetProperty("content_id", out JsonElement cid) && cid.ValueKind == JsonValueKind.String ? cid.GetString() : null;
				string? sourceSha = null;
				if(root.TryGetProperty("source", out JsonElement source) && source.ValueKind == JsonValueKind.Object
					&& source.TryGetProperty("sha256", out JsonElement sha) && sha.ValueKind == JsonValueKind.String) {
					sourceSha = sha.GetString();
				}
				return new InstallStampFields(contentId, sourceSha);
			} catch(JsonException) {
				//Malformed stamp: treated as absent below (fresh install).
				return null;
			}
		}

		//Semver comparison for the no-downgrade guard: parses the leading
		//major.minor.patch numeric parts (pre-release/build suffixes ignored)
		//and compares numerically. Returns 0 when either side has no parseable
		//version (so an unknown installed version never blocks an update).
		public static int CompareSemver(string? a, string? b)
		{
			(int, int, int) pa = ParseSemver(a);
			(int, int, int) pb = ParseSemver(b);
			if(pa == (0, 0, 0) || pb == (0, 0, 0)) {
				return 0;
			}
			if(pa.Item1 != pb.Item1) return pa.Item1.CompareTo(pb.Item1);
			if(pa.Item2 != pb.Item2) return pa.Item2.CompareTo(pb.Item2);
			return pa.Item3.CompareTo(pb.Item3);
		}

		private static (int, int, int) ParseSemver(string? version)
		{
			if(string.IsNullOrWhiteSpace(version)) {
				return (0, 0, 0);
			}
			//Take the leading numeric "major[.minor[.patch]]"; drop any suffix
			//(-beta, +build, letters).
			int end = 0;
			while(end < version.Length && (char.IsDigit(version[end]) || version[end] == '.')) {
				end++;
			}
			string[] parts = version.Substring(0, end).Split('.');
			int major = ParsePart(parts, 0);
			int minor = ParsePart(parts, 1);
			int patch = ParsePart(parts, 2);
			return (major, minor, patch);
		}

		private static int ParsePart(string[] parts, int index)
		{
			return index < parts.Length && int.TryParse(parts[index], out int value) ? value : 0;
		}
	}
}

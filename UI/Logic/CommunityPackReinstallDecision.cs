using System;
using System.Text.Json;

namespace Mesen.Logic
{
	//Verdict of CommunityPackReinstallDecision.Decide().
	public enum CommunityPackReinstallVerdict
	{
		//The pack folder has no readable install stamp: this is a fresh
		//install, not a reinstall.
		NotInstalled,
		//The installed source.sha256 matches the catalog entry's: nothing
		//to do.
		UpToDate,
		//The installed source.sha256 differs from (or is unreadable in) the
		//stamp: the pack must be reinstalled from the catalog's artifact.
		Reinstall
	}

	//Pure reinstall-gate decision (ADR-0138 SS4/SS37, F6.4b): does a catalog
	//entry's declared `source.sha256` still match what is already on disk in
	//`<pack folder>/.mep-install.json` (written by
	//Core/Shared/EnhancementPacks/MepRecipeInstaller, F6.4a -
	//WriteInstallStamp)? No filesystem access happens here - the caller
	//reads the stamp file (or notes its absence as null/empty) and passes
	//the raw JSON text in, keeping this class BCL-only per the UI/Logic
	//firewall (UI/AGENTS.md).
	//
	//This class only decides; it does not police whether acting on a
	//Reinstall verdict is safe against `DisabledPacks`/`EnableMepPacks` -
	//that stays the service layer's job (ADR-0138 risk area, see scout.md).
	public static class CommunityPackReinstallDecision
	{
		public static CommunityPackReinstallVerdict Decide(string catalogSourceSha256, string? installStampJson)
		{
			if(string.IsNullOrWhiteSpace(installStampJson)) {
				return CommunityPackReinstallVerdict.NotInstalled;
			}

			string? installedSha256 = ExtractSourceSha256(installStampJson);
			if(installedSha256 == null) {
				//A stamp file exists but is corrupt or missing the field:
				//fail closed toward reinstalling rather than assuming the
				//pack is already up to date.
				return CommunityPackReinstallVerdict.Reinstall;
			}

			return string.Equals(installedSha256, catalogSourceSha256, StringComparison.OrdinalIgnoreCase)
				? CommunityPackReinstallVerdict.UpToDate
				: CommunityPackReinstallVerdict.Reinstall;
		}

		//Reads the `source.sha256` field written by MepRecipeInstaller's
		//WriteInstallStamp (Core/Shared/EnhancementPacks/MepRecipeInstaller.cpp):
		//{"recipe_hash": ..., "source": {"sha256": "..."}, "deps": {...}, "installed_at": ...}.
		private static string? ExtractSourceSha256(string installStampJson)
		{
			try {
				using JsonDocument doc = JsonDocument.Parse(installStampJson);
				if(doc.RootElement.TryGetProperty("source", out JsonElement source)
					&& source.ValueKind == JsonValueKind.Object
					&& source.TryGetProperty("sha256", out JsonElement sha)
					&& sha.ValueKind == JsonValueKind.String) {
					return sha.GetString();
				}
			} catch(JsonException) {
				//Malformed JSON: treated the same as a missing field below.
			}
			return null;
		}
	}
}

using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Mesen.Logic
{
	//Host-free install registry (ADR-0147): the source of truth for "which
	//catalog pack a ROM has installed", kept OUTSIDE the editable mep/ folder so
	//a mangled pack can never destroy the ability to Restore. One JSON file per
	//ROM (No-Intro SHA-1 key) under <EnhancementPacks>/.cache/installs/. BCL
	//only - no Avalonia/EmuApi - so this dual-compiles into UI.Tests and any
	//accidental host dependency breaks `dotnet test`.
	public sealed class CommunityPackInstallRecord
	{
		public string PackId { get; set; } = "";
		public string ContentId { get; set; } = "";
		public string SourceSha256 { get; set; } = "";
		public string Container { get; set; } = "";
		public string MepPath { get; set; } = "";
		public string InstalledAt { get; set; } = "";
		//ADR-0147: content_id of the mep/ tree as materialized at install time,
		//compared against a recomputed value to detect a local (user) edit.
		public string BaselineContentId { get; set; } = "";
	}

	//Source-generated (AOT-safe, no trim/DynamicCode warnings) - the DTO lives in
	//this host-free folder, so it can't reference the host's MesenSerializerContext
	//(which UI.Tests does not compile). JsonException is caught by the callers.
	[JsonSourceGenerationOptions(WriteIndented = true)]
	[JsonSerializable(typeof(CommunityPackInstallRecord))]
	internal partial class CommunityPackInstallRegistryContext : JsonSerializerContext
	{
	}

	public static class CommunityPackInstallRegistry
	{
		//<cacheRoot>/installs/<romsha1>.json (cacheRoot = EnhancementPacks/.cache)
		public static string FilePath(string cacheRoot, string romSha1) =>
			Path.Combine(cacheRoot, "installs", (string.IsNullOrWhiteSpace(romSha1) ? "unknown" : romSha1.ToLowerInvariant()) + ".json");

		public static CommunityPackInstallRecord? Read(string cacheRoot, string romSha1)
		{
			try {
				string path = FilePath(cacheRoot, romSha1);
				return File.Exists(path) ? JsonSerializer.Deserialize(File.ReadAllText(path), CommunityPackInstallRegistryContext.Default.CommunityPackInstallRecord) : null;
			} catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or JsonException) {
				return null;
			}
		}

		public static void Write(string cacheRoot, string romSha1, CommunityPackInstallRecord record)
		{
			try {
				Directory.CreateDirectory(Path.Combine(cacheRoot, "installs"));
				File.WriteAllText(FilePath(cacheRoot, romSha1), JsonSerializer.Serialize(record, CommunityPackInstallRegistryContext.Default.CommunityPackInstallRecord));
			} catch(Exception ex) when(ex is IOException or UnauthorizedAccessException) {
				//Best-effort: the .mep-install.json inside the pack folder remains
				//the source for the per-load update decision; this registry only
				//backs Restore when mep/ has been mangled.
			}
		}
	}
}

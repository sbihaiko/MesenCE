using System.IO.Compression;
using System.Linq;

namespace Mesen.Logic
{
	//Host-free MEP zip validator (Fase 1, docs/roadmap/plano-testes-unitarios.md).
	//BCL + System.IO.Compression only, per the UI/Logic/ firewall contract - so
	//this file dual-compiles unmodified into UI.Tests (see UI.Tests/UI.Tests.csproj).
	//
	//Mirrors MepPack::DetectConventionLayout (Core/Shared/EnhancementPacks/MepPack.cpp):
	//a zip is a valid pack if it has pack.json at the root, or a probe file for
	//one of the three convention sections (ADR-0049), in either the human or
	//the `auto/` layer. The audio section additionally accepts fingerprints.json
	//in place of hires.txt (ADR-0047) - this was the one gap between the C++
	//core loader and the old inline UI check, closed here.
	public static class MepZipValidator
	{
		//Convention-layout probe files (Core kConventionProbe, plus the
		//audio/fingerprints.json alternative from ADR-0047).
		private static readonly string[] LayerProbes = new[] {
			"textures/hires.txt",
			"audio/hires.txt",
			"audio/fingerprints.json",
			"synth/preset.cfg",
		};

		//Validates a MEP pack zip already opened for reading. Returns null when
		//the archive is an acceptable pack; otherwise a message ID from the
		//existing UI string table describing why it was rejected.
		public static string? Validate(ZipArchive zip)
		{
			if(!HasAnyLayer(zip)) {
				return "InstallMepPackInvalidPack";
			}

			foreach(ZipArchiveEntry entry in zip.Entries) {
				if(!IsSafePath(entry.FullName)) {
					return "InstallMepPackInvalidPack";
				}
			}

			return null;
		}

		private static bool HasAnyLayer(ZipArchive zip)
		{
			if(zip.GetEntry("pack.json") != null) {
				return true;
			}

			foreach(string probe in LayerProbes) {
				if(zip.GetEntry(probe) != null || zip.GetEntry("auto/" + probe) != null) {
					return true;
				}
			}

			return false;
		}

		//Rejects zip-slip entry names: absolute paths (leading '/'), a colon
		//anywhere (Windows drive letters and NTFS alternate data streams alike),
		//any ".." path segment (checked after normalizing '\' to '/', since a
		//zip built on Windows may use either separator), and raw control
		//characters (< 0x20) that a downstream extractor could mishandle.
		public static bool IsSafePath(string entryFullName)
		{
			string normalized = entryFullName.Replace('\\', '/');
			if(normalized.StartsWith("/") || normalized.Contains(':')) {
				return false;
			}

			if(normalized.Split('/').Contains("..")) {
				return false;
			}

			foreach(char c in normalized) {
				if(c < 0x20) {
					return false;
				}
			}

			return true;
		}
	}
}

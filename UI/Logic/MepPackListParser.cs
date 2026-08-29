using System;
using System.Collections.Generic;
using System.Text;

namespace Mesen.Logic
{
	//Host-free counterpart to EmuApi.GetMepPackList()'s raw output (Fase 1,
	//docs/roadmap/plano-testes-unitarios.md). The native side emits one pack
	//per newline-separated line, either an 8-column tab-separated record or a
	//"!"-prefixed rejection message. Kept free of Avalonia/EmuApi so it can be
	//dual-compiled into UI.Tests (see UI.Tests/UI.Tests.csproj) and unit
	//tested without the native MesenCore library.
	public static class MepPackListParser
	{
		//Container, Name, Version, Author, License, Sections, Enabled, Origin
		//(columns 9/10 - packId/contentId - are optional, P.3)
		public const int ExpectedColumnCount = 8;

		public static MepPackListResult Parse(string packListOutput)
		{
			MepPackListResult result = new();
			StringBuilder rejected = new();

			foreach(string line in packListOutput.Split('\n', StringSplitOptions.RemoveEmptyEntries)) {
				if(line.StartsWith("!")) {
					rejected.AppendLine(line.Substring(1));
					continue;
				}

				string[] parts = line.Split('\t');
				if(parts.Length < ExpectedColumnCount) {
					//Malformed/short row: ignored rather than throwing, matching
					//the original inline VM behavior this replaces.
					continue;
				}

				result.Packs.Add(ParseEntry(parts));
			}

			result.RejectedInfo = rejected.ToString().TrimEnd();
			return result;
		}

		private static MepPackListEntry ParseEntry(string[] parts)
		{
			return new MepPackListEntry {
				Container = parts[0],
				Name = parts[1],
				Version = parts[2],
				Author = parts[3],
				License = parts[4],
				//Raw, un-prettified section list: the ","->", " display
				//formatting stays the caller's (VM) responsibility.
				Sections = parts[5],
				Enabled = parts[6] == "1",
				Source = ResolveSource(parts[7]),
				//P.3: columns 9/10 (pack_id/content_id from .mep-install.json)
				//are optional - an 8-column row from an older core is still valid.
				PackId = parts.Length >= 9 ? parts[8] : "",
				ContentId = parts.Length >= 10 ? parts[9] : ""
			};
		}

		private static string ResolveSource(string origin)
		{
			return origin switch {
				"2" => "sibling",
				"1" => "zip",
				_ => "folder"
			};
		}
	}

	public sealed class MepPackListResult
	{
		public List<MepPackListEntry> Packs { get; } = new();
		public string RejectedInfo { get; set; } = "";
		public bool HasPacks => Packs.Count > 0;
		public bool HasRejected => RejectedInfo.Length > 0;
	}

	public sealed class MepPackListEntry
	{
		public string Container { get; init; } = "";
		public string Name { get; init; } = "";
		public string Version { get; init; } = "";
		public string Author { get; init; } = "";
		public string License { get; init; } = "";
		public string Sections { get; init; } = "";
		public bool Enabled { get; init; }
		public string Source { get; init; } = "";
		//P.3: pack_id/content_id from the container's .mep-install.json stamp
		//("" for a stamp-less container - the resolver derives `local:<container>`)
		public string PackId { get; init; } = "";
		public string ContentId { get; init; } = "";
	}
}

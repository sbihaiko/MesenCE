using System;
using System.IO;
using System.Linq;

namespace Mesen.Logic
{
	//Host-free half of the community-pack container-name rule (ADR-0138 §43/§52);
	//stateful partner: UI/Services/CommunityPackInstallCoordinator.ResolveOutFolder,
	//which roots the result under EnhancementPackFolder and asserts it stayed there.
	//A catalog entry's `name` (fallback `game`) is remote, submitter-influenced data
	//(MEI-v1.md §2.2) that ends up as a folder name reached by Directory.Delete and
	//the native extraction target, and as the DisabledPacks key (ADR-0040) - so the
	//sanitization lives here, where UI.Tests can pin it.
	public static class CommunityPackContainerName
	{
		public const string Fallback = "community-pack";
		public const int MaxLength = 96;

		public static string Sanitize(string? name, string? game)
		{
			string raw = string.IsNullOrWhiteSpace(name) ? (game ?? "") : name;
			char[] invalid = Path.GetInvalidFileNameChars();
			string sanitized = new string(raw.Select(c => invalid.Contains(c) || c == '/' || c == '\\' ? '_' : c).ToArray()).Trim().TrimEnd('.', ' ');
			if(sanitized.Length > MaxLength) {
				sanitized = sanitized.Substring(0, MaxLength).TrimEnd('.', ' '); //truncation can re-expose a trailing dot/space
			}
			return sanitized.Length == 0 || sanitized.All(c => c == '.') ? Fallback : sanitized;
		}
	}
}

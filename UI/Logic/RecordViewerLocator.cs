using System;
using System.Collections.Generic;
using System.IO;

namespace Mesen.Logic
{
	//Host-free half of "open the live viewer for the game that is running"
	//(ADR-0169 section 4): where scripts/record_viewer.py is, and which command
	//runs it. Stateful partner: UI/Utilities/LiveRecordingSession, which starts
	//the process and owns its lifetime.
	//
	//The viewer is an external stdlib+tkinter tool in the repo (ADR-0165), not a
	//file the emulator ships, so the path is discovered rather than configured:
	//from the executable's folder (a dev build lives several levels under the
	//repo root) or the working directory, walking up until a
	//scripts/record_viewer.py turns up. MESENCE_RECORD_VIEWER overrides the
	//search for anyone running a packaged .app whose repo is somewhere else.
	public static class RecordViewerLocator
	{
		public const string EnvVar = "MESENCE_RECORD_VIEWER";
		public const string ScriptFolder = "scripts";
		public const string ScriptName = "record_viewer.py";

		//How far up from a start folder to look. A published dev build sits at
		//bin/<rid>/<config>/<rid>/publish/, five levels down; the extra levels
		//cover a .app bundle's own Contents/MacOS nesting under that.
		public const int MaxDepth = 10;

		//python3 first: the viewer is Python 3 stdlib + tkinter, and on a mac or
		//a Linux box "python" may still be a 2.x or missing entirely. Windows
		//installs the launcher and "python" instead.
		public static IReadOnlyList<string> PythonCommands(bool isWindows)
		{
			return isWindows ? new string[] { "python", "python3", "py" } : new string[] { "python3", "python" };
		}

		//The override, when it names a file that exists. Anything else (unset,
		//or a stale path) falls through to the search - an env var that no
		//longer resolves should not disable the feature silently.
		public static string? FromEnvironment(string? envValue, Func<string, bool> fileExists)
		{
			if(string.IsNullOrWhiteSpace(envValue)) {
				return null;
			}
			return fileExists(envValue) ? envValue : null;
		}

		//The first scripts/record_viewer.py found walking each start folder up
		//to the filesystem root, or null. Start folders are tried in order, so
		//the caller decides whether the executable or the working directory
		//wins.
		public static string? FindScript(IEnumerable<string?> startFolders, Func<string, bool> fileExists, int maxDepth = MaxDepth)
		{
			foreach(string? start in startFolders) {
				if(string.IsNullOrWhiteSpace(start)) {
					continue;
				}
				string? folder = start;
				for(int depth = 0; depth <= maxDepth && folder != null; depth++) {
					string candidate = Path.Combine(folder, ScriptFolder, ScriptName);
					if(fileExists(candidate)) {
						return candidate;
					}
					folder = Path.GetDirectoryName(folder.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
				}
			}
			return null;
		}
	}
}

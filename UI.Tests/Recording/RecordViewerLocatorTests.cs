using System;
using System.Collections.Generic;
using System.IO;
using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.Recording
{
	// ADR-0169 section 4: the Tools menu opens the live viewer for the game
	// that is running, so the emulator has to find scripts/record_viewer.py
	// from wherever its executable happens to live (UI/Logic/RecordViewerLocator).
	public class RecordViewerLocatorTests
	{
		private static string P(params string[] parts) => Path.Combine(parts);

		private static Func<string, bool> Exists(params string[] files)
		{
			HashSet<string> set = new(files, StringComparer.Ordinal);
			return path => set.Contains(path);
		}

		[Fact]
		public void FindScript_ScriptBesideTheStartFolder_IsFound()
		{
			string script = P("repo", "scripts", "record_viewer.py");

			Assert.Equal(script, RecordViewerLocator.FindScript(new[] { "repo" }, Exists(script)));
		}

		[Fact]
		public void FindScript_ExecutableSeveralLevelsUnderTheRepo_WalksUp()
		{
			string script = P("repo", "scripts", "record_viewer.py");
			string exeDir = P("repo", "bin", "osx-arm64", "Release", "osx-arm64", "publish");

			Assert.Equal(script, RecordViewerLocator.FindScript(new[] { exeDir }, Exists(script)));
		}

		[Fact]
		public void FindScript_TrailingSeparatorOnTheStartFolder_StillWalksUp()
		{
			string script = P("repo", "scripts", "record_viewer.py");
			string exeDir = P("repo", "bin", "publish") + Path.DirectorySeparatorChar;

			Assert.Equal(script, RecordViewerLocator.FindScript(new[] { exeDir }, Exists(script)));
		}

		[Fact]
		public void FindScript_NoScriptAnywhere_ReturnsNull()
		{
			Assert.Null(RecordViewerLocator.FindScript(new[] { P("repo", "bin") }, Exists()));
		}

		[Fact]
		public void FindScript_BeyondMaxDepth_IsNotFound()
		{
			string script = P("repo", "scripts", "record_viewer.py");
			string exeDir = P("repo", "a", "b", "c");

			Assert.Null(RecordViewerLocator.FindScript(new[] { exeDir }, Exists(script), maxDepth: 1));
		}

		[Fact]
		public void FindScript_StartFoldersAreTriedInOrder()
		{
			string first = P("first", "scripts", "record_viewer.py");
			string second = P("second", "scripts", "record_viewer.py");

			Assert.Equal(first, RecordViewerLocator.FindScript(new[] { "first", "second" }, Exists(first, second)));
			Assert.Equal(second, RecordViewerLocator.FindScript(new[] { "missing", "second" }, Exists(second)));
		}

		[Fact]
		public void FindScript_NullOrEmptyStartFolders_AreSkipped()
		{
			string script = P("repo", "scripts", "record_viewer.py");

			Assert.Equal(script, RecordViewerLocator.FindScript(new string?[] { null, "", "  ", "repo" }, Exists(script)));
		}

		[Fact]
		public void FromEnvironment_UnsetOrStalePath_FallsThroughToTheSearch()
		{
			Assert.Null(RecordViewerLocator.FromEnvironment(null, Exists()));
			Assert.Null(RecordViewerLocator.FromEnvironment("", Exists()));
			Assert.Null(RecordViewerLocator.FromEnvironment("/gone/record_viewer.py", Exists()));
		}

		[Fact]
		public void FromEnvironment_ExistingFile_Wins()
		{
			Assert.Equal("/elsewhere/record_viewer.py",
				RecordViewerLocator.FromEnvironment("/elsewhere/record_viewer.py", Exists("/elsewhere/record_viewer.py")));
		}

		[Fact]
		public void PythonCommands_PreferPython3OffWindows()
		{
			Assert.Equal("python3", RecordViewerLocator.PythonCommands(isWindows: false)[0]);
			Assert.Equal("python", RecordViewerLocator.PythonCommands(isWindows: true)[0]);
		}
	}
}

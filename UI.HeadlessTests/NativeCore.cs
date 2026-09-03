using System;
using System.IO;
using System.Runtime.InteropServices;
using Mesen.Interop;

namespace Mesen.HeadlessTests;

//ADR-0150 §3 ("P/Invoke containment"). UI/UI.csproj carries UI/Interop/EmuApi.cs
//and its ~60 DllImports against the native MesenCore library. Some of the XAML
//under test cannot be reached without at least one of them running:
//`MainWindow`'s constructor calls EmuApi.InitDll() before its XAML is loaded,
//and the input Test tab calls InputApi.GetConnectedGamepadCount() the moment the
//tab is selected.
//
//Rather than faking the core (a stub library would answer with values the real
//core never returns, and the test would then be asserting the stub), this loads
//the REAL library when the repo happens to have one built, and skips the test
//with an explicit reason when it does not - which is the case on the CI runner,
//where building MesenCore is out of scope for unit-tests.yml (ADR-0131).
public static class NativeCore
{
	private static bool _initialized;
	private static string? _skipReason;

	public static string? SkipReason
	{
		get {
			Initialize();
			return _skipReason;
		}
	}

	public static bool IsAvailable => SkipReason == null;

	private static void Initialize()
	{
		if(_initialized) {
			return;
		}
		_initialized = true;

		string? library = FindLibrary();
		if(library == null) {
			_skipReason = "MesenCore is not built in this checkout (looked for MESEN_CORE_LIB and bin/<rid>/{Release,Debug}/, InteropDLL/obj.<rid>/). " +
				"unit-tests.yml never builds the native core (ADR-0131), so this XAML-wiring check runs locally after `make` and is skipped in CI.";
			return;
		}

		try {
			IntPtr handle = NativeLibrary.Load(library);
			NativeLibrary.SetDllImportResolver(typeof(EmuApi).Assembly, (name, assembly, path) => name == EmuApi.DllName ? handle : IntPtr.Zero);
			//Fails loudly here rather than half-way through a window constructor.
			EmuApi.TestDll();
		} catch(Exception ex) {
			_skipReason = $"MesenCore at '{library}' could not be loaded: {ex.GetType().Name} - {ex.Message}";
		}
	}

	private static string? FindLibrary()
	{
		string fromEnv = Environment.GetEnvironmentVariable("MESEN_CORE_LIB") ?? "";
		if(fromEnv == "none") {
			//Escape hatch to reproduce the CI runner's "no native core" state on a
			//machine that does have one built.
			return null;
		}
		if(fromEnv.Length > 0 && File.Exists(fromEnv)) {
			return fromEnv;
		}

		string? repo = FindRepoRoot();
		if(repo == null) {
			return null;
		}

		//The RID sub-folder is whatever the local `make` produced; glob it rather
		//than guessing (RuntimeInformation.RuntimeIdentifier can carry an OS
		//version, e.g. osx.15-arm64, that the build folder never has).
		string name = OperatingSystem.IsWindows() ? "MesenCore.dll" : (OperatingSystem.IsMacOS() ? "MesenCore.dylib" : "MesenCore.so");
		foreach(string dir in EnumerateDirectories(Path.Combine(repo, "bin"))) {
			foreach(string config in new[] { "Release", "Debug" }) {
				string candidate = Path.Combine(dir, config, name);
				if(File.Exists(candidate)) {
					return candidate;
				}
			}
		}
		foreach(string dir in EnumerateDirectories(Path.Combine(repo, "InteropDLL"))) {
			string candidate = Path.Combine(dir, name);
			if(Path.GetFileName(dir).StartsWith("obj.", StringComparison.Ordinal) && File.Exists(candidate)) {
				return candidate;
			}
		}
		return null;
	}

	private static string[] EnumerateDirectories(string path)
	{
		return Directory.Exists(path) ? Directory.GetDirectories(path) : Array.Empty<string>();
	}

	private static string? FindRepoRoot()
	{
		DirectoryInfo? dir = new(AppContext.BaseDirectory);
		while(dir != null) {
			if(File.Exists(Path.Combine(dir.FullName, "Mesen.sln"))) {
				return dir.FullName;
			}
			dir = dir.Parent;
		}
		return null;
	}
}

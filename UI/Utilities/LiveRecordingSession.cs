using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using Mesen.Config;
using Mesen.Interop;
using Mesen.Logic;

namespace Mesen.Utilities
{
	//The live recording session as the UI drives it (ADR-0169 section 4): the
	//Core recorder publishing into the convention slot, the external viewer
	//watching it, and the ROM identity that keeps both pointed at the game
	//actually running.
	//
	//One place rather than one per caller: the Tools menu, the game-load
	//notification and the emulation-stopped notification all have to keep the
	//same three things in step, and "recording the previous ROM while showing
	//the new one" is exactly the inconsistency this exists to prevent.
	public static class LiveRecordingSession
	{
		//Fixed by ADR-0169 section 4 ("the interval is fixed") - one less field
		//in a surface whose whole point is that nothing is typed.
		public const int IntervalMs = 250;

		//The viewer we started, while it is alive. Only ours: a viewer the user
		//launched from a terminal is invisible here, and that is fine - the
		//protocol is one-way file publishing, so any number of viewers can
		//watch the same slot (ADR-0169 section 1).
		private static Process? _viewer;

		public static bool IsRecording => RecordApi.LiveRecordingIsRecording();

		public static bool IsViewerRunning
		{
			get
			{
				Process? viewer = _viewer;
				if(viewer == null) {
					return false;
				}
				try {
					return !viewer.HasExited;
				} catch(InvalidOperationException) {
					return false;
				}
			}
		}

		//Start publishing the running game and show it. The viewer opens even
		//when the recorder refuses (an already-running session, a bad slot):
		//the window is where the refusal is visible, and the Core half logs the
		//reason.
		public static void Start()
		{
			AnnounceRom();
			string dir = ConfigManager.LiveRecordingFolder;
			bool started = RecordApi.LiveRecordingStart(dir, IntervalMs);
			EmuApi.WriteLogEntry("[LiveRecording] UI: start requested (" + dir + ", " + IntervalMs + "ms) -> " + (started ? "started" : "REFUSED"));
			OpenViewer();
		}

		public static void Stop()
		{
			RecordApi.LiveRecordingStop();
			EmuApi.WriteLogEntry("[LiveRecording] UI: stop requested");
			//The viewer stays open on purpose: the last published frame plus the
			//final done=true status is what says how the session ended.
		}

		//Announce the game that just loaded, so the recorder re-targets its
		//slot instead of publishing a new game's frames beside the previous
		//one's CHR/palette (LiveFrameRecorder::SetRomName).
		public static void OnGameLoaded(RomInfo romInfo)
		{
			RecordApi.LiveRecordingSetRom(romInfo.GetRomName());
		}

		//No game, no session: with the ROM closed the recorder has nothing to
		//publish, and a "Stop" left enabled over an idle slot is the menu
		//inconsistency this avoids.
		public static void OnEmulationStopped()
		{
			RecordApi.LiveRecordingSetRom("");
			if(RecordApi.LiveRecordingIsRecording()) {
				RecordApi.LiveRecordingStop();
				EmuApi.WriteLogEntry("[LiveRecording] UI: stopped with the game");
			}
		}

		private static void AnnounceRom()
		{
			RomInfo romInfo = EmuApi.GetRomInfo();
			RecordApi.LiveRecordingSetRom(romInfo.GetRomName());
		}

		//Bring up scripts/record_viewer.py on the convention slot. Returns
		//false (and logs why) when the script or a Python cannot be found -
		//the recording is unaffected either way, which is the whole point of
		//the one-way protocol.
		public static bool OpenViewer()
		{
			if(IsViewerRunning) {
				//Nothing to do: it polls the slot, so it already follows the
				//ROM change that got us here. Re-launching would just stack
				//windows on the same directory.
				EmuApi.WriteLogEntry("[LiveRecording] UI: viewer already open");
				return true;
			}

			string? script = RecordViewerLocator.FromEnvironment(
				Environment.GetEnvironmentVariable(RecordViewerLocator.EnvVar), File.Exists)
				?? RecordViewerLocator.FindScript(ViewerSearchFolders(), File.Exists);
			if(script == null) {
				string msg = "cannot find " + RecordViewerLocator.ScriptFolder + "/" + RecordViewerLocator.ScriptName
					+ " - set " + RecordViewerLocator.EnvVar + " to its full path (recording is unaffected)";
				EmuApi.WriteLogEntry("[LiveRecording] UI: " + msg);
				DisplayMessageHelper.DisplayMessage("Error", msg);
				return false;
			}

			string liveDir = ConfigManager.LiveRecordingFolder;
			bool isWindows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
			foreach(string python in RecordViewerLocator.PythonCommands(isWindows)) {
				try {
					ProcessStartInfo startInfo = new() {
						FileName = python,
						UseShellExecute = false,
						//The slot is passed explicitly: the viewer can mirror the
						//convention on its own, but only for a non-portable
						//install - a portable emulator keeps its home folder
						//beside the executable (ConfigManager.HomeFolder).
						ArgumentList = { script, liveDir },
						WorkingDirectory = Path.GetDirectoryName(script) ?? ""
					};
					_viewer = Process.Start(startInfo);
					if(_viewer != null) {
						EmuApi.WriteLogEntry("[LiveRecording] UI: viewer opened (" + python + " " + script + " " + liveDir + ")");
						return true;
					}
				} catch(Exception ex) {
					EmuApi.WriteLogEntry("[LiveRecording] UI: " + python + " did not start the viewer (" + ex.Message + ")");
				}
			}

			string failure = "no Python 3 with tkinter could start the live viewer (recording is unaffected)";
			EmuApi.WriteLogEntry("[LiveRecording] UI: " + failure);
			DisplayMessageHelper.DisplayMessage("Error", failure);
			return false;
		}

		private static List<string?> ViewerSearchFolders()
		{
			//The executable's own folder first: a dev build sits under the repo
			//that holds scripts/, while the working directory is wherever the
			//app happened to be launched from.
			return new List<string?> { AppContext.BaseDirectory, Program.OriginalFolder, Environment.CurrentDirectory };
		}
	}
}

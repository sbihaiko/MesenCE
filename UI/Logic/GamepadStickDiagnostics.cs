namespace Mesen.Logic
{
	//Host-free stick diagnostics for the input tester (PRD I.1/I.3):
	//DeadzoneRatio mirrors Core's EmuSettings.GetControllerDeadzoneRatio - the
	//0-4 ControllerDeadzoneSize maps to a 0.5-1.5 multiplier that each platform
	//applies to its own base deadzone. The tester renders the ring at the
	//DirectInput-canonical extent (half the int16 range x ratio), which is within
	//a few percent of every backend's effective deadzone, as a display
	//approximation. Kept free of Avalonia/EmuApi so it dual-compiles into
	//UI.Tests.
	public static class GamepadStickDiagnostics
	{
		public static double DeadzoneRatio(uint deadzoneSize)
		{
			switch(deadzoneSize) {
				case 0: return 0.5;
				case 1: return 0.75;
				case 2: return 1;
				case 3: return 1.25;
				case 4: return 1.5;
			}
			return 1;
		}

		//DirectInput canonical deadzone in int16 axis units (Core mirrors the
		//same formula in DirectInputManager.cpp).
		public static int DeadzoneUnits(uint deadzoneSize)
		{
			return (int)((short.MaxValue / 2.0) * DeadzoneRatio(deadzoneSize));
		}
	}

	//Flags a stick that stays beyond the deadzone for a sustained run of samples
	//- the stick is not returning to center (a worn stick, or the pad held
	//off-center), so input would register without the player touching it.
	//Sample-count based (no timer), so it is deterministic and testable.
	public class GamepadDriftDetector
	{
		//~500ms at the tester's 16ms poll rate.
		public const int SustainedSamples = 30;

		private int _overDeadzoneSamples;

		public bool IsDrifting { get; private set; }

		public void Update(int magnitude, int deadzoneUnits)
		{
			if(magnitude > deadzoneUnits) {
				_overDeadzoneSamples++;
				IsDrifting = _overDeadzoneSamples >= SustainedSamples;
			} else {
				_overDeadzoneSamples = 0;
				IsDrifting = false;
			}
		}

		public void Reset()
		{
			_overDeadzoneSamples = 0;
			IsDrifting = false;
		}
	}
}

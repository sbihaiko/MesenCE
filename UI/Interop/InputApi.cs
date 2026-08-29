using Mesen.Config;
using Mesen.Utilities;
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Mesen.Interop
{
	public class InputApi
	{
		private const string DllPath = EmuApi.DllName;

		[DllImport(DllPath)] public static extern void SetKeyState(UInt16 scanCode, [MarshalAs(UnmanagedType.I1)] bool pressed);
		[DllImport(DllPath)] public static extern void ResetKeyState();

		[DllImport(DllPath)] public static extern void SetMouseMovement(Int16 x, Int16 y);
		[DllImport(DllPath)] public static extern void SetMousePosition(double x, double y);
		[DllImport(DllPath)] public static extern void DisableAllKeys([MarshalAs(UnmanagedType.I1)] bool disabled);
		[DllImport(DllPath)] public static extern void UpdateInputDevices();

		[DllImport(DllPath)] public static extern UInt16 GetKeyCode([MarshalAs(UnmanagedType.LPUTF8Str)] string keyName);

		[DllImport(DllPath)] public static extern void ResetLagCounter();

		[DllImport(DllPath)][return: MarshalAs(UnmanagedType.I1)] public static extern bool HasControlDevice(ControllerType type);

		[DllImport(DllPath)] public static extern SystemMouseState GetSystemMouseState(IntPtr rendererHandle);
		[DllImport(DllPath)][return: MarshalAs(UnmanagedType.I1)] public static extern bool CaptureMouse(Int32 x, Int32 y, Int32 width, Int32 height, IntPtr rendererHandle);
		[DllImport(DllPath)] public static extern void ReleaseMouse();
		[DllImport(DllPath)] public static extern void SetSystemMousePosition(Int32 x, Int32 y);
		[DllImport(DllPath)] public static extern void SetCursorImage(CursorImage cursor);
		[DllImport(DllPath)] public static extern double GetPixelScale();

		[DllImport(DllPath, EntryPoint = "GetKeyName")] private static extern IntPtr GetKeyNameWrapper(UInt16 key, IntPtr outKeyName, Int32 maxLength);
		public unsafe static string GetKeyName(UInt16 key)
		{
			byte[] outKeyName = new byte[1000];
			fixed(byte* ptr = outKeyName) {
				InputApi.GetKeyNameWrapper(key, (IntPtr)ptr, outKeyName.Length);
				return Utf8Utilities.PtrToStringUtf8((IntPtr)ptr);
			}
		}

		[DllImport(DllPath, EntryPoint = "GetPressedKeys")] private static extern void GetPressedKeysWrapper(IntPtr keyBuffer);
		public static unsafe List<UInt16> GetPressedKeys()
		{
			UInt16[] keyBuffer = new UInt16[3];
			fixed(UInt16* ptr = keyBuffer) {
				InputApi.GetPressedKeysWrapper((IntPtr)ptr);
			}

			List<UInt16> keys = new List<UInt16>();
			for(int i = 0; i < 3; i++) {
				if(keyBuffer[i] != 0) {
					keys.Add(keyBuffer[i]);
				}
			}
			return keys;
		}

		//Host input tester (PRD slice I.0): enumerate connected pads and read
		//their raw state without touching the emulated PadN mapping.
		[DllImport(DllPath)] public static extern UInt32 GetConnectedGamepadCount();
		[DllImport(DllPath)] public static extern bool GetGamepadInfo(UInt32 index, out GamepadInfo info);
		[DllImport(DllPath)] public static extern bool GetGamepadState(UInt32 index, out GamepadState state);
		[DllImport(DllPath)] public static extern void TestForceFeedback(UInt32 index, UInt16 magnitudeRight, UInt16 magnitudeLeft);
	}

	public enum GamepadBackend : byte
	{
		None = 0,
		XInput = 1,
		DirectInput = 2,
		Evdev = 3,
		GameController = 4
	}

	[StructLayout(LayoutKind.Sequential)]
	public struct GamepadInfo
	{
		[MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Name;
		public UInt32 VendorId;
		public UInt32 ProductId;
		public UInt32 Slot;
		[MarshalAs(UnmanagedType.U1)] public bool HasRumble;
		[MarshalAs(UnmanagedType.U1)] public GamepadBackend Backend;
	}

	[StructLayout(LayoutKind.Sequential)]
	public struct GamepadState
	{
		public UInt32 Buttons;
		[MarshalAs(UnmanagedType.ByValArray, SizeConst = 4)] public Int16[] Axes;
	}

	public enum CursorImage
	{
		Hidden,
		Arrow,
		Cross
	}

	[StructLayout(LayoutKind.Sequential)]
	public struct SystemMouseState
	{
		public Int32 XPosition;
		public Int32 YPosition;
		[MarshalAs(UnmanagedType.I1)] public bool LeftButton;
		[MarshalAs(UnmanagedType.I1)] public bool RightButton;
		[MarshalAs(UnmanagedType.I1)] public bool MiddleButton;
		[MarshalAs(UnmanagedType.I1)] public bool Button4;
		[MarshalAs(UnmanagedType.I1)] public bool Button5;
	}
}

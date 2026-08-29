using Avalonia;
using Avalonia.Media;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Mesen.Config;
using Mesen.Interop;
using Mesen.Localization;
using Mesen.Logic;
using Mesen.Utilities;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;

namespace Mesen.ViewModels
{
	//Host input tester (PRD slice I.1): Settings -> Input -> Test tab. One item
	//per connected pad (name/backend/slot/VID-PID/rumble) with its live buttons
	//and raw axes. The tab is fed by Refresh() from a ~16ms timer that only runs
	//while the tab is visible - the constructor never calls InputApi, so opening
	//the input settings does not touch the host devices until the user opens the
	//Test tab. Lives in ViewModels (not UI/Logic/) per the slice.
	public partial class GamepadTesterViewModel : DisposableViewModel
	{
		[ObservableProperty] public partial bool IsTestTabVisible { get; set; }
		[ObservableProperty] public partial bool HasPads { get; set; }
		[ObservableProperty] public partial bool ShowNoPadsHint { get; set; } = true;

		public ObservableCollection<GamepadTestItem> Gamepads { get; } = new();

		private DispatcherTimer? _pollTimer;

		public GamepadTesterViewModel()
		{
			AddDisposable(this.ObserveProp(nameof(IsTestTabVisible), () => {
				if(IsTestTabVisible) {
					StartPolling();
				} else {
					StopPolling();
				}
			}));
		}

		private void StartPolling()
		{
			StopPolling();
			_pollTimer = new DispatcherTimer();
			_pollTimer.Interval = TimeSpan.FromMilliseconds(16); //~60 Hz, within the 16-33 ms slice
			_pollTimer.Tick += (s, e) => Refresh();
			_pollTimer.Start();
			Refresh();
		}

		private void StopPolling()
		{
			_pollTimer?.Stop();
			_pollTimer = null;
		}

		public void Refresh()
		{
			uint count = InputApi.GetConnectedGamepadCount();
			uint globalDeadzoneSize = ConfigManager.Config.Input.ControllerDeadzoneSize;
			IReadOnlyList<DeviceDeadzoneOverride> overrides = ConfigManager.Config.Input.PerDeviceDeadzones;
			while(Gamepads.Count < count) {
				Gamepads.Add(new GamepadTestItem((uint)Gamepads.Count));
			}
			while(Gamepads.Count > count) {
				Gamepads.RemoveAt(Gamepads.Count - 1);
			}
			foreach(GamepadTestItem item in Gamepads) {
				item.RefreshState(globalDeadzoneSize, overrides);
			}
			HasPads = Gamepads.Count > 0;
			ShowNoPadsHint = !HasPads;
		}
	}

	//One connected pad as shown by the Test tab. Constructing an item reads no
	//device state; RefreshState() fills everything from the interop layer.
	public partial class GamepadTestItem : DisposableViewModel
	{
		public uint Index { get; }

		[ObservableProperty] public partial string Name { get; set; } = "";
		[ObservableProperty] public partial string Backend { get; set; } = "";
		[ObservableProperty] public partial uint Slot { get; set; }
		[ObservableProperty] public partial string VendorId { get; set; } = "";
		[ObservableProperty] public partial string ProductId { get; set; } = "";
		[ObservableProperty] public partial uint VendorIdValue { get; set; }
		[ObservableProperty] public partial uint ProductIdValue { get; set; }
		[ObservableProperty] public partial bool HasRumble { get; set; }
		[ObservableProperty] public partial string InfoText { get; set; } = "";

		//Per-device deadzone (PRD I.3): the pad's own deadzone size when an
		//override exists for its VID:PID, else the global ControllerDeadzoneSize.
		//IsUsingPerDeviceDeadzone distinguishes "override set" from "fell back to
		//global" even when the two happen to be equal; the 0-4 toggle buttons bind
		//to IsDz0..IsDz4, and SetDeadzone/ClearDeadzone persist via InputConfig.
		[ObservableProperty] public partial uint EffectiveDeadzoneSize { get; set; }
		[ObservableProperty] public partial uint GlobalDeadzoneSize { get; set; }
		[ObservableProperty] public partial bool IsUsingPerDeviceDeadzone { get; set; }
		public bool IsDz0 => EffectiveDeadzoneSize == 0;
		public bool IsDz1 => EffectiveDeadzoneSize == 1;
		public bool IsDz2 => EffectiveDeadzoneSize == 2;
		public bool IsDz3 => EffectiveDeadzoneSize == 3;
		public bool IsDz4 => EffectiveDeadzoneSize == 4;

		public List<GamepadButtonState> Buttons { get; } = new();
		[ObservableProperty] public partial int LeftX { get; set; }
		[ObservableProperty] public partial int LeftY { get; set; }
		[ObservableProperty] public partial int RightX { get; set; }
		[ObservableProperty] public partial int RightY { get; set; }

		//Stick diagnostics (PRD I.1 follow-up + I.3): the deadzone ring, the live
		//dot, magnitude, drift and circularity readouts for the left stick. The
		//ring geometry and the diagnostic math live in UI/Logic (host-free,
		//unit-tested); this VM only maps the raw axes to ring pixels and labels.
		public double LeftStickRingSize => RingRadius * 2;
		public double LeftStickDotSize => DotSize;
		[ObservableProperty] public partial double LeftStickDeadzoneSize { get; set; }
		[ObservableProperty] public partial Thickness LeftStickDotMargin { get; set; }
		[ObservableProperty] public partial string LeftStickReadout { get; set; } = "";
		[ObservableProperty] public partial bool IsDrifting { get; set; }
		[ObservableProperty] public partial bool HasCircularityResult { get; set; }
		[ObservableProperty] public partial string CircularityText { get; set; } = "";

		private const double RingRadius = 36;
		private const double DotSize = 8;
		private readonly GamepadCircularity _circularity = new();
		private readonly GamepadDriftDetector _drift = new();

		private static readonly string[] _buttonNames = {
			"A", "B", "X", "Y", "LB", "RB", "Menu", "Options",
			"DUp", "DDown", "DLeft", "DRight", "LT", "RT", "L3", "R3",
			"LUp", "LDown", "LLeft", "LRight", "RUp", "RDown", "RLeft", "RRight"
		};

		private DispatcherTimer? _rumbleStopTimer;

		public GamepadTestItem(uint index)
		{
			Index = index;
			for(int i = 0; i < _buttonNames.Length; i++) {
				Buttons.Add(new GamepadButtonState(_buttonNames[i]));
			}
		}

		public void RefreshState(uint globalDeadzoneSize, IReadOnlyList<DeviceDeadzoneOverride> overrides)
		{
			if(InputApi.GetGamepadInfo(Index, out GamepadInfo info)) {
				Name = info.Name;
				Backend = info.Backend.ToString();
				Slot = info.Slot;
				VendorId = info.VendorId.ToString("X4");
				ProductId = info.ProductId.ToString("X4");
				VendorIdValue = info.VendorId;
				ProductIdValue = info.ProductId;
				HasRumble = info.HasRumble;
				InfoText = $"{Backend} · Pad{Slot + 1} · VID:{VendorId} · PID:{ProductId}";
			}

			//Resolve the effective deadzone from the per-device overrides before
			//rendering the ring, so a pad with its own setting shows that ring.
			GlobalDeadzoneSize = globalDeadzoneSize;
			IsUsingPerDeviceDeadzone = PerDeviceDeadzone.HasOverride(overrides, VendorIdValue, ProductIdValue);
			EffectiveDeadzoneSize = PerDeviceDeadzone.Resolve(globalDeadzoneSize, overrides, VendorIdValue, ProductIdValue);

			if(InputApi.GetGamepadState(Index, out GamepadState state)) {
				for(int i = 0; i < Buttons.Count; i++) {
					Buttons[i].IsPressed = (state.Buttons & (1u << i)) != 0;
				}
				LeftX = state.Axes[0];
				LeftY = state.Axes[1];
				RightX = state.Axes[2];
				RightY = state.Axes[3];
			}

			UpdateStickDiagnostics(EffectiveDeadzoneSize);
		}

		partial void OnEffectiveDeadzoneSizeChanged(uint value)
		{
			OnPropertyChanged(nameof(IsDz0));
			OnPropertyChanged(nameof(IsDz1));
			OnPropertyChanged(nameof(IsDz2));
			OnPropertyChanged(nameof(IsDz3));
			OnPropertyChanged(nameof(IsDz4));
		}

		//Persist a per-device deadzone override for this pad (PRD I.3). Reassigning
		//InputConfig.PerDeviceDeadzones raises the recursive observer that calls
		//InputConfig.ApplyConfig() - the same lifecycle as the global slider. A pad
		//with no identity (0:0000) cannot be keyed, so it is ignored.
		[RelayCommand]
		private void SetDeadzone(string sizeText)
		{
			if(!uint.TryParse(sizeText, out uint size) || (VendorIdValue == 0 && ProductIdValue == 0)) {
				return;
			}
			uint clamped = PerDeviceDeadzone.ClampSize(size);
			List<DeviceDeadzoneOverride> overrides = new(ConfigManager.Config.Input.PerDeviceDeadzones);
			overrides.RemoveAll(o => o.VendorId == VendorIdValue && o.ProductId == ProductIdValue);
			overrides.Add(new DeviceDeadzoneOverride(VendorIdValue, ProductIdValue, clamped));
			ConfigManager.Config.Input.PerDeviceDeadzones = overrides;
			EffectiveDeadzoneSize = clamped;
			IsUsingPerDeviceDeadzone = true;
		}

		[RelayCommand]
		private void ClearDeadzone()
		{
			if(VendorIdValue == 0 && ProductIdValue == 0) {
				return;
			}
			List<DeviceDeadzoneOverride> overrides = new(ConfigManager.Config.Input.PerDeviceDeadzones);
			overrides.RemoveAll(o => o.VendorId == VendorIdValue && o.ProductId == ProductIdValue);
			ConfigManager.Config.Input.PerDeviceDeadzones = overrides;
			EffectiveDeadzoneSize = GlobalDeadzoneSize;
			IsUsingPerDeviceDeadzone = false;
		}

		private void UpdateStickDiagnostics(uint deadzoneSize)
		{
			int deadzoneUnits = GamepadStickDiagnostics.DeadzoneUnits(deadzoneSize);
			double nx = Math.Clamp(LeftX / (double)GamepadCircularity.MaxAxisValue, -1, 1);
			double ny = Math.Clamp(LeftY / (double)GamepadCircularity.MaxAxisValue, -1, 1);
			double magnitude = Math.Sqrt(nx * nx + ny * ny);

			LeftStickDeadzoneSize = 2 * deadzoneUnits / (double)GamepadCircularity.MaxAxisValue * RingRadius;
			LeftStickDotMargin = new Thickness(
				RingRadius + nx * RingRadius - DotSize / 2,
				RingRadius - ny * RingRadius - DotSize / 2,
				0, 0);
			LeftStickReadout = $"X: {LeftX}  Y: {LeftY}  mag {magnitude * 100:0}%";

			_circularity.AddSample((short)LeftX, (short)LeftY, deadzoneUnits);
			HasCircularityResult = _circularity.HasResult;
			CircularityText = HasCircularityResult
				? $"{_circularity.Score * 100:0}% · {CategoryLabel(_circularity.Category)} ({_circularity.SampleCount} samples)"
				: "";

			_drift.Update((int)Math.Round(magnitude * GamepadCircularity.MaxAxisValue), deadzoneUnits);
			IsDrifting = _drift.IsDrifting;
		}

		private static string CategoryLabel(GamepadCircularityCategory category)
		{
			switch(category) {
				case GamepadCircularityCategory.Excellent: return ResourceHelper.GetMessage("lblCircularityExcellent");
				case GamepadCircularityCategory.Good: return ResourceHelper.GetMessage("lblCircularityGood");
				case GamepadCircularityCategory.Fair: return ResourceHelper.GetMessage("lblCircularityFair");
				default: return ResourceHelper.GetMessage("lblCircularityPoor");
			}
		}

		[RelayCommand]
		private void ResetCircularity()
		{
			_circularity.Reset();
			HasCircularityResult = false;
			CircularityText = "";
		}

		[RelayCommand]
		private void TestRumble()
		{
			if(!HasRumble) {
				return;
			}
			InputApi.TestForceFeedback(Index, 0x8000, 0x8000);
			//Cut the rumble after a short pulse so the tester does not leave the
			//pad vibrating after the user leaves the tab.
			_rumbleStopTimer?.Stop();
			_rumbleStopTimer = new DispatcherTimer();
			_rumbleStopTimer.Interval = TimeSpan.FromMilliseconds(300);
			_rumbleStopTimer.Tick += (s, e) => {
				_rumbleStopTimer?.Stop();
				_rumbleStopTimer = null;
				InputApi.TestForceFeedback(Index, 0, 0);
			};
			_rumbleStopTimer.Start();
		}
	}

	public partial class GamepadButtonState : ObservableObject
	{
		private static readonly IBrush _pressedBrush = new SolidColorBrush(Color.FromArgb(0xCC, 0x33, 0xCC, 0x66));
		private static readonly IBrush _idleBrush = new SolidColorBrush(Color.FromArgb(0x22, 0x22, 0x22, 0x22));

		public string Label { get; }
		[ObservableProperty] public partial bool IsPressed { get; set; }
		[ObservableProperty] public partial IBrush IsPressedBrush { get; set; } = _idleBrush;

		public GamepadButtonState(string label)
		{
			Label = label;
		}

		partial void OnIsPressedChanged(bool value)
		{
			IsPressedBrush = value ? _pressedBrush : _idleBrush;
		}
	}
}

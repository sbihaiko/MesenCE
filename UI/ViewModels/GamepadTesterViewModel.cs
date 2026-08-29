using Avalonia.Media;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Mesen.Interop;
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
			while(Gamepads.Count < count) {
				Gamepads.Add(new GamepadTestItem((uint)Gamepads.Count));
			}
			while(Gamepads.Count > count) {
				Gamepads.RemoveAt(Gamepads.Count - 1);
			}
			foreach(GamepadTestItem item in Gamepads) {
				item.RefreshState();
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
		[ObservableProperty] public partial bool HasRumble { get; set; }
		[ObservableProperty] public partial string InfoText { get; set; } = "";

		public List<GamepadButtonState> Buttons { get; } = new();
		[ObservableProperty] public partial int LeftX { get; set; }
		[ObservableProperty] public partial int LeftY { get; set; }
		[ObservableProperty] public partial int RightX { get; set; }
		[ObservableProperty] public partial int RightY { get; set; }

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

		public void RefreshState()
		{
			if(InputApi.GetGamepadInfo(Index, out GamepadInfo info)) {
				Name = info.Name;
				Backend = info.Backend.ToString();
				Slot = info.Slot;
				VendorId = info.VendorId.ToString("X4");
				ProductId = info.ProductId.ToString("X4");
				HasRumble = info.HasRumble;
				InfoText = $"{Backend} · Pad{Slot + 1} · VID:{VendorId} · PID:{ProductId}";
			}

			if(InputApi.GetGamepadState(Index, out GamepadState state)) {
				for(int i = 0; i < Buttons.Count; i++) {
					Buttons[i].IsPressed = (state.Buttons & (1u << i)) != 0;
				}
				LeftX = state.Axes[0];
				LeftY = state.Axes[1];
				RightX = state.Axes[2];
				RightY = state.Axes[3];
			}
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

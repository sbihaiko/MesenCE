using System;
using System.Collections.Generic;

namespace Mesen.Logic
{
	//Host-free per-device deadzone resolution for the input tester (PRD I.3).
	//A pad is keyed by its (VendorId, ProductId); when an override exists for
	//that device the effective deadzone size (0-4) is the override's, otherwise
	//the global ControllerDeadzoneSize applies. Host-side only: the core input
	//path keeps using the global setting (EmuSettings.GetControllerDeadzoneRatio
	//has no caller today), so this governs the tester's ring/drift display and
	//the per-device config, not core input processing. Kept free of
	//Avalonia/EmuApi so it dual-compiles into UI.Tests.
	public record DeviceDeadzoneOverride(uint VendorId, uint ProductId, uint DeadzoneSize)
	{
		public const uint MinSize = 0;
		public const uint MaxSize = 4;
	}

	public static class PerDeviceDeadzone
	{
		public static uint ClampSize(uint size)
		{
			if(size < DeviceDeadzoneOverride.MinSize) {
				return DeviceDeadzoneOverride.MinSize;
			}
			if(size > DeviceDeadzoneOverride.MaxSize) {
				return DeviceDeadzoneOverride.MaxSize;
			}
			return size;
		}

		//First override matching the exact (VendorId, ProductId) wins; any size
		//is clamped to 0-4 so a malformed config entry cannot produce a ring
		//larger than the travel or a negative one.
		public static uint Resolve(
			uint globalSize,
			IReadOnlyList<DeviceDeadzoneOverride>? overrides,
			uint vendorId,
			uint productId)
		{
			if(overrides != null) {
				foreach(DeviceDeadzoneOverride o in overrides) {
					if(o != null && o.VendorId == vendorId && o.ProductId == productId) {
						return ClampSize(o.DeadzoneSize);
					}
				}
			}
			return ClampSize(globalSize);
		}

		public static bool HasOverride(
			IReadOnlyList<DeviceDeadzoneOverride>? overrides,
			uint vendorId,
			uint productId)
		{
			if(overrides != null) {
				foreach(DeviceDeadzoneOverride o in overrides) {
					if(o != null && o.VendorId == vendorId && o.ProductId == productId) {
						return true;
					}
				}
			}
			return false;
		}
	}
}

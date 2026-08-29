using Mesen.Logic;
using System.Collections.Generic;
using Xunit;

namespace Mesen.Tests.Input
{
	//Host-free per-device deadzone resolution (PRD I.3): a pad keyed by
	//(VendorId, ProductId) uses its own override when one exists, else the
	//global setting; every size is clamped to 0-4 so a malformed config entry
	//cannot produce an out-of-range ring.
	public class PerDeviceDeadzoneTests
	{
		private static readonly DeviceDeadzoneOverride[] _overrides = {
			new(0x045E, 0x028E, 3), //Xbox 360 pad -> size 3
			new(0x057E, 0x2009, 0), //Switch Pro -> size 0
		};

		[Fact]
		public void Resolve_NoOverrides_UsesGlobal()
		{
			Assert.Equal(2u, PerDeviceDeadzone.Resolve(2, _overrides, 0x1234, 0x5678));
			Assert.Equal(2u, PerDeviceDeadzone.Resolve(2, null, 0x045E, 0x028E));
		}

		[Fact]
		public void Resolve_EmptyOverrides_UsesGlobal()
		{
			Assert.Equal(2u, PerDeviceDeadzone.Resolve(2, new List<DeviceDeadzoneOverride>(), 0x045E, 0x028E));
		}

		[Fact]
		public void Resolve_MatchingOverride_Wins()
		{
			Assert.Equal(3u, PerDeviceDeadzone.Resolve(2, _overrides, 0x045E, 0x028E));
			Assert.Equal(0u, PerDeviceDeadzone.Resolve(2, _overrides, 0x057E, 0x2009));
		}

		[Fact]
		public void Resolve_PartialMatch_FallsBackToGlobal()
		{
			//Same vendor, different product -> no match.
			Assert.Equal(2u, PerDeviceDeadzone.Resolve(2, _overrides, 0x045E, 0xFFFF));
			//Same product, different vendor -> no match.
			Assert.Equal(2u, PerDeviceDeadzone.Resolve(2, _overrides, 0xFFFF, 0x028E));
		}

		[Fact]
		public void Resolve_FirstMatchWins()
		{
			var dupes = new List<DeviceDeadzoneOverride> {
				new(0x045E, 0x028E, 1),
				new(0x045E, 0x028E, 4),
			};
			Assert.Equal(1u, PerDeviceDeadzone.Resolve(2, dupes, 0x045E, 0x028E));
		}

		[Fact]
		public void Resolve_ClampsOverrideSizeToMax()
		{
			var bad = new List<DeviceDeadzoneOverride> { new(0x045E, 0x028E, 9) };
			Assert.Equal(4u, PerDeviceDeadzone.Resolve(2, bad, 0x045E, 0x028E));
		}

		[Fact]
		public void Resolve_ClampsGlobalSizeToMax()
		{
			Assert.Equal(4u, PerDeviceDeadzone.Resolve(9, _overrides, 0x1234, 0x5678));
		}

		[Fact]
		public void ClampSize_Boundaries()
		{
			Assert.Equal(0u, PerDeviceDeadzone.ClampSize(0));
			Assert.Equal(2u, PerDeviceDeadzone.ClampSize(2));
			Assert.Equal(4u, PerDeviceDeadzone.ClampSize(4));
			Assert.Equal(4u, PerDeviceDeadzone.ClampSize(5));
			Assert.Equal(4u, PerDeviceDeadzone.ClampSize(uint.MaxValue));
		}

		[Fact]
		public void HasOverride_MatchingDevice()
		{
			Assert.True(PerDeviceDeadzone.HasOverride(_overrides, 0x045E, 0x028E));
			Assert.True(PerDeviceDeadzone.HasOverride(_overrides, 0x057E, 0x2009));
		}

		[Fact]
		public void HasOverride_NoMatch()
		{
			Assert.False(PerDeviceDeadzone.HasOverride(_overrides, 0x045E, 0xFFFF));
			Assert.False(PerDeviceDeadzone.HasOverride(_overrides, 0x1234, 0x5678));
			Assert.False(PerDeviceDeadzone.HasOverride(null, 0x045E, 0x028E));
			Assert.False(PerDeviceDeadzone.HasOverride(new List<DeviceDeadzoneOverride>(), 0x045E, 0x028E));
		}

		[Fact]
		public void DeviceZeroZero_NeverMatches_UnlessOverrideHasIt()
		{
			//The tester guards against creating an override for 0:0000; an
			//explicit one (shouldn't happen) would still resolve.
			Assert.Equal(2u, PerDeviceDeadzone.Resolve(2, _overrides, 0, 0));
			var explicitZero = new List<DeviceDeadzoneOverride> { new(0, 0, 1) };
			Assert.Equal(1u, PerDeviceDeadzone.Resolve(2, explicitZero, 0, 0));
		}
	}
}

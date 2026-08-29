using Mesen.Logic;
using System;
using Xunit;

namespace Mesen.Tests.Input
{
	//Host-free stick diagnostics for the input tester (PRD I.1/I.3):
	//GamepadStickDiagnostics.DeadzoneRatio mirrors Core's EmuSettings mapping,
	//GamepadDriftDetector flags a stick that stays beyond the deadzone for a
	//sustained run of samples, and GamepadCircularity scores the traced shape
	//(coverage^2 x radial consistency) from synthetic stick samples.
	public class GamepadDiagnosticsTests
	{
		[Theory]
		[InlineData(0u, 0.5)]
		[InlineData(1u, 0.75)]
		[InlineData(2u, 1.0)]
		[InlineData(3u, 1.25)]
		[InlineData(4u, 1.5)]
		[InlineData(5u, 1.0)] //unknown sizes fall back to 1 (mirrors the Core switch default)
		public void DeadzoneRatio_MapsSizeToMultiplier(uint size, double expected)
		{
			Assert.Equal(expected, GamepadStickDiagnostics.DeadzoneRatio(size), 3);
		}

		[Fact]
		public void DeadzoneUnits_DefaultSize_IsHalfRange()
		{
			//DirectInput canonical: (int)(short.MaxValue / 2.0 * ratio), ratio 1.0 at size 2.
			Assert.Equal(16383, GamepadStickDiagnostics.DeadzoneUnits(2));
			Assert.Equal(8191, GamepadStickDiagnostics.DeadzoneUnits(0));
			Assert.Equal(24575, GamepadStickDiagnostics.DeadzoneUnits(4));
		}

		[Fact]
		public void Circularity_PerfectCircle_ScoresExcellent()
		{
			GamepadCircularity c = new GamepadCircularity();
			AddSamples(c, angles: 64, radius: 1.0, deadzoneUnits: 16383);

			Assert.True(c.HasResult);
			Assert.Equal(1.0, c.Coverage, 3);
			Assert.True(c.Score >= 0.85);
			Assert.Equal(GamepadCircularityCategory.Excellent, c.Category);
		}

		[Fact]
		public void Circularity_LineThroughCenter_IsPoor()
		{
			//A stick that only travels along one axis covers 2 of 16 sectors.
			GamepadCircularity c = new GamepadCircularity();
			for(int i = 0; i < 60; i++) {
				int sign = i % 2 == 0 ? 1 : -1;
				c.AddSample((short)(sign * GamepadCircularity.MaxAxisValue), 0, 16383);
			}

			Assert.True(c.HasResult);
			Assert.True(c.Coverage < 0.25);
			Assert.True(c.Score < 0.1);
			Assert.Equal(GamepadCircularityCategory.Poor, c.Category);
		}

		[Fact]
		public void Circularity_SquareGate_IsGood()
		{
			//A square gate reaches radius 1.0 on the axes and ~1.414 at 45 deg
			//(both axes saturate at short.MaxValue): full coverage, radial
			//consistency ~0.707 -> Good (score ~0.707). Sampled at sector centers
			//so int16 quantization never pushes a sample across a sector boundary.
			GamepadCircularity c = new GamepadCircularity();
			for(int rep = 0; rep < 4; rep++) {
				for(int k = 0; k < 16; k++) {
					double angle = (k + 0.5) * Math.PI / 8;
					double cos = Math.Cos(angle);
					double sin = Math.Sin(angle);
					//Distance to the unit square's edge in that direction.
					double r = 1 / Math.Max(Math.Abs(cos), Math.Abs(sin));
					AddSample(c, angle, r, 16383);
				}
			}

			Assert.True(c.HasResult);
			Assert.Equal(1.0, c.Coverage, 3);
			Assert.True(c.Score >= 0.70 && c.Score < 0.85);
			Assert.Equal(GamepadCircularityCategory.Good, c.Category);
		}

		[Fact]
		public void Circularity_DeadQuadrant_IsFair()
		{
			//Only 12 of 16 sectors visited (a dead region): coverage 0.75,
			//consistency 1.0 -> score 0.5625 -> Fair. Sampled at sector centers.
			GamepadCircularity c = new GamepadCircularity();
			for(int rep = 0; rep < 4; rep++) {
				for(int k = 0; k < 12; k++) {
					AddSample(c, (k + 0.5) * Math.PI / 8, 1.0, 16383);
				}
			}

			Assert.True(c.HasResult);
			Assert.Equal(0.75, c.Coverage, 3);
			Assert.True(c.Score >= 0.5 && c.Score < 0.7);
			Assert.Equal(GamepadCircularityCategory.Fair, c.Category);
		}

		[Fact]
		public void Circularity_TooFewSamples_IsNotEnough()
		{
			GamepadCircularity c = new GamepadCircularity();
			for(int i = 0; i < 20; i++) {
				AddSample(c, i * Math.PI / 10, 1.0, 16383);
			}

			Assert.False(c.HasResult);
			Assert.Equal(GamepadCircularityCategory.NotEnoughSamples, c.Category);
			Assert.Equal(0, c.Score, 3);
		}

		[Fact]
		public void Circularity_DeadzoneSamplesAreIgnored()
		{
			GamepadCircularity c = new GamepadCircularity();
			//radius 0.4 is inside the 0.5 deadzone fraction - must not count.
			for(int i = 0; i < 60; i++) {
				c.AddSample((short)(0.4 * GamepadCircularity.MaxAxisValue), 0, 16383);
			}

			Assert.Equal(0, c.SampleCount);
			Assert.False(c.HasResult);
			Assert.Equal(0, c.Coverage, 3);
		}

		[Fact]
		public void DriftDetector_RequiresSustainedRunThenResets()
		{
			GamepadDriftDetector d = new GamepadDriftDetector();
			for(int i = 0; i < GamepadDriftDetector.SustainedSamples - 1; i++) {
				d.Update(20000, 16383);
				Assert.False(d.IsDrifting);
			}
			d.Update(20000, 16383);
			Assert.True(d.IsDrifting);

			//Returning inside the deadzone clears the run immediately.
			d.Update(1000, 16383);
			Assert.False(d.IsDrifting);
		}

		private static void AddSamples(GamepadCircularity c, int angles, double radius, int deadzoneUnits)
		{
			for(int i = 0; i < angles; i++) {
				AddSample(c, i * 2 * Math.PI / angles, radius, deadzoneUnits);
			}
		}

		private static void AddSample(GamepadCircularity c, double angle, double radius, int deadzoneUnits)
		{
			short x = (short)(radius * GamepadCircularity.MaxAxisValue * Math.Cos(angle));
			short y = (short)(radius * GamepadCircularity.MaxAxisValue * Math.Sin(angle));
			c.AddSample(x, y, deadzoneUnits);
		}
	}
}

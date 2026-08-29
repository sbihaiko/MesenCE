using System;

namespace Mesen.Logic
{
	//Host-free circularity estimator for the input tester (PRD I.3). Feed it the
	//raw int16 stick samples as the user rotates the stick; it buckets them by
	//angle into 16 sectors and tracks the max deflection radius reached in each.
	//The score combines coverage (how many sectors the stick actually visited)
	//with radial consistency (how uniform the reach is across those sectors):
	//score = coverage^2 * radialConsistency, in [0,1]. A healthy stick tracing a
	//full circle scores high; a stick that cannot reach one direction (low
	//coverage) or is flattened (low consistency) scores lower. Samples inside the
	//deadzone are ignored - the center region carries no shape information.
	//Kept free of Avalonia/EmuApi so it dual-compiles into UI.Tests.
	public enum GamepadCircularityCategory
	{
		NotEnoughSamples,
		Excellent,
		Good,
		Fair,
		Poor
	}

	public class GamepadCircularity
	{
		public const int SectorCount = 16;
		//~0.8s of rotation at the tester's 16ms poll rate - enough for a full
		//revolution to visit every sector, so a short flick never reads Poor.
		public const int MinSamplesForScore = 48;
		public const int MaxAxisValue = short.MaxValue;

		private readonly double[] _sectorMaxRadius = new double[SectorCount];

		public int SampleCount { get; private set; }
		public double MaxRadius { get; private set; }

		public void AddSample(short x, short y, int deadzoneUnits)
		{
			double nx = x / (double)MaxAxisValue;
			double ny = y / (double)MaxAxisValue;
			double radius = Math.Sqrt(nx * nx + ny * ny);
			if(radius < deadzoneUnits / (double)MaxAxisValue) {
				return;
			}

			SampleCount++;
			MaxRadius = Math.Max(MaxRadius, radius);

			double angle = Math.Atan2(ny, nx);
			if(angle < 0) {
				angle += Math.PI * 2;
			}
			int sector = (int)(angle / (Math.PI * 2) * SectorCount) % SectorCount;
			_sectorMaxRadius[sector] = Math.Max(_sectorMaxRadius[sector], radius);
		}

		public void Reset()
		{
			SampleCount = 0;
			MaxRadius = 0;
			Array.Clear(_sectorMaxRadius, 0, _sectorMaxRadius.Length);
		}

		public bool HasResult => SampleCount >= MinSamplesForScore;

		//Fraction of the 16 sectors the stick has actually visited.
		public double Coverage
		{
			get {
				int visited = 0;
				for(int i = 0; i < _sectorMaxRadius.Length; i++) {
					if(_sectorMaxRadius[i] > 0) {
						visited++;
					}
				}
				return visited / (double)SectorCount;
			}
		}

		//min/max of the max radius reached per visited sector - how uniform the
		//reach is across directions. 1.0 = the same extent everywhere.
		public double RadialConsistency
		{
			get {
				double min = double.MaxValue;
				double max = 0;
				for(int i = 0; i < _sectorMaxRadius.Length; i++) {
					if(_sectorMaxRadius[i] > 0) {
						min = Math.Min(min, _sectorMaxRadius[i]);
						max = Math.Max(max, _sectorMaxRadius[i]);
					}
				}
				return max <= 0 ? 0 : min / max;
			}
		}

		public double Score => HasResult ? Coverage * Coverage * RadialConsistency : 0;

		public GamepadCircularityCategory Category
		{
			get {
				if(!HasResult) {
					return GamepadCircularityCategory.NotEnoughSamples;
				}
				double score = Score;
				if(score >= 0.85) {
					return GamepadCircularityCategory.Excellent;
				}
				if(score >= 0.7) {
					return GamepadCircularityCategory.Good;
				}
				if(score >= 0.5) {
					return GamepadCircularityCategory.Fair;
				}
				return GamepadCircularityCategory.Poor;
			}
		}
	}
}

using Avalonia.Media;
using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using Mesen.Utilities;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Mesen.ViewModels
{
	//F5.4d: before/after preview for the HD Pack Builder. Enumerates every
	//sheet/screen PNG in the pack folder that has a *.orig.png reference twin
	//(the pixel-exact, unfiltered capture F5.4a′ writes next to each processed
	//PNG) and shows the pair side by side, so the artist sees the raw capture
	//before and the current sheet/screen after.
	public class HdPackImagePair
	{
		public string AfterPath { get; }
		public string BeforePath { get; }

		public HdPackImagePair(string afterPath, string beforePath)
		{
			AfterPath = afterPath;
			BeforePath = beforePath;
		}

		public override string ToString()
		{
			return Path.GetFileName(AfterPath);
		}
	}

	public partial class HdPackPreviewViewModel : DisposableViewModel
	{
		[ObservableProperty] public partial List<HdPackImagePair> ImagePairs { get; set; } = new();
		[ObservableProperty] public partial HdPackImagePair? SelectedPair { get; set; }
		[ObservableProperty] public partial IImage? BeforeImage { get; set; }
		[ObservableProperty] public partial IImage? AfterImage { get; set; }

		public HdPackPreviewViewModel(string saveFolder)
		{
			ImagePairs = EnumeratePairs(saveFolder).ToList();
			AddDisposable(this.ObserveProp(nameof(SelectedPair), () => UpdateImages()));
			SelectedPair = ImagePairs.FirstOrDefault();
		}

		private void UpdateImages()
		{
			BeforeImage = LoadBitmap(SelectedPair?.BeforePath);
			AfterImage = LoadBitmap(SelectedPair?.AfterPath);
		}

		private static IImage? LoadBitmap(string? path)
		{
			if(string.IsNullOrEmpty(path) || !File.Exists(path)) {
				return null;
			}
			try {
				return new Bitmap(path);
			} catch {
				return null;
			}
		}

		private static IEnumerable<HdPackImagePair> EnumeratePairs(string saveFolder)
		{
			//Sheets live at the pack root (Chr_*.png); screens under backgrounds/
			//(screenNNN.png). Each processed PNG with a *.orig.png twin is a pair.
			foreach(string dir in new[] { saveFolder, Path.Combine(saveFolder, "backgrounds") }) {
				if(!Directory.Exists(dir)) {
					continue;
				}
				foreach(string orig in Directory.EnumerateFiles(dir, "*.orig.png")) {
					string after = orig.Substring(0, orig.Length - ".orig.png".Length) + ".png";
					if(File.Exists(after)) {
						yield return new HdPackImagePair(after, orig);
					}
				}
			}
		}
	}
}

using Avalonia.Controls;
using Avalonia.Markup.Xaml;
using Mesen.ViewModels;
using System;

namespace Mesen.Windows
{
	//F5.4d: before/after preview (see HdPackPreviewViewModel). Shown from the HD
	//Pack Builder's "Before/After" button - a unique, non-modal window.
	public class HdPackPreviewWindow : MesenWindow
	{
		private HdPackPreviewViewModel _model;

		[Obsolete("For designer only")]
		public HdPackPreviewWindow() : this("") { }

		public HdPackPreviewWindow(string saveFolder)
		{
			_model = new HdPackPreviewViewModel(saveFolder);
			DataContext = _model;

			InitializeComponent();
		}

		protected override void OnClosing(WindowClosingEventArgs e)
		{
			base.OnClosing(e);
			_model.Dispose();
		}

		private void InitializeComponent()
		{
			AvaloniaXamlLoader.Load(this);
		}
	}
}

using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Mesen.Config;
using Mesen.Logic;
using Mesen.Services;
using Mesen.Utilities;
using Mesen.ViewModels;
using System;
using System.Threading.Tasks;

namespace Mesen.Windows
{
	public class EnhancementPacksWindow : MesenWindow
	{
		private EnhancementPacksViewModel _model;

		public EnhancementPacksWindow()
		{
			_model = new EnhancementPacksViewModel();
			DataContext = _model;

			InitializeComponent();
		}

		private void InitializeComponent()
		{
			AvaloniaXamlLoader.Load(this);
		}

		protected override void OnClosing(WindowClosingEventArgs e)
		{
			base.OnClosing(e);
			_model.Dispose();
		}

		private async void Ok_OnClick(object sender, RoutedEventArgs e)
		{
			_model.ApplyChanges();
			//Toggles apply on the next load (same rule as EnableHdPacks) - offer
			//the power cycle right away, like InstallHdPack does
			if(await MesenMsgBox.Show(this, "EnhancementPacksConfirmReset", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) == DialogResult.OK) {
				LoadRomHelper.PowerCycle();
			}
			Close();
		}

		private void Cancel_OnClick(object sender, RoutedEventArgs e)
		{
			Close();
		}

		private async void Install_OnClick(object sender, RoutedEventArgs e)
		{
			string? result = await _model.InstallPack(this);
			if(result == null) {
				return; //cancelled
			}
			if(result.Length > 0) {
				await MesenMsgBox.Show(this, result, MessageBoxButtons.OK, MessageBoxIcon.Error);
				return;
			}
			if(await MesenMsgBox.Show(this, "InstallMepPackConfirmReset", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) == DialogResult.OK) {
				_model.ApplyChanges();
				LoadRomHelper.PowerCycle();
			}
			_model.Refresh();
		}

		//ADR-0147: explicit user action - discard local edits to the installed
		//catalog pack and re-materialize it from the original (Restore). The
		//editor edits <Game>/mep/, this restores it fresh from the catalog zip.
		private async void Restore_OnClick(object sender, RoutedEventArgs e)
		{
			(bool ok, string error) = await CommunityPackInstallService.RestoreInstalledPack();
			if(!ok) {
				await MesenMsgBox.Show(this, error, MessageBoxButtons.OK, MessageBoxIcon.Error);
				return;
			}
			_model.Refresh();
			if(await MesenMsgBox.Show(this, "InstallMepPackConfirmReset", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) == DialogResult.OK) {
				_model.ApplyChanges();
				LoadRomHelper.PowerCycle();
			}
		}
	}
}

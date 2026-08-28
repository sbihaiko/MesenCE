using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Mesen.Config;
using Mesen.Logic;
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

		//ADR-0138 §38: gates the very first automatic community-pack download
		//behind an explicit Yes/No prompt, on top of the AutoInstallCommunityPacks
		//toggle above. Called from the ROM-load hook (not from opening this
		//settings window) before CommunityPackInstallService attempts a download;
		//CommunityPackConsentState.Evaluate is the single source of truth for
		//whether the dialog is due and whether a download may proceed.
		//
		//CommunityPackAutoInstallConsentGiven is recorded as soon as the dialog
		//has been shown once, regardless of the answer, so the user is never
		//asked twice - a "No" answer also turns AutoInstallCommunityPacks off so
		//no download is attempted until the user re-enables it manually.
		public static async Task<bool> EnsureCommunityPackAutoInstallConsent()
		{
			EnhancementPackConfig config = ConfigManager.Config.EnhancementPacks;
			CommunityPackConsentDecision decision = CommunityPackConsentState.Evaluate(
				config.AutoInstallCommunityPacks,
				config.CommunityPackAutoInstallConsentGiven
			);

			if(!decision.MustShowConsentDialog) {
				return decision.CanDownloadNow;
			}

			DialogResult result = await MesenMsgBox.Show(null, "CommunityPackAutoInstallConsent", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
			bool consented = result == DialogResult.Yes;

			config.CommunityPackAutoInstallConsentGiven = true;
			if(!consented) {
				config.AutoInstallCommunityPacks = false;
			}
			config.ApplyConfig();
			ConfigManager.Config.Save();

			return consented;
		}
	}
}

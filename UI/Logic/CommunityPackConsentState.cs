namespace Mesen.Logic
{
	//ADR-0138 §38 (F6.4b): gates the FIRST automatic community-pack download
	//behind an explicit user consent, on top of the AutoInstallCommunityPacks
	//toggle (default true, EnhancementPackConfig.cs). Consent is recorded once
	//(EnhancementPackConfig.CommunityPackAutoInstallConsentGiven, default
	//false) and then never asked again while it stays true - the toggle alone
	//controls every later download.
	//
	//Host-free (BCL only) per the UI/Logic/ firewall: this class only decides
	//what should happen next; the actual dialog, the persisted flag's storage,
	//and the download itself all live in the caller
	//(UI/Services/CommunityPackInstallService.cs + the settings window).
	public readonly record struct CommunityPackConsentDecision(
		bool CanDownloadNow,
		bool MustShowConsentDialog
	);

	public static class CommunityPackConsentState
	{
		//autoInstallEnabled: EnhancementPackConfig.AutoInstallCommunityPacks.
		//consentGiven: EnhancementPackConfig.CommunityPackAutoInstallConsentGiven.
		//
		//Toggle off always wins: no download happens and no dialog is shown,
		//regardless of any consent recorded earlier (turning the toggle back on
		//later does NOT re-prompt, since consentGiven is a separate, sticky
		//flag - only the toggle gates further prompting).
		//Toggle on + no consent yet: the download is blocked until the
		//first-run consent dialog is shown and answered - this call never
		//marks consent as given itself, it only reports that showing the
		//dialog is the caller's next required step.
		//Toggle on + consent already recorded: the download may proceed with
		//no dialog.
		public static CommunityPackConsentDecision Evaluate(bool autoInstallEnabled, bool consentGiven)
		{
			if(!autoInstallEnabled) {
				return new CommunityPackConsentDecision(CanDownloadNow: false, MustShowConsentDialog: false);
			}

			if(!consentGiven) {
				return new CommunityPackConsentDecision(CanDownloadNow: false, MustShowConsentDialog: true);
			}

			return new CommunityPackConsentDecision(CanDownloadNow: true, MustShowConsentDialog: false);
		}
	}
}

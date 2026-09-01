namespace Mesen.Logic
{
	//ADR-0138 §38 (F6.4b) originally gated the FIRST automatic community-pack
	//download behind an explicit user consent. ADR-0146 supersedes that: every
	//community pack registered in a GitHub issue and accepted onto the
	//"MesenCE Community Packs" board (verdict accepted, label pack:valid, i.e.
	//a row in docs/community-packs.json) MUST auto-download/install/load
	//whenever possible. `AutoInstallCommunityPacks` is the single master
	//switch (default true); the first-run consent prompt and
	//`CommunityPackAutoInstallConsentGiven` are no longer consulted and are
	//inert for the auto-install path.
	//
	//Host-free (BCL only) per the UI/Logic/ firewall: this class only decides
	//what should happen next; the actual download, its storage, and the
	//settings master switch live in the caller
	//(UI/Services/CommunityPackInstallService.cs + EnhancementPackConfig).
	public readonly record struct CommunityPackConsentDecision(
		bool CanDownloadNow,
		bool MustShowConsentDialog
	);

	public static class CommunityPackConsentState
	{
		//autoInstallEnabled: EnhancementPackConfig.AutoInstallCommunityPacks.
		//consentGiven: kept only for signature stability (ADR-0138 §38 callers);
		//inert under ADR-0146 - ignored via `_ = consentGiven`.
		//
		//ADR-0146: the consent gate no longer blocks auto-install of accepted
		//catalog packs. Toggle off wins: no download, no prompt. Toggle on:
		//download proceeds (the pack auto-loads); the consent prompt is never
		//shown.
		public static CommunityPackConsentDecision Evaluate(bool autoInstallEnabled, bool consentGiven)
		{
			_ = consentGiven;
			if(!autoInstallEnabled) {
				return new CommunityPackConsentDecision(CanDownloadNow: false, MustShowConsentDialog: false);
			}
			return new CommunityPackConsentDecision(CanDownloadNow: true, MustShowConsentDialog: false);
		}
	}
}

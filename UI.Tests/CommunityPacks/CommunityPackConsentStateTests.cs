using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	// ADR-0138 §38 (F6.4b): coverage for the first-run consent gate extracted
	// into UI/Logic/CommunityPackConsentState.cs.
	public class CommunityPackConsentStateTests
	{
		[Fact]
		public void Evaluate_ToggleOn_NoConsentYet_RequiresDialogAndBlocksDownload()
		{
			CommunityPackConsentDecision decision = CommunityPackConsentState.Evaluate(
				autoInstallEnabled: true, consentGiven: false);

			Assert.False(decision.CanDownloadNow);
			Assert.True(decision.MustShowConsentDialog);
		}

		[Fact]
		public void Evaluate_ToggleOn_ConsentRecorded_AllowsDownloadWithNoDialog()
		{
			CommunityPackConsentDecision decision = CommunityPackConsentState.Evaluate(
				autoInstallEnabled: true, consentGiven: true);

			Assert.True(decision.CanDownloadNow);
			Assert.False(decision.MustShowConsentDialog);
		}

		[Fact]
		public void Evaluate_ToggleOff_ConsentGiven_NeverDownloadsAndNeverPrompts()
		{
			CommunityPackConsentDecision decision = CommunityPackConsentState.Evaluate(
				autoInstallEnabled: false, consentGiven: true);

			Assert.False(decision.CanDownloadNow);
			Assert.False(decision.MustShowConsentDialog);
		}

		[Fact]
		public void Evaluate_ToggleOff_NoConsent_NeverDownloadsAndNeverPrompts()
		{
			CommunityPackConsentDecision decision = CommunityPackConsentState.Evaluate(
				autoInstallEnabled: false, consentGiven: false);

			Assert.False(decision.CanDownloadNow);
			Assert.False(decision.MustShowConsentDialog);
		}
	}
}

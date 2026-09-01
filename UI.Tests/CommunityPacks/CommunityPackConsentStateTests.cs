using Mesen.Logic;
using Xunit;

namespace Mesen.Tests.CommunityPacks
{
	// ADR-0138 §38 (F6.4b) originally required a first-run consent gate before
	// automatic community-pack download. ADR-0146 supersedes it: accepted
	// catalog packs auto-load whenever possible, so consent is inert. Coverage
	// still lives here (UI/Logic/CommunityPackConsentState.cs).
	public class CommunityPackConsentStateTests
	{
		[Fact]
		public void Evaluate_ToggleOn_NoConsent_AllowsDownloadWithNoDialog()
		{
			CommunityPackConsentDecision decision = CommunityPackConsentState.Evaluate(
				autoInstallEnabled: true, consentGiven: false);

			Assert.True(decision.CanDownloadNow);
			Assert.False(decision.MustShowConsentDialog);
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

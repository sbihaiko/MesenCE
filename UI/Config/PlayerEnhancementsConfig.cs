using CommunityToolkit.Mvvm.ComponentModel;

namespace Mesen.Config;

//P.7 (PRD Part B §6.1/§6.2): state the Player-mode "Enhancements" overlay
//panel and home cards need to persist, on top of settings that already
//exist elsewhere (EnhancementPackConfig.EnableTextures/EnableAudio,
//VideoConfig.AspectRatio/VideoFilter, the per-console overclock fields).
//This class has no Core counterpart - it is never marshaled to the
//native side, unlike EnhancementPackConfig/VideoConfig/etc.
public partial class PlayerEnhancementsConfig : BaseConfig<PlayerEnhancementsConfig>
{
	//WideScrn/HiRes toggle off restores exactly what was configured before
	//the toggle was switched on (not a hardcoded default) - these two
	//fields are that "before" value, only meaningful while the
	//corresponding toggle is on (VideoConfig.AspectRatio == Widescreen /
	//VideoConfig.VideoFilter == HQ4x). Read/written by
	//UI/Logic/PlayerEnhancementsToggle.cs's pure toggle functions.
	[ObservableProperty] public partial VideoAspectRatio WideScrnPriorAspectRatio { get; set; } = VideoAspectRatio.NoStretching;
	[ObservableProperty] public partial VideoFilterType HiResPriorFilter { get; set; } = VideoFilterType.None;

	//The Welcome card (§6.2) shows once, on the very first Player-mode
	//boot, and never again once dismissed.
	[ObservableProperty] public partial bool WelcomeCardDismissed { get; set; } = false;
}

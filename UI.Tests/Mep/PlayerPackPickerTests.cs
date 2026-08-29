using Mesen.Logic;
using System.Collections.Generic;
using Xunit;

namespace Mesen.Tests.Mep
{
	//P.5 (PRD-player-shell §5): the Player picker decision - it opens only for
	//2+ competing pack_ids (after the content_id merge) with no effective
	//stored choice and no sibling-folder pack; it stays silent otherwise.
	public class PlayerPackPickerTests
	{
		private static PackPreferenceResolver.Candidate Candidate(string container, string packId = "", string contentId = "")
		{
			return new() { Container = container, PackId = packId, ContentId = contentId };
		}

		[Fact]
		public void TwoCompetingPackIds_NoPreference_Opens()
		{
			Assert.True(PlayerPackPicker.ShouldOpen(
				hasSiblingPack: false, distinctPackIdCount: 2, hasEffectivePreference: false));
		}

		[Fact]
		public void SiblingPack_AlwaysSuppresses()
		{
			//§4: the sibling-folder pack always wins - no picker even with 2+ ids.
			Assert.False(PlayerPackPicker.ShouldOpen(
				hasSiblingPack: true, distinctPackIdCount: 2, hasEffectivePreference: false));
		}

		[Fact]
		public void StoredPreference_SilentApply()
		{
			//§5: a stored per-ROM choice applies silently; the picker never re-opens.
			Assert.False(PlayerPackPicker.ShouldOpen(
				hasSiblingPack: false, distinctPackIdCount: 2, hasEffectivePreference: true));
		}

		[Fact]
		public void SinglePackId_NeverAsks()
		{
			//§5: 1 pack_id (any number of revisions) applies the slot - never ask
			//1.0 vs 1.2.
			Assert.False(PlayerPackPicker.ShouldOpen(
				hasSiblingPack: false, distinctPackIdCount: 1, hasEffectivePreference: false));
		}

		[Fact]
		public void StalePreference_AsksAgain()
		{
			//The stored pack_id matches no candidate -> no effective preference ->
			//the picker asks again (the game plays un-enhanced this session).
			Assert.True(PlayerPackPicker.ShouldOpen(
				hasSiblingPack: false, distinctPackIdCount: 2, hasEffectivePreference: false));
		}

		[Fact]
		public void DistinctPackIdCount_DuplicateContentId_IsOnePack()
		{
			//A dropped copy of an installed pack shares its content_id -> one choice.
			var merged = new List<PackPreferenceResolver.Candidate> {
				Candidate("catalog-pack", packId: "contra80s", contentId: "AAA"),
				Candidate("dropped-copy", packId: "local:dropped-copy", contentId: "AAA")
			};
			//Fed the RAW list the count would be 2; fed the merged list it is 1.
			//Here both share content_id "AAA", so a caller that merged would see 1.
			var deduped = PackPreferenceResolver.Resolve(merged, null).Candidates;
			Assert.Single(deduped);
			Assert.Equal(1, PlayerPackPicker.DistinctPackIdCount(deduped));
		}

		[Fact]
		public void DistinctPackIdCount_TwoLocalContainers_IsTwo()
		{
			var merged = new List<PackPreferenceResolver.Candidate> {
				Candidate("pack-a", contentId: "AAA"),
				Candidate("pack-b", contentId: "BBB")
			};
			Assert.Equal(2, PlayerPackPicker.DistinctPackIdCount(merged));
		}

		[Fact]
		public void DistinctPackIdCount_StampedAndLocal_DifferentProducts()
		{
			//A stamped pack_id and an unrelated local drop are two choices.
			var merged = new List<PackPreferenceResolver.Candidate> {
				Candidate("stamped", packId: "contra80s", contentId: "AAA"),
				Candidate("local-drop", contentId: "BBB")
			};
			Assert.Equal(2, PlayerPackPicker.DistinctPackIdCount(merged));
		}
	}
}

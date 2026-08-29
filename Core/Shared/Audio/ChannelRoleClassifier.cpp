#include "pch.h"
#include "Shared/Audio/ChannelRoleClassifier.h"

namespace
{
	//F5.4g Bloco B item 3 (ADR-0052): detect a fast 2-4 note arpeggio cycle
	//(20-60 Hz) from a channel's recent onset ring. Returns the number of
	//distinct cycle notes (>= 2) written into outKeys, or 0 when the recent
	//onsets do not form a repeating cycle in that band. Uses its own wider
	//window (kArpeggioWindowS) than the SFX retrigger gate so the low end of
	//the 20-60 Hz band is covered.
	uint32_t DetectArpeggio(const double* onsetTimes, const int* onsetKeys, uint32_t onsetCount, uint32_t onsetPos, double now, int outKeys[4])
	{
		constexpr double kArpeggioWindowS = 0.30;
		constexpr uint32_t kMinOnsets = 5;
		constexpr uint32_t kRing = ChannelRoleClassifier::kOnsetHistory;
		uint32_t recent = 0;
		for(uint32_t k = 0; k < onsetCount && k < kRing; k++) {
			uint32_t idx = (onsetPos + kRing - 1 - k) % kRing;
			if(now - onsetTimes[idx] <= kArpeggioWindowS) {
				recent++;
			} else {
				break;
			}
		}
		if(recent < kMinOnsets) {
			return 0;
		}
		int keys[8] = {};
		for(uint32_t k = 0; k < recent && k < 8; k++) {
			keys[k] = onsetKeys[(onsetPos + kRing - 1 - k) % kRing];
		}
		//Cycle rate: (recent-1) onsets over the span, must sit in 20-60 Hz
		uint32_t firstIdx = (onsetPos + kRing - recent) % kRing;
		uint32_t lastIdx = (onsetPos + kRing - 1) % kRing;
		double span = onsetTimes[lastIdx] - onsetTimes[firstIdx];
		double rate = span > 0 ? (recent - 1.0) / span : 0.0;
		if(rate < 20.0 || rate > 60.0) {
			return 0;
		}
		for(uint32_t period = 2; period <= 4; period++) {
			if(recent < period + 1) {
				break;
			}
			bool periodic = true;
			for(uint32_t k = period; k < recent; k++) {
				if(std::abs(keys[k] - keys[k - period]) > 1) {
					periodic = false;
					break;
				}
			}
			//a cycle must contain at least two distinct pitches
			bool distinct = false;
			for(uint32_t k = 1; k < period; k++) {
				if(std::abs(keys[k] - keys[0]) > 1) {
					distinct = true;
				}
			}
			if(periodic && distinct) {
				uint32_t count = 0;
				for(uint32_t k = 0; k < recent && count < 4; k++) {
					bool dup = false;
					for(uint32_t d = 0; d < count; d++) {
						if(std::abs(keys[k] - outKeys[d]) <= 1) {
							dup = true;
							break;
						}
					}
					if(!dup) {
						outKeys[count++] = keys[k];
					}
				}
				return count >= 2 ? count : 0;
			}
		}
		return 0;
	}
}

void ChannelRoleClassifier::Init(uint32_t count, const ChannelRole* defaultRole)
{
	_count = count > MaxChannels ? MaxChannels : count;
	for(uint32_t i = 0; i < MaxChannels; i++) {
		_defaultRole[i] = i < _count ? defaultRole[i] : ChannelRole::Harmony;
	}
	Reset();
}

void ChannelRoleClassifier::Reset()
{
	for(uint32_t i = 0; i < MaxChannels; i++) {
		_ch[i] = {};
		_role[i] = _defaultRole[i];
		_pendingRole[i] = _defaultRole[i];
		_heldRoleAtSilence[i] = _defaultRole[i];
		_fixedRole[i] = -1; //-1 = auto (no FixedRole override)
		_arpeggioCount[i] = 0;
		_arpeggioAt[i] = 0;
	}
	_swapPending = false;
	_swapWaitS = 0;
	_pendingVotes = 0;
	_sinceDecisionS = 0;
	_now = 0;
}

void ChannelRoleClassifier::SetFixedRoles(const int32_t fixedRoles[MaxChannels])
{
	for(uint32_t i = 0; i < MaxChannels; i++) {
		_fixedRole[i] = fixedRoles[i] < -1 ? -1 : fixedRoles[i] > 2 ? 2 : fixedRoles[i];
	}
	//Re-apply immediately (a reloaded ESP takes effect on the next flush)
	for(uint32_t i = 0; i < _count; i++) {
		if(_fixedRole[i] >= 0) {
			_role[i] = (ChannelRole)_fixedRole[i];
			_pendingRole[i] = _role[i];
		}
	}
}

void ChannelRoleClassifier::UpdateNoteTracking(uint32_t i, const Channel& c, double dt)
{
	State& s = _ch[i];
	bool sounding = c.Vol > kVolThreshold && c.Freq > 1.0 && c.Freq < kMaxAudibleHz;
	bool wasSounding = s.Sounding;
	uint32_t onsets = 0;
	s.AtBoundary = false;

	if(sounding) {
		double note = ToNote(c.Freq);
		s.SilentS = 0;
		s.LastVol = c.Vol;
		if(!wasSounding) {
			s.SoundingS = 0;
			s.HeldNote = note;
			s.LastNote = note;
			s.GlideDir = 0;
			s.GlideSteps = 0;
			s.GlideTotal = 0;
			//F5.4g Bloco B item 4: expression state resets per note
			s.PeakVol = c.Vol;
			s.PeakAtS = _now;
			s.VibratoDepth = 0;
			//F5.4g Bloco B (ADR-0052 item 2): a channel resuming after silence
			//whose *native* role was reassigned to another channel while it was
			//away gets that role handed back instantly (composer-swap-back).
			//Only the native role triggers the fast path - a borrowed
			//non-default role is a melody handoff, which stays as the
			//classifier decided it.
			if(_role[i] != _heldRoleAtSilence[i] && _heldRoleAtSilence[i] == _defaultRole[i]) {
				HandleChannelSteal(i, _heldRoleAtSilence[i]);
			}
			onsets = 1;
		} else {
			s.SoundingS += dt;
			double d = note - s.LastNote;
			double ad = std::abs(d);
			//Glide detector: consecutive same-direction steps within the
			//[min,max] band; zero steps are tolerated because the driver
			//updates at 60 Hz while we poll faster than that.
			if(ad >= kGlideMinStep && ad <= kGlideMaxStep) {
				int dir = d > 0 ? 1 : -1;
				if(dir == s.GlideDir) {
					s.GlideSteps++;
					s.GlideTotal += ad;
				} else {
					//F5.4g Bloco B item 4: a direction reversal closes a
					//glide run - its distance is one half-cycle of a pitch
					//oscillation (vibrato) when it repeats
					s.VibratoDepth = std::max(s.VibratoDepth, s.GlideTotal);
					s.GlideDir = dir;
					s.GlideSteps = 1;
					s.GlideTotal = ad;
					s.GlideStartS = _now - dt;
				}
			} else if(ad > kGlideMaxStep) {
				s.GlideDir = 0;
				s.GlideSteps = 0;
				s.GlideTotal = 0;
			}
			if(c.Vol > s.PeakVol) {
				s.PeakVol = c.Vol;
				s.PeakAtS = _now;
			}
			if(std::abs(note - s.HeldNote) > kOnsetJumpSemitones) {
				s.HeldNote = note;
				onsets = 1;
			}
		}
		s.Note = note;
		s.LastNote = note;
	} else {
		if(wasSounding) {
			s.AtBoundary = true;
			//F5.4g Bloco B: record the role this channel held as it fell
			//silent, so HandleChannelSteal can hand it back on a brief resume
			_heldRoleAtSilence[i] = _role[i];
		}
		s.SilentS += dt;
		s.SoundingS = 0;
		s.LastVol = c.Vol;
		s.GlideDir = 0;
		s.GlideSteps = 0;
		s.GlideTotal = 0;
	}
	s.Sounding = sounding;

	if(onsets) {
		s.AtBoundary = true;
		s.OnsetTimes[s.OnsetPos] = _now;
		s.OnsetKeys[s.OnsetPos] = (int)std::lround(s.Note);
		s.OnsetPos = (s.OnsetPos + 1) % kOnsetHistory;
		if(s.OnsetCount < kOnsetHistory) {
			s.OnsetCount++;
		}
	}
	if(!sounding) {
		s.AtBoundary = true;
	}

	//Windowed features - frozen while the channel is playing an effect so a
	//jump sound does not drag the channel's "mean pitch" up for a second
	if(!s.Sfx) {
		double alpha = dt / kFeatureWindowS;
		if(alpha > 1.0) {
			alpha = 1.0;
		}
		s.AudibleFraction += ((sounding ? 1.0 : 0.0) - s.AudibleFraction) * alpha;
		if(sounding) {
			s.MeanNote += (s.Note - s.MeanNote) * alpha;
		}
		s.OnsetRate += ((dt > 0 ? onsets / dt : 0.0) - s.OnsetRate) * alpha;
	}
}

void ChannelRoleClassifier::UpdateSfxGate(uint32_t i, const Channel& c, double dt)
{
	State& s = _ch[i];
	s.Cue = 0;
	if(!s.Sounding) {
		if(s.Sfx && s.SilentS >= kSfxReleaseS) {
			s.Sfx = false;
			s.SfxHeldS = 0;
		}
		return;
	}

	double glideRate = s.GlideSteps > 0 ? s.GlideTotal / std::max(_now - s.GlideStartS, dt) : 0.0;
	//F5.4g Bloco B item 4: expose the portamento rate for the expression
	//envelope's patch-family choice
	s.GlideRate = glideRate;
	//Fast hardware sweep (slow musical slides on the sweep unit stay music)
	if(c.HwSweep && s.GlideTotal >= kSweepMinTotal && glideRate >= kGlideMinRate) {
		s.Cue |= CueSweep;
	}
	//Fast one-directional glide (distance and speed both matter)
	if(s.GlideSteps >= kGlideMinSteps && s.GlideTotal >= kGlideMinTotal && glideRate >= kGlideMinRate) {
		s.Cue |= CueGlide;
	}
	//Piercing squeal
	if(s.Note > kSqueakNote) {
		s.Cue |= CueSqueak;
	}
	//Fast retriggers that are not a short repeating cycle (an arpeggio)
	if(s.OnsetCount >= kRetrigMinOnsets) {
		uint32_t recent = 0;
		for(uint32_t k = 0; k < s.OnsetCount; k++) {
			uint32_t idx = (s.OnsetPos + kOnsetHistory - 1 - k) % kOnsetHistory;
			if(_now - s.OnsetTimes[idx] <= kRetrigWindowS) {
				recent++;
			} else {
				break;
			}
		}
		if(recent >= kRetrigMinOnsets) {
			//keys of the last "recent" onsets, newest first
			int keys[kOnsetHistory];
			for(uint32_t k = 0; k < recent; k++) {
				keys[k] = s.OnsetKeys[(s.OnsetPos + kOnsetHistory - 1 - k) % kOnsetHistory];
			}
			int lo = keys[0], hi = keys[0];
			for(uint32_t k = 1; k < recent; k++) {
				lo = std::min(lo, keys[k]);
				hi = std::max(hi, keys[k]);
			}
			//Narrow fast alternation = wide vibrato / trill: music
			bool arpeggio = (hi - lo) < kRetrigMinRange;
			for(uint32_t period = 2; period <= 4 && !arpeggio; period++) {
				if(recent < period + 1) {
					break;
				}
				bool periodic = true;
				for(uint32_t k = period; k < recent; k++) {
					if(std::abs(keys[k] - keys[k - period]) > 1) {
						periodic = false;
						break;
					}
				}
				//a cycle must contain at least two distinct pitches
				bool distinct = false;
				for(uint32_t k = 1; k < period; k++) {
					if(std::abs(keys[k] - keys[0]) > 1) {
						distinct = true;
					}
				}
				arpeggio = periodic && distinct;
			}
			if(!arpeggio) {
				s.Cue |= CueRetrigger;
			}
		}
	}

	if(s.Cue != 0) {
		s.Sfx = true;
		s.SfxHeldS = 0;
	} else if(s.Sfx) {
		s.SfxHeldS += dt;
		if(s.SoundingS >= kSfxMaxHoldS && !c.HwSweep) {
			//a tone held this long is music after all
			s.Sfx = false;
			s.SfxHeldS = 0;
		}
	}

	//F5.4g Bloco B item 3 (ADR-0052): track the channel's arpeggio cycle for
	//the engine's chord folding. A clean 2-4 note cycle at 20-60 Hz is music
	//(the retrigger gate above already withholds CueRetrigger for it); the
	//detection here runs independently of the SFX gate so the 20-36 Hz low end
	//of the band is covered too.
	int arpKeys[4];
	uint32_t arpCount = DetectArpeggio(s.OnsetTimes, s.OnsetKeys, s.OnsetCount, s.OnsetPos, _now, arpKeys);
	if(arpCount >= 2) {
		for(uint32_t k = 0; k < arpCount; k++) {
			_arpeggioKeys[i][k] = arpKeys[k];
		}
		_arpeggioCount[i] = arpCount;
		_arpeggioAt[i] = _now;
	} else if(_now - _arpeggioAt[i] > kArpeggioFreshS) {
		_arpeggioCount[i] = 0;
	}
}

uint32_t ChannelRoleClassifier::ArpeggioKeys(uint32_t i, int outKeys[4]) const
{
	if(i >= _count || _now - _arpeggioAt[i] > kArpeggioFreshS) {
		return 0;
	}
	uint32_t count = _arpeggioCount[i] > 4 ? 4 : _arpeggioCount[i];
	for(uint32_t k = 0; k < count; k++) {
		outKeys[k] = _arpeggioKeys[i][k];
	}
	return count;
}

void ChannelRoleClassifier::HandleChannelSteal(uint32_t channel, ChannelRole stolenRole)
{
	//Fast-restore a role that was reassigned to another channel while its
	//original channel was silent (ADR-0052 item 2, F5.4g Bloco B): the moment
	//the channel resumes, swap the two channels' roles back, bypassing the
	//kDecisionsToSwitch hysteresis. The caller only fires for a channel's
	//native role, so a genuine melody handoff is untouched.
	if(channel >= _count) {
		return;
	}
	int holder = -1;
	for(uint32_t i = 0; i < _count; i++) {
		if((int)i != (int)channel && _role[i] == stolenRole) {
			holder = (int)i;
			break;
		}
	}
	if(holder < 0) {
		//the role is not currently assigned elsewhere - nothing to hand back
		return;
	}
	ChannelRole resumeRole = _role[channel];
	_role[channel] = stolenRole;
	_role[holder] = resumeRole;
	//the resumed channel holds its role again; cancel any in-flight hysteresis
	for(uint32_t i = 0; i < _count; i++) {
		_pendingRole[i] = _role[i];
	}
	_pendingVotes = 0;
	_swapPending = false;
}

double ChannelRoleClassifier::DecayRate(uint32_t i) const
{
	const State& s = _ch[i];
	if(i >= _count || !s.Sounding || s.PeakVol <= kVolThreshold || s.PeakAtS <= 0) {
		return 0;
	}
	double dt = _now - s.PeakAtS;
	if(dt <= 0) {
		return 0;
	}
	double fall = (s.PeakVol - s.LastVol) / dt; //vol/s
	return fall > 0 ? fall : 0;
}

void ChannelRoleClassifier::Decide()
{
	//F5.4g Bloco B item 6: channels with a FixedRole override are locked -
	//the auto decision never reassigns them (Update() re-pins the role after
	//this anyway; locking here keeps the other channels' assignment coherent)
	bool locked[MaxChannels] = {};
	for(uint32_t i = 0; i < _count; i++) {
		locked[i] = _fixedRole[i] >= 0;
	}

	//Candidate assignment from the windowed features
	bool audible[MaxChannels];
	double score[MaxChannels];
	uint32_t audibleCount = 0;
	for(uint32_t i = 0; i < _count; i++) {
		audible[i] = !locked[i] && !_ch[i].Sfx && _ch[i].AudibleFraction >= kMinAudibleFraction;
		double rate = _ch[i].OnsetRate > 4.0 ? 4.0 : _ch[i].OnsetRate;
		score[i] = _ch[i].MeanNote + kOnsetRateWeight * rate;
		if(audible[i]) {
			audibleCount++;
		}
	}
	if(audibleCount < 2) {
		//Not enough material to judge; let any pending swap lapse
		_pendingVotes = 0;
		return;
	}

	//Bass: lowest audible channel if it sits low and clearly below the next
	int bass = -1;
	int defaultBass = -1;
	for(uint32_t i = 0; i < _count; i++) {
		if(_defaultRole[i] == ChannelRole::Bass) {
			defaultBass = (int)i;
		}
	}
	{
		int lowest = -1, second = -1;
		for(uint32_t i = 0; i < _count; i++) {
			if(!audible[i]) {
				continue;
			}
			if(lowest < 0 || _ch[i].MeanNote < _ch[lowest].MeanNote) {
				second = lowest;
				lowest = (int)i;
			} else if(second < 0 || _ch[i].MeanNote < _ch[second].MeanNote) {
				second = (int)i;
			}
		}
		if(lowest >= 0 && _ch[lowest].MeanNote <= kBassMaxNote && (second < 0 || _ch[second].MeanNote - _ch[lowest].MeanNote >= kBassMinGap)) {
			bass = lowest;
		} else if(lowest >= 0 && lowest == defaultBass && _ch[lowest].MeanNote <= kBassMaxNote + 6.0) {
			bass = lowest;
		} else {
			bass = defaultBass;
		}
	}

	//Lead: highest melody score among the audible non-bass channels, with a
	//margin over the channel currently holding the lead
	int lead = -1;
	int currentLead = -1;
	for(uint32_t i = 0; i < _count; i++) {
		if((int)i == bass) {
			continue;
		}
		if(_role[i] == ChannelRole::Lead) {
			currentLead = (int)i;
		}
		if(audible[i] && (lead < 0 || score[i] > score[lead])) {
			lead = (int)i;
		}
	}
	if(lead < 0) {
		//only the bass is audible among the non-sfx channels
		_pendingVotes = 0;
		return;
	}
	if(currentLead >= 0 && currentLead != lead && audible[currentLead] && score[lead] < score[currentLead] + kScoreMargin) {
		lead = currentLead;
	}

	ChannelRole candidate[MaxChannels];
	for(uint32_t i = 0; i < _count; i++) {
		candidate[i] = locked[i] ? (ChannelRole)_fixedRole[i] :
			(int)i == bass ? ChannelRole::Bass : (int)i == lead ? ChannelRole::Lead :
																								ChannelRole::Harmony;
	}

	bool same = true, samePending = true;
	for(uint32_t i = 0; i < _count; i++) {
		same &= candidate[i] == _role[i];
		samePending &= candidate[i] == _pendingRole[i];
	}
	if(same) {
		_pendingVotes = 0;
		_swapPending = false;
		return;
	}
	if(samePending) {
		_pendingVotes++;
	} else {
		for(uint32_t i = 0; i < _count; i++) {
			_pendingRole[i] = candidate[i];
		}
		_pendingVotes = 1;
	}
	if(_pendingVotes >= kDecisionsToSwitch && !_swapPending) {
		_swapPending = true;
		_swapWaitS = 0;
	}
}

void ChannelRoleClassifier::Update(const Channel* channels, double dt)
{
	if(dt <= 0) {
		dt = 1.0 / 179.0;
	}
	_now += dt;
	for(uint32_t i = 0; i < _count; i++) {
		UpdateNoteTracking(i, channels[i], dt);
		UpdateSfxGate(i, channels[i], dt);
	}

	if(!_autoRoles) {
		for(uint32_t i = 0; i < _count; i++) {
			_role[i] = _defaultRole[i];
		}
		_swapPending = false;
		_pendingVotes = 0;
	} else {
		_sinceDecisionS += dt;
		if(_sinceDecisionS >= kDecisionPeriodS) {
			_sinceDecisionS = 0;
			Decide();
		}

		if(_swapPending) {
			_swapWaitS += dt;
			bool ready = true;
			for(uint32_t i = 0; i < _count; i++) {
				if(_pendingRole[i] != _role[i] && !_ch[i].AtBoundary) {
					ready = false;
				}
			}
			if(ready || _swapWaitS >= kSwapGraceS) {
				for(uint32_t i = 0; i < _count; i++) {
					_role[i] = _pendingRole[i];
				}
				_swapPending = false;
				_pendingVotes = 0;
			}
		}
	}

	//F5.4g Bloco B item 6 (ADR-0052): FixedRole overrides pin the channel's
	//role after both the default fallback and the auto decision, so the human
	//per-game override always wins; its in-flight swap state is cleared.
	bool anyFixed = false;
	for(uint32_t i = 0; i < _count; i++) {
		if(_fixedRole[i] >= 0) {
			_role[i] = (ChannelRole)_fixedRole[i];
			_pendingRole[i] = _role[i];
			anyFixed = true;
		}
	}
	if(anyFixed) {
		_pendingVotes = 0;
		_swapPending = false;
	}
}

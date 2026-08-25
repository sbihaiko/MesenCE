#include "pch.h"
#include "Shared/Audio/ChannelRoleClassifier.h"

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
	}
	_swapPending = false;
	_swapWaitS = 0;
	_pendingVotes = 0;
	_sinceDecisionS = 0;
	_now = 0;
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
		if(!wasSounding) {
			s.SoundingS = 0;
			s.HeldNote = note;
			s.LastNote = note;
			s.GlideDir = 0;
			s.GlideSteps = 0;
			s.GlideTotal = 0;
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
		}
		s.SilentS += dt;
		s.SoundingS = 0;
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
}

void ChannelRoleClassifier::Decide()
{
	//Candidate assignment from the windowed features
	bool audible[MaxChannels];
	double score[MaxChannels];
	uint32_t audibleCount = 0;
	for(uint32_t i = 0; i < _count; i++) {
		audible[i] = !_ch[i].Sfx && _ch[i].AudibleFraction >= kMinAudibleFraction;
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
		candidate[i] = (int)i == bass ? ChannelRole::Bass : (int)i == lead ? ChannelRole::Lead : ChannelRole::Harmony;
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
		return;
	}

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

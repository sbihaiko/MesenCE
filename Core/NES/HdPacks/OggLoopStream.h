#pragma once
#include "pch.h"

//F5.4g Block C item 8 (ADR-0134): the decoder-agnostic half of OggReader - how
//far a track is read and where it goes when it ends. The loop point is an
//optional per-track property (fingerprints.json `tracks[i].loop`, PCM samples
//at the OGG's own rate): once the stream runs out, playback resumes at that
//sample instead of at 0, so a track's intro is not repeated. A track that
//omits the field (0), or whose loop point falls outside the stream, keeps the
//pre-item-8 behaviour and loops the whole file.
//
//Split out of OggReader so the rule can be exercised without stb_vorbis or
//VirtualFile - the same move ADR-0142 made for the mixer with IOggSource. The
//production decoder is the stb_vorbis wrapper inside OggReader.cpp.
class IOggDecoder
{
public:
	virtual ~IOggDecoder() = default;

	//Sample rate of the encoded stream, in Hz.
	virtual int GetSampleRate() = 0;
	//Total length of the stream in PCM samples (per channel).
	virtual uint32_t GetStreamLength() = 0;
	//Reads up to `frames` interleaved stereo frames into `buffer`; returns how
	//many frames were actually produced (less than asked = end of stream).
	virtual uint32_t ReadFrames(int16_t* buffer, uint32_t frames) = 0;
	//Moves the read position to the given PCM sample offset.
	virtual void Seek(uint32_t sampleOffset) = 0;
	//Current read position, in PCM samples.
	virtual uint32_t GetOffset() = 0;
};

class OggLoopStream
{
private:
	IOggDecoder* _decoder = nullptr;
	uint32_t _loopPosition = 0;
	bool _loop = false;
	bool _done = false;

public:
	//`loopPosition` is the ADR-0134 track loop point, in PCM samples; 0 means
	//"no loop point" and any value at or past the end of the stream is treated
	//the same way, so a stale or mis-authored value degrades to looping the
	//whole file rather than failing to play.
	void Init(IOggDecoder* decoder, bool loop, uint32_t loopPosition)
	{
		_decoder = decoder;
		_loop = loop;
		_done = false;
		_loopPosition = (loopPosition > 0 && decoder && loopPosition < decoder->GetStreamLength()) ? loopPosition : 0;
	}

	uint32_t GetLoopPosition() const { return _loopPosition; }
	bool IsDone() const { return _done; }
	void SetLoopFlag(bool loop) { _loop = loop; }

	//Reads `frames` interleaved stereo frames, wrapping to the loop point when
	//the track ends. Returns the number of frames produced; a non-looping
	//track that ran out marks the stream done and returns a short read.
	uint32_t Read(int16_t* buffer, uint32_t frames)
	{
		if(!_decoder) {
			return 0;
		}
		uint32_t framesRead = _decoder->ReadFrames(buffer, frames);
		if(framesRead < frames) {
			if(_loop) {
				_decoder->Seek(_loopPosition);
				framesRead += _decoder->ReadFrames(buffer + framesRead * 2, frames - framesRead);
			} else {
				_done = true;
			}
		}
		return framesRead;
	}
};

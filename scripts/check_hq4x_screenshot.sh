#!/usr/bin/env bash
# P.7 (docs/validation/manual-validation-automation-plan.md): objective check that the
# HQ4x video filter is really applied to the screenshot pipeline
# (BaseVideoFilter::TakeScreenshot -> ScaleFilter::GetScaleFilter->ApplyFilter),
# replacing the "look at it on a real display" manual step.
#
# It runs scripts/headless_record twice on the same ROM (no input is ever fed,
# so the captured frame is deterministic): once with filter=none to learn the
# native frame size, once with filter=hq4x. It then asserts, on the PNGs:
#   1. the HQ4x PNG is exactly 4x the native width and height;
#   2. a filter signature - HQ4x interpolates, so (a) many 4x4 blocks of the
#      output are NOT uniform (a plain nearest-neighbour upscale of a native
#      frame would make every 4x4 block a solid colour) and (b) the output has
#      far more distinct colours than the native frame.
# The PNG is decoded with the Python standard library only (zlib), no PIL.
#
# On-demand tool, not a CI gate: it needs a built core dylib and a ROM.
#
# Build once:  make capture-tool
# Usage:       scripts/check_hq4x_screenshot.sh [rom] [seconds] [workdir]
# Defaults:    rom=roms/Zelda.nes  seconds=3  workdir=$(mktemp -d)
# Exit code:   0 = HQ4x verified, 1 = assertion failed / setup missing.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROM="${1:-$REPO_ROOT/roms/Zelda.nes}"
SECONDS_TO_RUN="${2:-3}"
WORKDIR="${3:-$(mktemp -d)}"
RECORDER="$REPO_ROOT/scripts/headless_record"

if [ ! -x "$RECORDER" ]; then
	echo "error: $RECORDER not found - run 'make capture-tool' first" >&2
	exit 1
fi
if [ ! -f "$ROM" ]; then
	echo "error: ROM not found: $ROM" >&2
	exit 1
fi

mkdir -p "$WORKDIR"

# mep-off keeps MEP/HD pack texture replacement out of the picture, so the
# "native" frame really is the console's native resolution (a 4x HD pack would
# otherwise make the baseline itself upscaled).
run_capture() {
	local filter="$1"
	local out="$WORKDIR/$filter"
	rm -rf "$out"
	mkdir -p "$out"
	(cd "$REPO_ROOT" && "$RECORDER" "$ROM" "$SECONDS_TO_RUN" "$out/out" screenshot mep-off "filter=$filter") >"$out/log.txt" 2>&1 || {
		echo "error: headless_record failed for filter=$filter; log:" >&2
		cat "$out/log.txt" >&2
		exit 1
	}
	local png
	png="$(find "$out" -name '*.png' | head -1)"
	if [ -z "$png" ]; then
		echo "error: no screenshot produced for filter=$filter; log:" >&2
		cat "$out/log.txt" >&2
		exit 1
	fi
	echo "$png"
}

echo "== capturing native frame (filter=none)"
NATIVE_PNG="$(run_capture none)"
echo "== capturing filtered frame (filter=hq4x)"
HQ4X_PNG="$(run_capture hq4x)"

python3 - "$NATIVE_PNG" "$HQ4X_PNG" <<'PY'
import struct, sys, zlib

def read_png(path):
	"""Minimal PNG reader: 8-bit RGB/RGBA, non-interlaced (what PNGHelper writes)."""
	data = open(path, 'rb').read()
	assert data[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG: ' + path
	pos = 8
	idat = b''
	width = height = depth = color = interlace = None
	while pos < len(data):
		length, ctype = struct.unpack('>I4s', data[pos:pos + 8])
		body = data[pos + 8:pos + 8 + length]
		pos += 12 + length
		if ctype == b'IHDR':
			width, height, depth, color, _, _, interlace = struct.unpack('>IIBBBBB', body)
		elif ctype == b'IDAT':
			idat += body
		elif ctype == b'IEND':
			break
	assert depth == 8 and color in (2, 6) and interlace == 0, \
		'unsupported PNG format (depth=%s color=%s interlace=%s)' % (depth, color, interlace)
	channels = 3 if color == 2 else 4
	raw = zlib.decompress(idat)
	stride = width * channels
	out = bytearray(width * height * channels)
	prev = bytearray(stride)
	src = 0
	for y in range(height):
		ftype = raw[src]; src += 1
		line = bytearray(raw[src:src + stride]); src += stride
		if ftype == 1:
			for i in range(channels, stride):
				line[i] = (line[i] + line[i - channels]) & 0xFF
		elif ftype == 2:
			for i in range(stride):
				line[i] = (line[i] + prev[i]) & 0xFF
		elif ftype == 3:
			for i in range(stride):
				left = line[i - channels] if i >= channels else 0
				line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
		elif ftype == 4:
			for i in range(stride):
				a = line[i - channels] if i >= channels else 0
				b = prev[i]
				c = prev[i - channels] if i >= channels else 0
				p = a + b - c
				pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
				pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
				line[i] = (line[i] + pr) & 0xFF
		elif ftype != 0:
			raise AssertionError('unknown PNG filter type %d' % ftype)
		out[y * stride:(y + 1) * stride] = line
		prev = line
	pixels = [tuple(out[i:i + 3]) for i in range(0, len(out), channels)]
	return width, height, pixels

native_path, hq4x_path = sys.argv[1], sys.argv[2]
nw, nh, npx = read_png(native_path)
hw, hh, hpx = read_png(hq4x_path)

print('native : %s  %dx%d' % (native_path, nw, nh))
print('hq4x   : %s  %dx%d' % (hq4x_path, hw, hh))

failures = []

# 1. dimensions
if (hw, hh) != (nw * 4, nh * 4):
	failures.append('expected %dx%d (4x native), got %dx%d' % (nw * 4, nh * 4, hw, hh))
else:
	print('OK  dimensions: %dx%d == 4x %dx%d' % (hw, hh, nw, nh))

# 2a. filter signature: non-uniform 4x4 blocks
if (hw, hh) == (nw * 4, nh * 4):
	nonuniform = 0
	total = nw * nh
	for by in range(nh):
		for bx in range(nw):
			o = by * 4 * hw + bx * 4
			first = hpx[o]
			for dy in range(4):
				row = o + dy * hw
				if hpx[row] != first or hpx[row + 1] != first or hpx[row + 2] != first or hpx[row + 3] != first:
					nonuniform += 1
					break
	pct = 100.0 * nonuniform / total
	print('    non-uniform 4x4 blocks: %.2f%% (%d/%d)' % (pct, nonuniform, total))
	if pct < 1.0:
		failures.append('only %.2f%% of 4x4 blocks are non-uniform - looks like a nearest-neighbour upscale, not HQ4x' % pct)
	else:
		print('OK  filter signature: HQ4x introduced sub-block detail')

	# informational: how far the filtered frame is from a plain 4x pixel copy
	diff = 0
	for by in range(nh):
		for bx in range(nw):
			src = npx[by * nw + bx]
			o = by * 4 * hw + bx * 4
			for dy in range(4):
				row = o + dy * hw
				for dx in range(4):
					if hpx[row + dx] != src:
						diff += 1
	print('    differs from nearest-neighbour 4x upscale on %.2f%% of pixels' % (100.0 * diff / (hw * hh)))

# 2b. filter signature: colour count inflation from interpolation
ncolors = len(set(npx))
hcolors = len(set(hpx))
print('    distinct colours: native=%d hq4x=%d' % (ncolors, hcolors))
if hcolors < ncolors * 3:
	failures.append('hq4x frame has %d colours vs %d native - no interpolation detected' % (hcolors, ncolors))
else:
	print('OK  filter signature: interpolated colours (%.1fx the native palette)' % (float(hcolors) / max(ncolors, 1)))

if failures:
	print('')
	for f in failures:
		print('FAIL ' + f)
	sys.exit(1)
print('')
print('PASS HQ4x is applied to the screenshot pipeline')
PY

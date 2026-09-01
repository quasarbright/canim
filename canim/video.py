"""Telling players what color space the rendered video is in.

Manim writes H.264 with no color metadata at all — `color_primaries`,
`color_trc`, `colorspace` and `color_range` all come out `unknown`. The pixels
are fine; the file just never says how to read them, so every player guesses.
ffmpeg happens to guess right, which is why a frame extracted with ffmpeg
matches the theme exactly. QuickTime guesses BT.709 with a video transfer
curve and then color-manages that to the display, which lands the same numbers
somewhere else — the video looks brighter and more saturated than the same
hex does in a browser.

The values below are what manim actually produces, established by testing all
three matrices against a render and seeing which one round-trips:

    matrix=1  bt709        total error across four theme colors: 42
    matrix=5  bt470bg                                             4
    matrix=6  smpte170m                                           4

So the YUV conversion is BT.601 even at 720p, while the RGB it was converted
*from* is plain sRGB. Tagging it BT.709 — the obvious guess for HD — makes
things worse, not better.

Manim exposes no hook for this. The file writer class is only reachable
through a renderer constructor argument and there is no post-render callback,
so this wraps `SceneFileWriter.open_partial_movie_stream` — manim keeps the
stream it just made on `self.video_stream`, which is enough to stamp it.
PyAV's own container is a C extension type and cannot be patched, so this is
the outermost seam that is plain Python.

Only the partial files need stamping. The final movie is remuxed from them
with `add_stream(template=...)`, which copies the codec parameters across, so
the tags come along on their own.

Opt-in rather than an import side effect — call `tag_color_space()` once from
the video's own module.
"""

from __future__ import annotations

from manim.scene.scene_file_writer import SceneFileWriter

# AVCOL_* enum values.
SRGB_ON_BT601 = {
    "color_primaries": 1,  # BT.709 primaries, which sRGB shares
    "color_trc": 13,  # IEC 61966-2-1, the sRGB transfer curve
    "colorspace": 6,  # SMPTE 170M — the BT.601 matrix manim converts with
    "color_range": 1,  # MPEG, i.e. limited/tv range
}


def tag_color_space(values: dict[str, int] | None = None) -> None:
    """Make every video stream manim writes declare its color space.

    Safe to call more than once; the second call does nothing.
    """
    values = SRGB_ON_BT601 if values is None else values
    original = SceneFileWriter.open_partial_movie_stream
    if getattr(original, "_canim_tagged", False):
        return

    def open_partial_movie_stream(self, *args, **kwargs):
        original(self, *args, **kwargs)
        context = self.video_stream.codec_context
        for attribute, value in values.items():
            setattr(context, attribute, value)

    open_partial_movie_stream._canim_tagged = True
    SceneFileWriter.open_partial_movie_stream = open_partial_movie_stream

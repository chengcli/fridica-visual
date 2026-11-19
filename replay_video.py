"""Encode the shared SVG frames with FFmpeg and its librsvg decoder."""
from pathlib import Path
import subprocess
import tempfile

from replay_frame import FRAMES_PER_SECOND


def render_video(frames, output):
    target = Path(output).resolve()
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        folder = Path(tmp)
        for i, frame in enumerate(frames):
            name = f"{i}.svg"
            (folder / name).write_text(frame["svg"])
        encoded = folder / "replay.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-framerate", str(FRAMES_PER_SECOND),
                        "-i", str(folder / "%d.svg"), "-c:v",
                        "libx264", "-threads", "3", "-preset", "ultrafast", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(encoded)], check=True)
        encoded.replace(target)

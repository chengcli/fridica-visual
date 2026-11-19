"""Encode the shared SVG frames with FFmpeg and its librsvg decoder."""
from pathlib import Path
import subprocess
import tempfile


def render_video(frames, output):
    target = Path(output).resolve()
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        folder = Path(tmp)
        playlist = []
        for i, frame in enumerate(frames):
            name = f"{i}.svg"
            (folder / name).write_text(frame["svg"])
            playlist.extend([f"file '{name}'", f"duration {frame['seconds']}"])
        playlist.append(f"file '{name}'")
        manifest = folder / "frames.txt"
        manifest.write_text("\n".join(playlist) + "\n")
        encoded = folder / "replay.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "concat",
                        "-safe", "0", "-i", str(manifest), "-fps_mode", "vfr", "-c:v",
                        "libx264", "-threads", "3", "-preset", "ultrafast", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(encoded)], check=True)
        encoded.replace(target)

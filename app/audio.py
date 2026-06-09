import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("audio")


class AudioError(Exception):
    pass


def concat_to_wav(input_paths: list[Path], out_dir: Path) -> Path:
    """Merge N audio files into a single 16 kHz mono WAV."""
    if not input_paths:
        raise AudioError("no audio file provided")

    out_path = out_dir / "merged.wav"

    cmd: list[str] = ["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error"]
    for p in input_paths:
        cmd += ["-i", str(p)]

    if len(input_paths) == 1:
        cmd += ["-map", "0:a"]
    else:
        n = len(input_paths)
        streams = "".join(f"[{i}:a]" for i in range(n))
        cmd += ["-filter_complex", f"{streams}concat=n={n}:v=0:a=1[out]", "-map", "[out]"]

    cmd += ["-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(out_path)]

    logger.info("ffmpeg merge of %d files -> %s", len(input_paths), out_path)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg failed: {proc.stderr.strip()}")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise AudioError("ffmpeg produced no valid output")
    return out_path


def make_workdir() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="whisper-")

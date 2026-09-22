from __future__ import annotations

import argparse
import time
from pathlib import Path

from faster_whisper import WhisperModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark local Whisper transcription.")
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--threads", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.audio.exists():
        raise SystemExit(f"Audio file not found: {args.audio}")

    print(f"Loading model: {args.model} ({args.device}/{args.compute_type})")
    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
        cpu_threads=args.threads,
        num_workers=1,
    )
    started = time.perf_counter()
    segments, info = model.transcribe(
        str(args.audio),
        language="zh",
        vad_filter=True,
        beam_size=1,
        condition_on_previous_text=False,
    )
    text = "".join(segment.text for segment in segments).strip()
    elapsed = time.perf_counter() - started
    duration = float(info.duration)
    rtf = elapsed / duration if duration else float("inf")

    print(f"Audio duration : {duration:.2f}s")
    print(f"Elapsed time   : {elapsed:.2f}s")
    print(f"Realtime factor: {rtf:.3f}")
    print(f"Target (<0.7)  : {'PASS' if rtf < 0.7 else 'NEEDS TUNING'}")
    print("Transcript preview:")
    print(text[:500] or "(no speech detected)")


if __name__ == "__main__":
    main()


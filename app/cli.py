"""Manual, queue-free entrypoint for smoke tests.

Does not touch Redis — it calls the shared Pipeline / S3Store directly.
Production runs as a Celery worker (see app/celery_app.py).

    python -m app.cli list             # list roomhash folders with recordings
    python -m app.cli run <roomhash>   # transcribe one room and write to S3
    python -m app.cli summarize <file> # summarize a local text file (LLM only)
"""
import argparse
import logging
from pathlib import Path

from .config import get_settings
from .s3 import S3Store
from .summarizer import Summarizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcriber CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list roomhash folders that have recordings")
    sub.add_parser("scan", help="show rooms with recordings but no transcript (dry run)")
    run = sub.add_parser("run", help="transcribe one room and exit")
    run.add_argument("roomhash")
    run.add_argument("--force", action="store_true",
                     help="re-transcribe even if a transcript already exists")
    summ = sub.add_parser("summarize", help="summarize a local text file (LLM only, no Whisper/S3)")
    summ.add_argument("file")

    args = parser.parse_args()
    settings = get_settings()

    if args.cmd == "list":
        store = S3Store(settings)
        rooms = store.list_rooms()
        if not rooms:
            print(f"(no recordings under {settings.recordings_prefix}/)")
        for r in rooms:
            print(r)
        return

    if args.cmd == "scan":
        store = S3Store(settings)
        todo = store.rooms_to_transcribe()
        print(f"{len(todo)} room(s) to transcribe (recordings without a transcript):")
        for r in todo:
            print(r)
        return

    if args.cmd == "summarize":
        text = Path(args.file).read_text(encoding="utf-8")
        print(Summarizer(settings).summarize(text))
        return

    from .pipeline import Pipeline
    from .transcriber import Transcriber
    pipeline = Pipeline(settings, S3Store(settings), Transcriber(settings))
    print(pipeline.process_room(args.roomhash, force=args.force))


if __name__ == "__main__":
    main()

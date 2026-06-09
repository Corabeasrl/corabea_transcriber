"""Manual, queue-free entrypoint for smoke tests.

Does not touch Redis — it calls the shared Pipeline / S3Store directly.
Production runs as a Celery worker (see app/celery_app.py).

    python -m app.cli list             # list roomhash folders with recordings
    python -m app.cli run <roomhash>   # transcribe one room and write to S3
"""
import argparse
import logging

from .config import get_settings
from .pipeline import Pipeline
from .s3 import S3Store
from .transcriber import Transcriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcriber CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list roomhash folders that have recordings")
    run = sub.add_parser("run", help="transcribe one room and exit")
    run.add_argument("roomhash")
    run.add_argument("--force", action="store_true",
                     help="re-transcribe even if a transcript already exists")

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

    pipeline = Pipeline(settings, S3Store(settings), Transcriber(settings))
    print(pipeline.process_room(args.roomhash, force=args.force))


if __name__ == "__main__":
    main()

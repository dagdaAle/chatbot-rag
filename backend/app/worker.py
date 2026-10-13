"""Entrypoint for the dedicated persistent import worker."""
import logging
import signal
import threading

from app.core.import_jobs import run_worker


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run_worker(stop_event=stop)


if __name__ == "__main__":
    main()

"""Opt-in CLI diagnostics; library calls and JSON stdout remain unchanged."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
import sys
import threading
import time

_active = ContextVar('migration_progress', default=None)


class Progress:
    def __init__(self, operation, interval=10, stream=None):
        self.operation = operation
        self.interval = interval
        self.stream = stream if stream is not None else sys.stderr
        self.started = time.monotonic()
        self.updated = self.started
        self.last_emitted = 0
        self.state = {'phase': 'startup'}
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.file = None

    def attach(self, path):
        self.file = path.open('x', encoding='utf-8')

    def emit(self, event, **fields):
        with self.lock:
            now = time.monotonic()
            record = {'time': datetime.now(timezone.utc).isoformat(), 'operation': self.operation,
                'pid': os.getpid(), 'event': event, 'elapsed_s': round(now-self.started, 3),
                'checkpoint_age_s': round(now-self.updated, 3), **self.state, **fields}
            line = json.dumps(record, ensure_ascii=False)
            self.stream.write('[progress] ' + line + '\n')
            self.stream.flush()
            if self.file:
                self.file.write(line + '\n')
                self.file.flush()
            self.last_emitted = now

    def checkpoint(self, phase, **fields):
        with self.lock:
            changed = phase != self.state.get('phase')
            self.state = {'phase': phase, **fields}
            self.updated = time.monotonic()
            complete = fields.get('total') is not None and fields.get('completed') == fields['total']
            if changed or self.updated-self.last_emitted >= 1 or complete:
                self.emit('progress')

    def _heartbeat(self):
        while not self.stop.wait(self.interval):
            self.emit('heartbeat')

    def __enter__(self):
        self.token = _active.set(self)
        self.emit('start')
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, kind, value, traceback):
        self.stop.set()
        self.thread.join()
        self.emit('failed' if kind else 'finished', **({'error': str(value) or kind.__name__} if kind else {}))
        _active.reset(self.token)
        if self.file:
            self.file.close()


def checkpoint(name, **fields):
    reporter = _active.get()
    if reporter:
        reporter.checkpoint(name, **fields)


def attach_log(path):
    reporter = _active.get()
    if reporter:
        reporter.attach(path)


@contextmanager
def phase(name, **fields):
    reporter = _active.get()
    started = time.monotonic()
    previous = dict(reporter.state) if reporter else None
    checkpoint(name, **fields)
    if reporter:
        reporter.emit('phase-start')
    try:
        yield
    except BaseException as error:
        if reporter:
            reporter.emit('phase-failed', phase=name, seconds=round(time.monotonic()-started, 3), error=str(error) or type(error).__name__)
        raise
    else:
        if reporter:
            reporter.emit('phase-finished', phase=name, seconds=round(time.monotonic()-started, 3))
    finally:
        if reporter:
            with reporter.lock:
                reporter.state = previous
                reporter.updated = time.monotonic()


def step(name, function, *args, **kwargs):
    with phase(name):
        return function(*args, **kwargs)


def tracked(items, name, describe=str):
    """Report actual completed units, not a guessed overall percentage."""
    total = len(items)
    for index, item in enumerate(items):
        checkpoint(name, completed=index, total=total, unit=describe(item))
        yield item
    checkpoint(name, completed=total, total=total)

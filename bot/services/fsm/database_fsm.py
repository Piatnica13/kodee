from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import fcntl
import tempfile
import time
from sqlalchemy import text
from flask import current_app
from db.models import db, BotState
from .fsm_storage import FSM


class DatabaseFSMStorage(FSM):
    """Persistent dialogs with expiry and serialization across WSGI workers."""
    def __init__(self):
        self._active = ContextVar('bot_dialog', default=None)

    @contextmanager
    def scope(self, chat_id):
        # A dedicated PostgreSQL connection keeps this session lock across the
        # commits performed by existing business handlers.
        if db.engine.dialect.name == 'postgresql':
            with db.engine.connect() as connection:
                connection.execute(text('SELECT pg_advisory_lock(:key)'), {'key': chat_id})
                try:
                    with self._dialog(chat_id):
                        yield
                finally:
                    connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': chat_id})
        else:
            lock_path = Path(tempfile.gettempdir()) / f'kodee-dialog-{chat_id}.lock'
            with lock_path.open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    with self._dialog(chat_id):
                        yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    @contextmanager
    def _dialog(self, chat_id):
        record = db.session.get(BotState, chat_id)
        data = deepcopy(record.data) if record and record.expires_at > time.time() else None
        token = self._active.set({'chat_id': chat_id, 'data': data})
        try:
            yield
            state = self._active.get()['data']
            if record is not None:
                db.session.delete(record)
                db.session.flush()
            if state is not None:
                db.session.add(BotState(chat_id=chat_id, data=deepcopy(state),
                    expires_at=time.time() + current_app.config.get('BOT_STATE_TTL', 3600)))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        finally:
            self._active.reset(token)

    def get(self, chat_id):
        active = self._active.get()
        if active and active['chat_id'] == chat_id:
            return active['data']
        record = db.session.get(BotState, chat_id)
        return deepcopy(record.data) if record and record.expires_at > time.time() else None

    def set(self, chat_id, data):
        active = self._active.get()
        if active and active['chat_id'] == chat_id:
            active['data'] = data
            return
        raise RuntimeError('FSM writes require a dialog scope')

    def clear(self, chat_id):
        self.set(chat_id, None)

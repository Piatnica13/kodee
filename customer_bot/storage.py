"""Customer bot persistence, installed in the main application database."""
from contextlib import contextmanager
from contextvars import ContextVar
from sqlalchemy import (MetaData, Table, Column, Integer, BigInteger,
                        String, JSON, Float, Boolean, select)

metadata = MetaData()
sessions = Table('cb_sessions', metadata,
    Column('key', String(200), primary_key=True), Column('user_id', BigInteger, nullable=False),
    Column('state', JSON, nullable=False), Column('updated_at', Float, nullable=False))
updates = Table('cb_updates', metadata,
    Column('id', BigInteger, primary_key=True), Column('created_at', Float, nullable=False))
orders = Table('cb_orders', metadata,
    Column('id', String(16), primary_key=True), Column('user_id', BigInteger, nullable=False, index=True),
    Column('session_key', String(200), nullable=False), Column('route', JSON, nullable=False),
    Column('items', JSON, nullable=False), Column('total', Integer, nullable=False),
    Column('customer', JSON, nullable=False), Column('status', String(24), nullable=False),
    Column('created_at', Float, nullable=False), Column('updated_at', Float, nullable=False))
events = Table('cb_events', metadata,
    Column('id', Integer, primary_key=True), Column('kind', String(50), nullable=False),
    Column('order_id', String(16), nullable=False), Column('payload', JSON, nullable=False),
    Column('created_at', Float, nullable=False), Column('exported', Boolean, nullable=False, default=False))
outbox = Table('cb_outbox', metadata,
    Column('id', Integer, primary_key=True), Column('target', String(16), nullable=False, default='customer'),
    Column('method', String(40), nullable=False),
    Column('payload', JSON, nullable=False), Column('attempts', Integer, nullable=False, default=0),
    Column('available_at', Float, nullable=False), Column('sent', Boolean, nullable=False, default=False),
    Column('failed', Boolean, nullable=False, default=False), Column('last_error', String(100)))



class Store:
    """Uses the application's database and serializes customer transactions."""
    def __init__(self, engine_provider):
        self._engine_provider = engine_provider
        self.current_connection = ContextVar('customer_bot_connection', default=None)

    @property
    def engine(self):
        return self._engine_provider()

    @contextmanager
    def transaction(self):
        with self.engine.connect() as conn:
            if self.engine.dialect.name == 'sqlite':
                conn.exec_driver_sql('BEGIN IMMEDIATE')
            else:
                conn.begin()
                conn.exec_driver_sql('SELECT pg_advisory_xact_lock(807194026)')
            token = self.current_connection.set(conn)
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                self.current_connection.reset(token)

    def pending_count(self):
        from sqlalchemy import func
        with self.engine.connect() as conn:
            return conn.scalar(select(func.count()).select_from(outbox).where(outbox.c.sent.is_(False), outbox.c.failed.is_(False)))

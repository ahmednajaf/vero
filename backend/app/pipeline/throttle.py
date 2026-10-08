"""Database-reserved request slots shared by all batch workers and restarts."""

import time
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.db.models import PipelineDomain


class DomainPacer:
    def __init__(
        self,
        engine: Engine,
        domains: tuple[str, ...],
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.engine, self.domains, self.sleep = engine, domains, sleeper

    def __call__(self, host: str, delay: float) -> None:
        # Throttle the approved parent and its subdomains together.
        domain = next(
            (d for d in self.domains if host == d or host.endswith("." + d)), host
        )
        with Session(self.engine) as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": "pipeline-domain:" + domain},
            )
            now = session.scalar(select(func.clock_timestamp()))
            assert now is not None
            row = session.get(PipelineDomain, domain)
            slot = max(now, row.next_allowed_at) if row else now
            if row is None:
                session.add(
                    PipelineDomain(
                        domain=domain, next_allowed_at=slot + timedelta(seconds=delay)
                    )
                )
            else:
                row.next_allowed_at = slot + timedelta(seconds=delay)
            wait = max(0.0, (slot - now).total_seconds())
        if wait:
            self.sleep(wait)

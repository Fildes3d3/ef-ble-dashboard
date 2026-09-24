"""Guarding the login endpoint.

One password protects everything here, so an attacker who can guess freely has only
entropy standing in their way. This makes guessing expensive: a handful of failures
locks the source out for a period that doubles each time.

The state is in memory, which suits a single-process gateway. A restart forgets the
lockouts - acceptable, because a restart needs access to the machine anyway.
"""

import logging
import math
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Attempts:
    failures: int = 0
    last_failure: float = 0.0
    locked_until: float = 0.0


@dataclass
class LoginGuard:
    """Tracks failed sign-ins per source and locks out repeat offenders."""

    # Failures allowed before a lockout begins.
    allowance: int = 5
    # Failures older than this are forgotten, so an occasional typo never accumulates.
    window: float = 900.0
    # First lockout, doubling with each further failure, up to the cap.
    base_lockout: float = 30.0
    max_lockout: float = 3600.0

    _sources: dict[str, Attempts] = field(default_factory=dict)

    def retry_after(self, source: str, now: float) -> float:
        """Seconds the caller must wait, or 0.0 if it may try now."""
        record = self._sources.get(source)
        if record is None:
            return 0.0
        if now - record.last_failure > self.window and now >= record.locked_until:
            # Nothing recent: forget this source entirely.
            del self._sources[source]
            return 0.0
        return max(0.0, record.locked_until - now)

    def record_failure(self, source: str, now: float) -> float:
        """Note a wrong password. Returns the lockout imposed, if any."""
        record = self._sources.setdefault(source, Attempts())
        if now - record.last_failure > self.window:
            record.failures = 0
        record.failures += 1
        record.last_failure = now

        if record.failures <= self.allowance:
            return 0.0

        excess = record.failures - self.allowance
        lockout = min(self.base_lockout * (2 ** (excess - 1)), self.max_lockout)
        record.locked_until = now + lockout
        log.warning(
            "locked out %s for %.0fs after %d failed sign-ins",
            source, lockout, record.failures,
        )
        return lockout

    def record_success(self, source: str) -> None:
        self._sources.pop(source, None)

    def seconds_to_report(self, wait: float) -> int:
        return max(1, math.ceil(wait))

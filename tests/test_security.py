"""The login guard. One password protects everything, so guessing must be expensive."""

from app.security import LoginGuard

IP = "192.0.2.10"


def test_a_fresh_source_may_try_immediately():
    assert LoginGuard().retry_after(IP, now=0.0) == 0.0


def test_occasional_failures_do_not_lock_anyone_out():
    guard = LoginGuard()
    for attempt in range(guard.allowance):
        assert guard.record_failure(IP, now=float(attempt)) == 0.0
    assert guard.retry_after(IP, now=10.0) == 0.0


def test_exceeding_the_allowance_starts_a_lockout():
    guard = LoginGuard()
    for attempt in range(guard.allowance + 1):
        guard.record_failure(IP, now=float(attempt))
    assert guard.retry_after(IP, now=10.0) > 0.0


def test_each_further_failure_doubles_the_wait():
    guard = LoginGuard()
    waits = []
    for attempt in range(guard.allowance + 4):
        lockout = guard.record_failure(IP, now=float(attempt))
        if lockout:
            waits.append(lockout)
    assert waits == sorted(waits), "lockouts must not shrink"
    assert waits[1] == waits[0] * 2
    assert waits[2] == waits[0] * 4


def test_the_lockout_is_capped():
    guard = LoginGuard()
    for attempt in range(60):
        guard.record_failure(IP, now=float(attempt))
    assert guard.retry_after(IP, now=60.0) <= guard.max_lockout


def test_the_lockout_expires():
    guard = LoginGuard()
    for attempt in range(guard.allowance + 1):
        guard.record_failure(IP, now=float(attempt))
    locked_for = guard.retry_after(IP, now=10.0)
    assert guard.retry_after(IP, now=10.0 + locked_for + 1) == 0.0


def test_a_correct_password_clears_the_record():
    guard = LoginGuard()
    for attempt in range(guard.allowance + 1):
        guard.record_failure(IP, now=float(attempt))
    guard.record_success(IP)
    assert guard.retry_after(IP, now=10.0) == 0.0


def test_old_failures_are_forgotten():
    """A typo today must not combine with one a fortnight ago."""
    guard = LoginGuard()
    for attempt in range(guard.allowance):
        guard.record_failure(IP, now=float(attempt))
    later = guard.window + 100
    assert guard.record_failure(IP, now=later) == 0.0, "the old run should have expired"


def test_sources_are_tracked_separately():
    guard = LoginGuard()
    for attempt in range(guard.allowance + 1):
        guard.record_failure(IP, now=float(attempt))
    assert guard.retry_after(IP, now=10.0) > 0.0
    assert guard.retry_after("198.51.100.4", now=10.0) == 0.0


def test_the_reported_wait_is_never_zero_while_locked():
    guard = LoginGuard()
    assert guard.seconds_to_report(0.2) == 1
    assert guard.seconds_to_report(30.4) == 31

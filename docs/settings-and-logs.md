# Settings and logs

Requested 2026-09-18. Not built yet — this is the design note that precedes it.

Three things were asked for: an automated refresh on a set interval, a settings
section to change that interval, and access to logs both live and stored.

## What already exists

**The automated refresh is already there.** `CollectorManager._run()` (`app/manager.py`)
loops continuously, polls each device in turn, then sleeps one interval. The interval is
`Settings.poll_seconds` — `ECOFLOW_POLL_SECONDS`, default 15, floored at 5 in
`config.py`.

What is missing is not the loop. It is that the value is read once at startup into a
frozen dataclass, so changing it means editing `.env` and restarting the gateway.

**Logs are not stored anywhere.** `main.py` calls `logging.basicConfig()` and writes to
stdout. When the process is started from the launcher app rather than a terminal, that
output goes nowhere a person can read. Nothing survives a restart.

## 1. Runtime-configurable interval

`_wait()` already reads `self.settings.poll_seconds` on *every* iteration, so if the
value can change, the next sleep picks it up with no restart and no task restart. That
makes this cheaper than it looks.

`Settings` is `@dataclass(frozen=True)` and should stay that way — it is the boot
configuration and its immutability is worth keeping. Introduce a separate mutable
runtime value instead, owned by the manager, seeded from `Settings` at startup and
persisted to SQLite so it survives restarts. Env remains the bootstrap default; the
stored value wins once set.

**The 5-second floor must stay, and the settings UI must enforce it too.** One BLE cycle
across both devices takes roughly 3 seconds and the radio is serialized behind a single
lock. An interval below the cycle time means the next poll is already due when the
previous finishes, so the loop never idles, the radio never rests, and the coalescing
that fixed the 145-second refresh stops having anything to coalesce. Treat 5s as the
hard minimum and surface a recommended range rather than a free-text box — the control
sliders added for the charger are the right precedent.

Note the coupling: `collector.py` computes its failure backoff as
`poll_seconds * 2 ** (failures - 1)`, capped at 300. Shortening the interval shortens
the backoff, so a device that is off will be retried more aggressively. That is probably
acceptable but should be a deliberate choice, not a surprise.

**API shape:** `GET /api/settings` and `PUT /api/settings`, behind the same session guard
as the control endpoints, validating min/max server-side exactly as the control layer
does. Client-side validation is a convenience, never the enforcement point.

## 2. Settings section

A third view alongside the two device tabs. It holds the interval control now, and is the
natural home for anything else that becomes adjustable later.

Follow the established frontend rule: decisions live in a pure, tested module; the DOM
layer stays thin glue. The interval control is a slider with a labelled range, matching
the charger controls.

## 3. Logs, live and stored

Two different needs, best served by two mechanisms behind one view.

**Live** — a bounded in-memory ring buffer (`collections.deque`, a few hundred records)
attached as a logging handler, drained over Server-Sent Events. SSE fits the existing
single-event-loop FastAPI app and needs no new dependency; websockets would be more
machinery than this earns.

**Stored** — a `RotatingFileHandler` under `data/`, so history survives restarts and
stays greppable from a terminal. A SQLite table is the alternative and would make the
stored view filterable through the existing storage layer; the file is simpler and does
not grow the schema. Pick one, do not do both.

**Both views must sit behind the session guard.** Logs carry the device serial and the
EcoFlow user id. Two rules follow:

- The session secret, admin password and gateway token must never reach a log record.
  Add a filter that redacts them rather than trusting every future call site.
- Logs stay on the van LAN. The relay pushes telemetry only; the internet-facing copy is
  read-only telemetry, and the settings and log views are not part of it. See
  [deployment-plan.md](deployment-plan.md).

## Open questions

- Should the interval be per-device? The alternator changes slowly; the DELTA 2 does not.
  One interval is simpler and is the assumption above.
- Log retention: how long, and capped by size or by age? The telemetry tables already use
  a 30-day retention, which is the obvious precedent.
- Does the van-display kiosk mode need its own interval, separate from the gateway's poll?
  Those are different things — screen refresh versus radio poll — and conflating them
  would be easy.

# Plan: putting the dashboard on the internet

Status: step 3's auth work is done. Next: the relay worker.
Decided 2026-09-17, updated 2026-09-18.

## Decisions already made

| Question | Decision |
| --- | --- |
| How the van reaches the server | **Push relay** — gateway POSTs outbound to the server |
| Controls online | **No.** Telemetry read-only in public; controls stay on the van LAN |

## The constraint that shapes everything

Bluetooth LE is a ~10 m radio. The server cannot read the DELTA 2. The gateway stays
in the van, and the server only ever holds what the gateway chose to send it.

## Build order

1. **Gateway: relay worker.**
   A background task beside the collectors. Track the last acknowledged timestamp per
   table, batch unsent rows, POST them, advance on 2xx. `data/telemetry.sqlite3` is
   already a 30-day buffer, so an offline week backfills on reconnect. Reuse the
   exponential backoff already written for an absent device
   (`DeviceCollector.failed`).

2. **Server: ingest endpoint.**
   `POST /api/ingest`, authenticated by the gateway token, same row shape, same schema.
   Run it as its own small service rather than inside an existing application: it shares
   nothing with the site it sits beside except a reverse proxy, and keeping it separate
   means the public surface stays exactly one endpoint.

3. **Split the auth three ways.** ~~Today one password guards everything.~~
   - ~~rate limiting on `/api/auth/login`~~ **done** — `app/security.py`, five
     attempts then a doubling lockout; the correct password is refused while locked
     so it cannot act as an oracle. 13 tests.
   - ~~a gateway token~~ **done** — `APP_GATEWAY_TOKEN`, separate from the dashboard
     password. Not yet used; the relay (step 1) will send it.
   - the dashboard login behind HTTPS with `APP_COOKIE_SECURE=true` — a deployment
     step, nothing to build.

4. **Keep control local.**
   The public build does not register the control endpoints at all — absent from the
   server, not merely hidden in the UI.

5. **Kiosk mode, for the van displays.**
   Tokened read-only URL, no login, large type, no chrome, auto-refresh. Needs the
   actual screens named first: a 7" Pi touchscreen and an e-ink panel want different
   layouts.

## Settled

- The alternator's **100 W** `power_limit`/`power_max` is a deliberate configuration,
  not a fault or an undiscovered ceiling (confirmed 2026-09-18).
- Suspend detection works and is verified against real sleeps; see
  `docs/architecture.md` for why the obvious clock-divergence method does not.

## Hard-won constraints

- **Auto-restart is available but deliberately not installed.** Start it manually if you prefer. `scripts/install_launchagent.sh` installs it (verified:
  back in 20s after a kill) and should be installed on whatever machine ends up wired
  into the van. Sleep/wake recovers on its own either way.
- **The gateway must stay powered.** On 2026-09-18 the laptop hibernated at 1% battery
  and the record lost 6.5 hours (00:31-07:00 UTC). A Mac mini or Pi wired into the van,
  not a laptop.
- **System sleep poisons cached Bluetooth handles.** A 22-second clamshell sleep left
  both devices connecting and authenticating but delivering no notifications, silently,
  for ten hours. Handled in code now (an empty read drops the cache and rescans), but
  worth remembering as a class of failure: the connection succeeding is not evidence
  that data is arriving.

## Open questions

- Which displays are going in the van, and where, before kiosk mode is designed.

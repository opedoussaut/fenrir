# LeBlond integration — specification and client

Status: **specification + tested protocol client. LeBlond itself has not been modified.**
Nothing here touches LeBlond's repository, database or deployment.

## What was verified in the LeBlond codebase (read-only, 2026-11-16)

| Fact | Where |
|---|---|
| Next.js 16 (App Router), React 19, TypeScript, Tailwind 4; PWA with manifest and service worker | `package.json`, `app/manifest.ts`, `lib/offline/` |
| Supabase (Postgres, auth, row-level security); SQL migrations and SQL tests | `supabase/migrations`, `supabase/tests` |
| Vitest unit tests, Playwright end-to-end, zod validation | `package.json` |
| User-facing strings in French (default) and English | `lib/i18n` |
| Analytics are pure functions with tests; no formulas in JSX | `CLAUDE.md`, `lib/analytics` |
| External data sources are adapters with a registry and an honest status; "never fake a Connected state" | `lib/integrations/wearables/{types,registry,status}.ts` |
| A training set already records `seconds`, `load_kg`, `edge_mm` (3–60), `side` (LEFT/RIGHT/BOTH), `details` JSON | `training_exercise_sets` in `lib/supabase/database.types.ts`, migration `20261117000000_set_edge.sql` |
| The assessment protocol tags each value with an evidence level: measured / observed / self / estimated / insufficient | `lib/training/assessment-protocol.ts` |
| Required checks before finishing: lint, typecheck, unit tests, build, database tests | `CLAUDE.md` |

Not examined: UI component structure in detail, the coach context builder, authentication flows.

## Integration boundary

```
LeBlond UI (components/training/…)            ← new screens only
        │
lib/analytics/force.ts                         ← pure functions: peak, mean, TUT, RFD, fatigue
        │
lib/integrations/force/                        ← this folder's src/, vendored
   protocol.ts   bytes ⇄ packets (pinned to protocol/vectors/v1.txt)
   recording.ts  packets → time series + link statistics
   device.ts     ForceDevice (commands, state) over a Transport
        │
Transport:  WebBluetoothTransport │ native bridge │ SimulatedTransport
```

Rules carried over from LeBlond's own conventions:

- The connection state shown to the user comes only from `ForceDevice.connection`. No optimistic
  "connected".
- A FENRIR result has evidence level **measured** only when the recording is calibrated, has no fault
  packets and stays inside the device's verified range (`CalInfo.maxRefN`). Otherwise it is stored and
  shown as **estimated**, with the reason.
- Battery is shown only when the device reports it (`batteryPct !== null`).
- Metrics are computed by `lib/analytics/force.ts`, never by the coach model and never in components.

## Platform support for Bluetooth

From general knowledge of the platforms as of mid-2026; **to be re-verified on real devices in Phase 5.**

| Environment | Web Bluetooth | Route |
|---|---|---|
| Chrome / Edge on Android | Yes | `WebBluetoothTransport` in the PWA |
| Chrome / Edge on Windows, macOS, ChromeOS, Linux | Yes | Same |
| Safari on iOS / iPadOS, and every other iOS browser (all use WebKit) | **No** | Native bridge, or a third-party browser that implements Web Bluetooth (e.g. Bluefy) as a stop-gap |
| Safari on macOS, Firefox | No | Use Chrome/Edge |

Proposed order: (1) Web Bluetooth for Android and desktop; (2) test the stop-gap browser on an iPhone;
(3) if iPhone support matters, wrap the PWA in a thin native shell (Capacitor) exposing a BLE plugin
as another `Transport`. The data model and everything above `Transport` stay identical.

Web Bluetooth needs HTTPS and a user gesture for the device chooser, and does not let a page reconnect
silently in the background.

## Proposed data model (not applied — needs approval)

One new table, linked to the existing set when the recording belongs to one:

| Column | Type | Note |
|---|---|---|
| `id`, `user_id`, `created_at` | | RLS: owner only, like every user table |
| `set_id` | uuid, nullable → `training_exercise_sets` | Reuses `edge_mm`, `side`, `load_kg`, `seconds` already there |
| `kind` | enum: `max_pull`, `no_hang`, `repeater`, `sustained`, `free` | |
| `grip` | text / enum | half-crimp, open hand, … (existing vocabulary to be checked) |
| `started_at`, `duration_s`, `sample_rate_hz` | | Rate as measured, not nominal |
| `device_serial`, `firmware_rev`, `hardware_rev`, `protocol_version` | text | From Device Information |
| `calibration` | jsonb | Snapshot of CalInfo at recording time (valid, max_ref_n, date, points) |
| `link` | jsonb | Packets, lost packets, estimated lost samples, fault packets |
| `evidence` | existing evidence-level vocabulary | measured / estimated |
| `summary` | jsonb | peak_n, mean_n, tut_s, rfd (with the windows used), fatigue_index |
| `samples` | storage object reference | `fenrir.recording/1` JSON (same schema as the Python export), gzip. A 90 SPS, 60 s recording is ~5 400 rows |

Raw counts are kept in the stored recording so results can be recomputed if a calibration is corrected.
Exports: CSV and the `fenrir.recording/1` JSON, identical to the Python tool's.

## Implementation plan (Phase 5, on a dedicated LeBlond branch, after hardware validation)

1. Vendor `src/` into `lib/integrations/force/`; port `software/fenrir/metrics.py` to
   `lib/analytics/force.ts` with the same test cases (V-20).
2. Add a simulated transport so every screen works without hardware (and in Playwright).
3. Device screen: discover, connect, status, battery, firmware, calibration status.
4. Live screen: force-time graph, peak, tare, start / pause / stop.
5. Migration + RLS + SQL test for the table above; save and list recordings.
6. Protocol-driven tests: max pull, no-hang, repeaters, timed contractions; left/right comparison
   only when edge, grip and protocol match.
7. History and progression views; CSV/JSON export.
8. Run LeBlond's full check list; confirm no existing test changed.

## Using the client

```ts
const dev = new ForceDevice(new WebBluetoothTransport(), {
  onForce: (p) => recording.add(p),
  onConnection: (s) => setConnection(s),
});
await dev.connect();      // from a click handler
await dev.tare();         // rejects if the device is not at rest
await dev.start();        // raw + force, 4 samples per notification
```

Tests: `npm test` (Node ≥ 22.18, no dependencies).

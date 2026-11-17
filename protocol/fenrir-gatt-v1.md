# FENRIR GATT protocol — version 1.1

Status: **draft, implemented in firmware core, Python and TypeScript; not yet exercised over a real BLE link.**

Three independent codecs implement this document and are pinned to the same bytes by
[`vectors/v1.txt`](vectors/v1.txt): `firmware/src/core/protocol.c` (generates the file),
`software/fenrir/protocol.py` and `software/leblond-integration/src/protocol.ts` (both tested against it).

All multi-byte fields are little-endian. `i24` is a 24-bit two's-complement integer.

## Services

| Service | UUID | Notes |
|---|---|---|
| FENRIR | `f3e70001-6b1d-4c8a-9e2f-5a1c0d7e4b90` | Advertised. All characteristics below share the base `f3e7XXXX-…`. |
| Device Information | `0x180A` | Manufacturer `2A29`, model `2A24`, serial `2A25`, firmware revision `2A26`, hardware revision `2A27`. |
| Battery | `0x180F` | Level `2A19`. Not updated when the level is unknown. |

Device name: `FENRIR-XXXX` (last four hex digits of the serial).

| Characteristic | UUID suffix | Properties | Length |
|---|---|---|---|
| Force data | `0002` | notify | 12 + 3·n or 12 + 6·n |
| Control point | `0003` | write, notify | command: 1–16; response: 2 |
| Status | `0004` | read, notify | 16 |
| Calibration | `0005` | read | 20 |
| Protocol version | `0006` | read | 2 (`major`, `minor`) |

A client must read **Protocol version** first and refuse to continue if `major` differs from its own.
Minor versions only add things (new opcodes, new status bits, bytes appended to Status/Calibration).

## Force data

| Offset | Type | Field | Meaning |
|---:|---|---|---|
| 0 | u16 | `seq` | Notification counter, +1 per packet, wraps. Reset to 0 by START. |
| 2 | u32 | `t0_us` | Device clock at the first sample of the packet, µs. Wraps every 71.6 min. |
| 6 | u16 | `dt_us` | Sample period **as measured by the device**, µs (≈11111 at 90 SPS, ≈2857 at 350 SPS). |
| 8 | u16 | `status` | Status flags (below), OR-ed over the samples in this packet. |
| 10 | u8 | `format` | 0 = raw + force, 1 = force only. |
| 11 | u8 | `count` | Samples in this packet, 1–40. |
| 12 | … | samples | `count` × sample. |

Sample, format 0: `i24 raw` (ADC counts, untouched) then `i24 force` (centinewtons).
Sample, format 1: `i24 force` only.

- Sample *i* was taken at `t0_us + i·dt_us`.
- `force` is `(raw − zero − tare) × scale`, rounded to 0.01 N, saturated to ±83 886.07 N.
  The code `0x800000` (−8 388 608) is reserved: **no valid force for this sample** (e.g. ADC clipped).
  Clients must treat it as missing, never as a number.
- `raw` is never filtered, tared or scaled. If `FILTERED` is set, `force` has been low-pass filtered on
  the device; `raw` has not. A client that wants unfiltered force can recompute it from `raw` and the
  Calibration characteristic.

### Status flags

| Bit | Name | Meaning | Trust samples? |
|---:|---|---|---|
| 0 | STREAMING | Acquisition running | — |
| 1 | CAL_VALID | A stored calibration is in use. Clear = datasheet-nominal scale only | force is indicative only when clear |
| 2 | TARED | Non-zero user tare applied | — |
| 3 | OVERLOAD | \|force\| above 2200 N in this packet | yes, but stop loading |
| 4 | ADC_SATURATED | ADC code at a rail; affected samples carry the invalid code | **no** |
| 5 | ADC_TIMEOUT | Conversions stopped arriving | **no** |
| 6 | ADC_STUCK | ADC code frozen (dead ADC / open bridge wire) | **no** |
| 7 | SAMPLE_DROPPED | The device lost samples or a notification before this packet | gap before this packet |
| 8 | LOW_BATTERY | Battery ≤ 10 % | — |
| 9 | FILTERED | `force` values are device-filtered | — |
| 10 | SLEW | Implausible jump between consecutive samples (> 1000 N) | suspect |
| 11 | CONFIG_CRC | Stored configuration was corrupt; defaults loaded | calibration lost |
| 12 | ADC_FAULT | ADC failed to initialise | **no** |

### Throughput and loss detection

Payload per notification is `ATT_MTU − 3`. The device clamps the requested batch to what fits.

| ATT MTU | Format | Max samples/packet | 90 SPS, batch 4 | 350 SPS, batch 16 |
|---:|---|---:|---|---|
| 23 (no MTU exchange) | raw+force | 1 | 90 notif/s × 18 B = 1.6 kB/s | 350 notif/s — **not expected to be sustainable** |
| 23 | force only | 2 | 45 notif/s × 18 B | 175 notif/s — marginal |
| 247 | raw+force | 38 | 22.5 notif/s × 36 B = 0.81 kB/s | 21.9 notif/s × 108 B = 2.4 kB/s |

These are computed figures; real throughput and loss must be measured (tests V-10, V-11).

Loss is detected, never concealed:
- a gap in `seq` = lost notifications (`gap − 1` packets);
- the jump in `t0_us` beyond `count·dt_us` estimates how many samples that was;
- the device sets `SAMPLE_DROPPED` when it knows it lost data on its side.

Clients must keep the time axis from `t0_us`/`dt_us` and leave gaps as gaps (no interpolation, no
re-spacing). Buffering latency is `batch / rate` (44 ms at batch 4, 90 SPS) plus the connection interval.

## Control point

Write `[opcode, payload…]` with response. The device answers with a notification `[opcode, result]`.
One command at a time.

| Opcode | Name | Payload | Rules |
|---:|---|---|---|
| 0x01 | START | `format u8`, `batch u8` (1–40) | Resets `seq`. Batch is clamped to the MTU. |
| 0x02 | STOP | — | |
| 0x03 | TARE | — | Averages 40 samples. Answer arrives after the window. `BAD_STATE` if the signal moved (not at rest). Tare is not persisted. |
| 0x04 | CLEAR_TARE | — | |
| 0x05 | SET_RATE | `sps u16` = 90 or 350 | Not while streaming. Persisted. The 1.0 values 80 and 320 are accepted and mapped to 90 and 350; Status `sample_rate` always reports the real rate. |
| 0x06 | SET_FILTER | `type u8`, `param u8` | 0 none; 1 moving average of `param` (2–32) samples; 2 one-pole IIR, α = 2^−`param` (1–8). Persisted. |
| 0x10 | CAL_WRITE | `scale f32` (N/count), `zero i32`, `max_ref_n u16`, `n_points u8` (≥ 2), `unix_time u32` | Not while streaming. Clears tare. Persisted with CRC. |
| 0x11 | CAL_CLEAR | — | Back to the nominal scale; CAL_VALID clears. |
| 0x20 | GET_STATUS | — | Forces a Status notification. |
| 0x30 | SLEEP | — | Deep sleep. |

Results: 0 OK, 1 UNKNOWN_OP, 2 BAD_LENGTH, 3 BAD_PARAM, 4 BAD_STATE, 5 HW_ERROR.

## Status (16 bytes)

`state u8` (0 boot, 1 idle, 2 streaming, 3 error) · `last_error u8` · `flags u16` · `battery_pct u8`
(0xFF = unknown) · reserved u8 · `battery_mv u16` (0 = unknown) · `sample_rate u16` · `filter_type u8` ·
`filter_param u8` · `uptime_s u32`. Notified every 5 s and after each command.

## Calibration (20 bytes)

`valid u8` · `n_points u8` · `max_ref_n u16` · `scale f32` · `zero i32` · `tare i32` · `unix_time u32`.

`max_ref_n` is the largest reference force used. An application must show readings above it as
**outside the verified range**, whatever the display range of the device.

## Connection behaviour

- On disconnect the device stops streaming and re-advertises. A reconnecting client must START again.
- The device sleeps after 10 minutes with no connection.
- No pairing or encryption in v1: force data is not sensitive, but anyone in range can write a
  calibration. Accepted for the prototype; revisit before distribution (decision D-011).

## Relation to the Tindeq Progressor API

Independent design. Tindeq's public page describes a control point and a data point using TLV framing;
FENRIR does not reuse its UUIDs, opcodes or packet layout, and is not wire-compatible with it.

## Version history

| Version | Change |
|---|---|
| 1.0 | First draft (NAU7802 rates 80 / 320 SPS). Never deployed on hardware. |
| 1.1 | 2026-11-17, decision D-024 (ADS1220 ADC). Rates become 90 / 350 SPS (ADS1220 turbo mode has no 80 or 320 SPS setting). SET_RATE still accepts 80 and 320 and maps them, so a 1.0 client keeps working; it must read the real rate from Status. Reference vectors updated to the new rates. |


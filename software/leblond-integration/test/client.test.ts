import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CommandError, ForceDevice, type Transport } from "../src/device.ts";
import {
  Format, Op, ProtocolError, Result, Status, UUID, decodeCalInfo, decodeForce, decodeResponse, decodeStatus,
  forceCapacity,
} from "../src/protocol.ts";
import { ForceRecording } from "../src/recording.ts";

const vectors = Object.fromEntries(
  readFileSync(new URL("../../../protocol/vectors/v1.txt", import.meta.url), "utf8")
    .trim().split(/\r?\n/).map((l) => l.split(" ")),
) as Record<string, string>;
const hex = (s: string) => Uint8Array.from(s.match(/../g)!.map((h) => parseInt(h, 16)));

test("decodes the firmware reference vectors", () => {
  const p = decodeForce(hex(vectors.force_raw));
  assert.deepEqual(p, {
    seq: 7, t0Us: 1234567890, dtUs: 12500, status: Status.STREAMING | Status.CAL_VALID | Status.TARED,
    format: Format.RAW_FORCE, raw: [1000, 108374, -5, 8388607], forceCn: [0, 10000, -1, null],
  });
  const q = decodeForce(hex(vectors.force_only));
  assert.equal(q.seq, 65535);
  assert.equal(q.dtUs, 3125);
  assert.deepEqual(q.raw, []);
  assert.deepEqual(q.forceCn, [0, 10000, -1, null]);
  const s = decodeStatus(hex(vectors.status));
  assert.deepEqual([s.state, s.batteryPct, s.batteryMv, s.sampleRate, s.uptimeS], [2, 87, 4012, 80, 3600]);
  const c = decodeCalInfo(hex(vectors.calinfo));
  assert.deepEqual([c.valid, c.nPoints, c.maxRefN, c.zeroCounts, c.tareCounts, c.unixTime], [true, 5, 490, -20000, 150, 1794000000]);
  assert.equal(c.scaleNPerCount, 15625 / 2 ** 24);
  assert.deepEqual(decodeResponse(hex(vectors.response)), { op: Op.TARE, result: Result.BAD_STATE });
});

test("rejects malformed packets", () => {
  const good = hex(vectors.force_raw);
  assert.throws(() => decodeForce(good.slice(0, -1)), ProtocolError);
  assert.throws(() => decodeForce(good.slice(0, 5)), ProtocolError);
  const badFormat = good.slice();
  badFormat[10] = 9;
  assert.throws(() => decodeForce(badFormat), ProtocolError);
  assert.equal(decodeStatus(Uint8Array.from([1, 0, 0, 0, 0xff, 0, 0, 0, 80, 0, 0, 0, 0, 0, 0, 0])).batteryPct, null);
});

test("capacity follows the MTU", () => {
  assert.equal(forceCapacity(23, Format.RAW_FORCE), 1);
  assert.equal(forceCapacity(247, Format.RAW_FORCE), 38);
  assert.equal(forceCapacity(517, Format.FORCE), 40);
});

const packet = (seq: number, t0Us: number, status: number = Status.STREAMING | Status.CAL_VALID) => ({
  seq, t0Us, dtUs: 12500, status, format: Format.FORCE, raw: [], forceCn: [100, 200, null, 400] as (number | null)[],
});

test("recording counts gaps, unwraps the clock and drops reordered packets", () => {
  const r = new ForceRecording();
  const start = 2 ** 32 - 60000;
  r.add(packet(65534, start));
  r.add(packet(65535, start + 50000));
  r.add(packet(1, (start + 150000) % 2 ** 32)); // seq 0 lost, clock wrapped
  r.add(packet(65535, start + 50000)); // late duplicate
  assert.equal(r.stats.packets, 3);
  assert.equal(r.stats.lostPackets, 1);
  assert.equal(r.stats.lostSamplesEst, 4);
  assert.equal(r.stats.duplicateOrReordered, 1);
  assert.equal(r.samples.length, 12);
  assert.ok(Math.abs(r.samples[8].t - 0.15) < 1e-9);
  assert.equal(r.samples[2].forceN, null);
  assert.equal(r.peakN(), 4);
  assert.ok(Math.abs(r.packetLossRatio - 0.25) < 1e-12);
  assert.equal(r.calibrated, true);
  r.add(packet(2, 300000, Status.STREAMING | Status.ADC_STUCK));
  assert.equal(r.calibrated, false);
  assert.equal(r.stats.faultPackets, 1);
});

class FakeTransport implements Transport {
  written: Uint8Array[] = [];
  subs = new Map<string, (d: Uint8Array) => void>();
  drop: () => void = () => {};
  version = Uint8Array.of(1, 0);
  reply: ((data: Uint8Array) => Uint8Array | null) = (d) => Uint8Array.of(d[0], Result.OK);
  async connect() {}
  async disconnect() {}
  async read(id: string) {
    if (id === UUID.protocol) return this.version;
    return hex(id === UUID.status ? vectors.status : vectors.calinfo);
  }
  async write(_id: string, data: Uint8Array) {
    this.written.push(data);
    const r = this.reply(data);
    if (r) queueMicrotask(() => this.subs.get(UUID.control)!(r));
  }
  async subscribe(id: string, onData: (d: Uint8Array) => void) {
    this.subs.set(id, onData);
  }
  onDisconnect(h: () => void) {
    this.drop = h;
  }
}

test("device: connect, commands, errors, malformed data and disconnect", async () => {
  const t = new FakeTransport();
  const states: string[] = [];
  const errors: unknown[] = [];
  const forces: number[] = [];
  const dev = new ForceDevice(t, {
    onConnection: (s) => states.push(s),
    onProtocolError: (e) => errors.push(e),
    onForce: (p) => forces.push(p.seq),
  });
  await assert.rejects(dev.start(), /not connected/);
  await dev.connect();
  assert.equal(dev.calibration?.maxRefN, 490);
  assert.equal(dev.isStreaming, true);

  await dev.start(Format.RAW_FORCE, 4);
  assert.deepEqual([...t.written[0]], [Op.START, 0, 4]);
  t.reply = (d) => Uint8Array.of(d[0], Result.BAD_STATE);
  await assert.rejects(dev.tare(), (e) => e instanceof CommandError && e.result === Result.BAD_STATE);

  t.subs.get(UUID.force)!(hex(vectors.force_raw));
  t.subs.get(UUID.force)!(hex(vectors.force_raw).slice(0, 7)); // truncated notification
  assert.deepEqual(forces, [7]);
  assert.equal(errors.length, 1);

  t.reply = () => null; // device never answers
  const hung = dev.command(Uint8Array.of(Op.STOP), 20);
  await assert.rejects(dev.stop(), /in flight/);
  await assert.rejects(hung, /timed out/);

  const inFlight = dev.command(Uint8Array.of(Op.STOP), 5000);
  t.drop();
  await assert.rejects(inFlight, /disconnected/);
  assert.deepEqual(states, ["connecting", "connected", "disconnected"]);
});

test("device refuses an incompatible protocol major version", async () => {
  const t = new FakeTransport();
  t.version = Uint8Array.of(2, 0);
  const dev = new ForceDevice(t);
  await assert.rejects(dev.connect(), /protocol 2\.0/);
  assert.equal(dev.connection, "disconnected");
});

/**
 * FENRIR GATT protocol v1 codec (see protocol/fenrir-gatt-v1.md).
 * Dependency-free and runtime-agnostic (browser, Node, React Native).
 * Pinned to protocol/vectors/v1.txt together with the firmware and Python codecs.
 */

export const PROTOCOL_MAJOR = 1;

const uuid = (n: number) => `f3e7${n.toString(16).padStart(4, "0")}-6b1d-4c8a-9e2f-5a1c0d7e4b90`;
export const UUID = {
  service: uuid(1),
  force: uuid(2),
  control: uuid(3),
  status: uuid(4),
  calibration: uuid(5),
  protocol: uuid(6),
} as const;

export const FORCE_HEADER_LEN = 12;
export const MAX_SAMPLES_PER_PACKET = 40;
const FORCE_INVALID = -8388608;

export const Format = { RAW_FORCE: 0, FORCE: 1 } as const;
export type Format = (typeof Format)[keyof typeof Format];

export const Status = {
  STREAMING: 1 << 0,
  CAL_VALID: 1 << 1,
  TARED: 1 << 2,
  OVERLOAD: 1 << 3,
  ADC_SATURATED: 1 << 4,
  ADC_TIMEOUT: 1 << 5,
  ADC_STUCK: 1 << 6,
  SAMPLE_DROPPED: 1 << 7,
  LOW_BATTERY: 1 << 8,
  FILTERED: 1 << 9,
  SLEW: 1 << 10,
  CONFIG_CRC: 1 << 11,
  ADC_FAULT: 1 << 12,
} as const;

/** Flags that mean "do not trust the samples in this packet". */
export const FAULT_FLAGS =
  Status.ADC_SATURATED | Status.ADC_TIMEOUT | Status.ADC_STUCK | Status.SAMPLE_DROPPED | Status.ADC_FAULT;

export const Op = {
  START: 0x01,
  STOP: 0x02,
  TARE: 0x03,
  CLEAR_TARE: 0x04,
  SET_RATE: 0x05,
  SET_FILTER: 0x06,
  CAL_WRITE: 0x10,
  CAL_CLEAR: 0x11,
  GET_STATUS: 0x20,
  SLEEP: 0x30,
} as const;

export const Result = { OK: 0, UNKNOWN_OP: 1, BAD_LENGTH: 2, BAD_PARAM: 3, BAD_STATE: 4, HW_ERROR: 5 } as const;
export const DeviceState = { BOOT: 0, IDLE: 1, STREAMING: 2, ERROR: 3 } as const;

export class ProtocolError extends Error {}

export interface ForcePacket {
  seq: number;
  /** Device clock at the first sample, microseconds, wraps at 2^32. */
  t0Us: number;
  /** Sample period measured by the device, microseconds. */
  dtUs: number;
  status: number;
  format: Format;
  /** Untouched ADC counts; empty for Format.FORCE. */
  raw: number[];
  /** Force in centinewtons; null where the device reported no valid force. */
  forceCn: (number | null)[];
}

export interface DeviceStatus {
  state: number;
  lastError: number;
  flags: number;
  /** null when the device cannot measure its battery. Never a guess. */
  batteryPct: number | null;
  batteryMv: number | null;
  sampleRate: number;
  filterType: number;
  filterParam: number;
  uptimeS: number;
}

export interface CalInfo {
  valid: boolean;
  nPoints: number;
  /** Largest reference force used when calibrating, newtons. */
  maxRefN: number;
  scaleNPerCount: number;
  zeroCounts: number;
  tareCounts: number;
  unixTime: number;
}

const view = (b: Uint8Array) => new DataView(b.buffer, b.byteOffset, b.byteLength);
const i24 = (b: Uint8Array, o: number) => ((b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)) << 8) >> 8;
const sampleSize = (fmt: number) => {
  if (fmt === Format.RAW_FORCE) return 6;
  if (fmt === Format.FORCE) return 3;
  throw new ProtocolError(`unknown sample format ${fmt}`);
};

export function forceCapacity(attMtu: number, fmt: Format): number {
  const n = Math.floor((attMtu - 3 - FORCE_HEADER_LEN) / sampleSize(fmt));
  return Math.max(0, Math.min(n, MAX_SAMPLES_PER_PACKET));
}

export function decodeForce(b: Uint8Array): ForcePacket {
  if (b.length < FORCE_HEADER_LEN) throw new ProtocolError("force packet shorter than header");
  const v = view(b);
  const format = b[10];
  const count = b[11];
  const ss = sampleSize(format);
  if (count < 1 || count > MAX_SAMPLES_PER_PACKET || b.length !== FORCE_HEADER_LEN + ss * count) {
    throw new ProtocolError("force packet length does not match its header");
  }
  const raw: number[] = [];
  const forceCn: (number | null)[] = [];
  let o = FORCE_HEADER_LEN;
  for (let i = 0; i < count; i++) {
    if (format === Format.RAW_FORCE) {
      raw.push(i24(b, o));
      o += 3;
    }
    const f = i24(b, o);
    o += 3;
    forceCn.push(f === FORCE_INVALID ? null : f);
  }
  return {
    seq: v.getUint16(0, true),
    t0Us: v.getUint32(2, true),
    dtUs: v.getUint16(6, true),
    status: v.getUint16(8, true),
    format: format as Format,
    raw,
    forceCn,
  };
}

export function decodeStatus(b: Uint8Array): DeviceStatus {
  if (b.length !== 16) throw new ProtocolError("bad status length");
  const v = view(b);
  const pct = b[4];
  const mv = v.getUint16(6, true);
  return {
    state: b[0],
    lastError: b[1],
    flags: v.getUint16(2, true),
    batteryPct: pct === 0xff ? null : pct,
    batteryMv: mv === 0 ? null : mv,
    sampleRate: v.getUint16(8, true),
    filterType: b[10],
    filterParam: b[11],
    uptimeS: v.getUint32(12, true),
  };
}

export function decodeCalInfo(b: Uint8Array): CalInfo {
  if (b.length !== 20) throw new ProtocolError("bad calibration info length");
  const v = view(b);
  return {
    valid: b[0] === 1,
    nPoints: b[1],
    maxRefN: v.getUint16(2, true),
    scaleNPerCount: v.getFloat32(4, true),
    zeroCounts: v.getInt32(8, true),
    tareCounts: v.getInt32(12, true),
    unixTime: v.getUint32(16, true),
  };
}

export function decodeResponse(b: Uint8Array): { op: number; result: number } {
  if (b.length !== 2) throw new ProtocolError("bad response length");
  return { op: b[0], result: b[1] };
}

export const cmdStart = (format: Format = Format.RAW_FORCE, batch = 4) => Uint8Array.of(Op.START, format, batch);
export const cmdSimple = (op: number) => Uint8Array.of(op);
export const cmdSetRate = (sps: 80 | 320) => Uint8Array.of(Op.SET_RATE, sps & 0xff, sps >> 8);
export const cmdSetFilter = (type: 0 | 1 | 2, param = 0) => Uint8Array.of(Op.SET_FILTER, type, param);

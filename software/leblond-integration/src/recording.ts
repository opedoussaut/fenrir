/**
 * Transport-independent force recording: orders packets, unwraps the device
 * clock, and counts what was lost. Same rules as software/fenrir/model.py.
 * Pure data + pure functions, in the spirit of LeBlond's lib/analytics.
 */
import { FAULT_FLAGS, Status, type ForcePacket } from "./protocol.ts";

export const N_PER_KGF = 9.80665;
export const N_PER_LBF = 4.4482216152605;

export interface ForceSample {
  /** Seconds since the first sample of the recording (device clock). */
  t: number;
  /** Newtons, or null where the device flagged the value invalid. */
  forceN: number | null;
  raw: number | null;
  flags: number;
}

export interface LinkStats {
  packets: number;
  samples: number;
  lostPackets: number;
  lostSamplesEst: number;
  duplicateOrReordered: number;
  faultPackets: number;
}

export class ForceRecording {
  readonly samples: ForceSample[] = [];
  readonly stats: LinkStats = {
    packets: 0, samples: 0, lostPackets: 0, lostSamplesEst: 0, duplicateOrReordered: 0, faultPackets: 0,
  };
  /** True once any packet carried device-side filtered force. */
  filtered = false;
  /** False once any packet came from an uncalibrated device. */
  calibrated = true;

  private lastSeq: number | null = null;
  private lastT0: number | null = null;
  private epochUs = 0;
  private originUs: number | null = null;
  private expectedNextUs: number | null = null;

  add(p: ForcePacket): void {
    if (this.lastSeq !== null) {
      const gap = (p.seq - this.lastSeq) & 0xffff;
      if (gap === 0 || gap > 0x8000) {
        this.stats.duplicateOrReordered++;
        return;
      }
      if (gap > 1) this.stats.lostPackets += gap - 1;
    }
    this.lastSeq = p.seq;

    if (this.lastT0 !== null && p.t0Us < this.lastT0 && this.lastT0 - p.t0Us > 2 ** 31) this.epochUs += 2 ** 32;
    this.lastT0 = p.t0Us;
    const t0 = this.epochUs + p.t0Us;
    this.originUs ??= t0;
    if (this.expectedNextUs !== null && p.dtUs > 0) {
      const missing = Math.round((t0 - this.expectedNextUs) / p.dtUs);
      if (missing > 0) this.stats.lostSamplesEst += missing;
    }
    const count = p.forceCn.length;
    this.expectedNextUs = t0 + count * p.dtUs;

    this.stats.packets++;
    this.stats.samples += count;
    if (p.status & FAULT_FLAGS) this.stats.faultPackets++;
    if (p.status & Status.FILTERED) this.filtered = true;
    if (!(p.status & Status.CAL_VALID)) this.calibrated = false;
    for (let i = 0; i < count; i++) {
      const f = p.forceCn[i];
      this.samples.push({
        t: (t0 - this.originUs + i * p.dtUs) / 1e6,
        forceN: f === null ? null : f / 100,
        raw: p.raw.length ? p.raw[i] : null,
        flags: p.status,
      });
    }
  }

  get packetLossRatio(): number {
    const total = this.stats.packets + this.stats.lostPackets;
    return total ? this.stats.lostPackets / total : 0;
  }

  /** Peak of the valid samples, or null if there are none. */
  peakN(): number | null {
    let peak: number | null = null;
    for (const s of this.samples) if (s.forceN !== null && (peak === null || s.forceN > peak)) peak = s.forceN;
    return peak;
  }
}

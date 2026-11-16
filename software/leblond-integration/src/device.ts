/**
 * Device abstraction: the application talks to `ForceDevice`; how bytes reach
 * the hardware is a `Transport`. Web Bluetooth is one transport; a native
 * bridge (Capacitor/React Native) or the simulator are others. Nothing above
 * this file may depend on which one is in use.
 *
 * STATUS: WebBluetoothTransport has not been exercised against hardware.
 */
import {
  DeviceState, Op, PROTOCOL_MAJOR, Result, UUID, cmdSimple, cmdStart, decodeCalInfo, decodeForce,
  decodeResponse, decodeStatus, type CalInfo, type DeviceStatus, type ForcePacket, type Format,
} from "./protocol.ts";

export interface Transport {
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  read(characteristic: string): Promise<Uint8Array>;
  write(characteristic: string, data: Uint8Array): Promise<void>;
  subscribe(characteristic: string, onData: (data: Uint8Array) => void): Promise<void>;
  onDisconnect(handler: () => void): void;
}

export type ConnectionState = "disconnected" | "connecting" | "connected";

export class CommandError extends Error {
  readonly op: number;
  readonly result: number;
  constructor(op: number, result: number) {
    super(`FENRIR command 0x${op.toString(16)} failed with result ${result}`);
    this.op = op;
    this.result = result;
  }
}

export interface ForceDeviceEvents {
  onForce?: (p: ForcePacket) => void;
  onStatus?: (s: DeviceStatus) => void;
  onConnection?: (s: ConnectionState) => void;
  /** Malformed data from the device; the packet is dropped, never guessed at. */
  onProtocolError?: (e: unknown) => void;
}

export class ForceDevice {
  private readonly transport: Transport;
  private readonly events: ForceDeviceEvents;
  private state: ConnectionState = "disconnected";
  private pending: { op: number; resolve: () => void; reject: (e: Error) => void; timer: ReturnType<typeof setTimeout> } | null = null;
  calibration: CalInfo | null = null;
  status: DeviceStatus | null = null;

  constructor(transport: Transport, events: ForceDeviceEvents = {}) {
    this.transport = transport;
    this.events = events;
    transport.onDisconnect(() => {
      this.failPending(new Error("disconnected"));
      this.setState("disconnected");
    });
  }

  get connection(): ConnectionState {
    return this.state;
  }

  async connect(): Promise<void> {
    this.setState("connecting");
    try {
      await this.transport.connect();
      const ver = await this.transport.read(UUID.protocol);
      if (ver[0] !== PROTOCOL_MAJOR) {
        throw new Error(`Device speaks FENRIR protocol ${ver[0]}.${ver[1]}; this client speaks ${PROTOCOL_MAJOR}.x`);
      }
      this.calibration = decodeCalInfo(await this.transport.read(UUID.calibration));
      this.status = decodeStatus(await this.transport.read(UUID.status));
      await this.transport.subscribe(UUID.control, (d) => this.onResponse(d));
      await this.transport.subscribe(UUID.status, (d) => this.guard(() => {
        this.status = decodeStatus(d);
        this.events.onStatus?.(this.status);
      }));
      await this.transport.subscribe(UUID.force, (d) => this.guard(() => this.events.onForce?.(decodeForce(d))));
      this.setState("connected");
    } catch (e) {
      await this.transport.disconnect().catch(() => {});
      this.setState("disconnected");
      throw e;
    }
  }

  async disconnect(): Promise<void> {
    await this.transport.disconnect();
    this.setState("disconnected");
  }

  /** After a reconnect the device is idle: the caller must start() again. */
  start(format?: Format, batch?: number): Promise<void> {
    return this.command(cmdStart(format, batch));
  }
  stop(): Promise<void> {
    return this.command(cmdSimple(Op.STOP));
  }
  /** Rejects with BAD_STATE if the device is not at rest. Takes ~0.5 s. */
  async tare(): Promise<void> {
    await this.command(cmdSimple(Op.TARE));
    this.calibration = decodeCalInfo(await this.transport.read(UUID.calibration));
  }

  get isStreaming(): boolean {
    return this.status?.state === DeviceState.STREAMING;
  }

  command(data: Uint8Array, timeoutMs = 5000): Promise<void> {
    if (this.state !== "connected") return Promise.reject(new Error("not connected"));
    if (this.pending) return Promise.reject(new Error("another command is in flight"));
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => this.failPending(new Error("command timed out")), timeoutMs);
      this.pending = { op: data[0], resolve, reject, timer };
      this.transport.write(UUID.control, data).catch((e) => this.failPending(e instanceof Error ? e : new Error(String(e))));
    });
  }

  private onResponse(d: Uint8Array): void {
    this.guard(() => {
      const { op, result } = decodeResponse(d);
      const p = this.pending;
      if (!p || p.op !== op) return; // unsolicited or stale response
      clearTimeout(p.timer);
      this.pending = null;
      if (result === Result.OK) p.resolve();
      else p.reject(new CommandError(op, result));
    });
  }

  private failPending(e: Error): void {
    const p = this.pending;
    if (!p) return;
    clearTimeout(p.timer);
    this.pending = null;
    p.reject(e);
  }

  private guard(fn: () => void): void {
    try {
      fn();
    } catch (e) {
      this.events.onProtocolError?.(e);
    }
  }

  private setState(s: ConnectionState): void {
    if (s === this.state) return;
    this.state = s;
    this.events.onConnection?.(s);
  }
}

/** True where the browser exposes Web Bluetooth (not Safari, not any iOS browser engine). */
export function webBluetoothAvailable(): boolean {
  return typeof navigator !== "undefined" && "bluetooth" in navigator;
}

/**
 * Web Bluetooth transport (Chrome/Edge on Android, Windows, macOS, ChromeOS, Linux).
 * `connect()` must be called from a user gesture: the browser shows its own
 * device chooser.
 */
export class WebBluetoothTransport implements Transport {
  // Typed loosely on purpose: the Web Bluetooth types are not in lib.dom.
  private device: any = null;
  private service: any = null;
  private chars = new Map<string, any>();
  private disconnectHandler: () => void = () => {};

  async connect(): Promise<void> {
    const bt = (navigator as any).bluetooth;
    if (!bt) throw new Error("Web Bluetooth is not available in this browser");
    this.device ??= await bt.requestDevice({
      filters: [{ services: [UUID.service] }],
      optionalServices: ["battery_service", "device_information"],
    });
    this.device.addEventListener("gattserverdisconnected", () => {
      this.chars.clear();
      this.disconnectHandler();
    });
    const server = await this.device.gatt.connect();
    this.service = await server.getPrimaryService(UUID.service);
  }
  async disconnect(): Promise<void> {
    this.device?.gatt?.disconnect();
  }
  onDisconnect(handler: () => void): void {
    this.disconnectHandler = handler;
  }
  private async char(id: string): Promise<any> {
    let c = this.chars.get(id);
    if (!c) {
      c = await this.service.getCharacteristic(id);
      this.chars.set(id, c);
    }
    return c;
  }
  async read(id: string): Promise<Uint8Array> {
    const v: DataView = await (await this.char(id)).readValue();
    return new Uint8Array(v.buffer, v.byteOffset, v.byteLength);
  }
  async write(id: string, data: Uint8Array): Promise<void> {
    await (await this.char(id)).writeValueWithResponse(data);
  }
  async subscribe(id: string, onData: (data: Uint8Array) => void): Promise<void> {
    const c = await this.char(id);
    c.addEventListener("characteristicvaluechanged", () => {
      const v: DataView = c.value;
      onData(new Uint8Array(v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength)));
    });
    await c.startNotifications();
  }
}

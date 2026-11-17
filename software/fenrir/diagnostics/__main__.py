"""Desktop diagnostic utility.

  python -m fenrir.diagnostics --sim --seconds 8              simulated device
  python -m fenrir.diagnostics --sim --loss 0.05 --csv out.csv
  python -m fenrir.diagnostics --ble --seconds 10             real device (needs `pip install bleak`)
  python -m fenrir.diagnostics --ble --dwell 3                mean/σ of raw counts (calibration dwell)

Prints link quality (rate, loss, faults) and basic force metrics. The BLE path
has not been exercised against hardware yet.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys

from .. import metrics, protocol as P
from ..model import Recording, n_to_kgf, n_to_lbf


def record_sim(seconds: float, loss: float, rate: int, peak: float) -> tuple[Recording, P.CalInfo]:
    from ..simulator import Faults, LoadCellModel, MockDevice, NOMINAL_COUNTS_PER_N, max_pull

    cell = LoadCellModel()
    dev = MockDevice(max_pull(peak, 1.0, 0.25, max(seconds - 3.0, 1.0)), cell, sample_rate=rate,
                     rate_error=0.012, faults=Faults(packet_loss=loss),
                     cal=P.CalInfo(True, 6, 392, 1 / cell.counts_per_n, int(cell.zero_counts), 0, 0))
    assert P.decode_response(dev.write_control(P.cmd_start(P.Format.RAW_FORCE, 4)))[1] == P.Result.OK
    rec = Recording(metadata={"source": "simulator", "simulated": True, "nominal_counts_per_n": NOMINAL_COUNTS_PER_N})
    for n in dev.notifications(seconds):
        rec.add_packet(P.ForcePacket.decode(n))
    return rec, dev.calinfo()


async def record_ble(seconds: float, rate: int, name: str | None) -> tuple[Recording, P.CalInfo]:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        sys.exit("The BLE mode needs the 'bleak' package: pip install bleak")
    dev = await BleakScanner.find_device_by_filter(
        lambda d, ad: P.UUID_SERVICE in (ad.service_uuids or []) and (name is None or d.name == name), timeout=10)
    if dev is None:
        sys.exit("No FENRIR device found (is it awake and not connected elsewhere?)")
    rec = Recording(metadata={"source": "ble", "device": dev.name, "address": dev.address})
    responses: asyncio.Queue[bytes] = asyncio.Queue()
    async with BleakClient(dev) as c:
        ver = await c.read_gatt_char(P.UUID_PROTOCOL)
        if ver[0] != P.PROTOCOL_MAJOR:
            sys.exit(f"Device speaks protocol {ver[0]}.{ver[1]}, this tool speaks {P.PROTOCOL_MAJOR}.x")
        cal = P.CalInfo.decode(bytes(await c.read_gatt_char(P.UUID_CALIBRATION)))
        await c.start_notify(P.UUID_CONTROL, lambda _, d: responses.put_nowait(bytes(d)))
        await c.start_notify(P.UUID_FORCE, lambda _, d: rec.add_packet(P.ForcePacket.decode(bytes(d))))

        async def command(data: bytes) -> None:
            await c.write_gatt_char(P.UUID_CONTROL, data, response=True)
            op, res = P.decode_response(await asyncio.wait_for(responses.get(), 5))
            if res != P.Result.OK:
                sys.exit(f"Command 0x{op:02x} rejected: {res.name}")

        status = P.DeviceStatus.decode(bytes(await c.read_gatt_char(P.UUID_STATUS)))
        if status.sample_rate != rate:
            await command(P.cmd_set_rate(rate))
        await command(P.cmd_start(P.Format.RAW_FORCE, 4))
        await asyncio.sleep(seconds)
        await command(P.cmd_simple(P.Op.STOP))
        rec.metadata["mtu"] = c.mtu_size
    return rec, cal


def report(rec: Recording, cal: P.CalInfo, dwell: bool) -> None:
    st = rec.stats
    rate = rec.measured_rate_hz()
    print(f"calibration : {'valid' if cal.valid else 'NOMINAL (uncalibrated)'}"
          + (f", {cal.n_points} points up to {cal.max_ref_n} N" if cal.valid else ""))
    print(f"packets     : {st.packets} received, {st.lost_packets} lost ({st.packet_loss_ratio:.2%}), "
          f"{st.duplicate_or_reordered} out of order, {st.fault_packets} with fault flags")
    print(f"samples     : {st.samples} received, ~{st.lost_samples_est} lost")
    print(f"sample rate : {rate:.2f} Hz (device clock)" if rate else "sample rate : n/a")
    raws = [s.raw for s in rec.samples if s.raw is not None]
    if dwell and len(raws) > 1:
        print(f"dwell       : mean_counts={statistics.fmean(raws):.1f} std_counts={statistics.pstdev(raws):.1f} "
              f"n_samples={len(raws)}")
        return
    t, f = rec.valid_series()
    if len(f) < 2:
        print("no valid force samples")
        return
    pk, t_pk = metrics.peak_force(t, f)
    print(f"peak force  : {pk:.1f} N = {n_to_kgf(pk):.2f} kgf = {n_to_lbf(pk):.2f} lbf at t={t_pk:.2f} s"
          + ("" if rec.calibrated else "  [UNCALIBRATED]"))
    r = metrics.rfd(t, f)
    if r:
        fmt = lambda v: "n/a" if v is None else f"{v:.0f} N/s"  # noqa: E731
        print(f"RFD         : onset {r.onset_s:.3f} s (20 N); 0-100 ms {fmt(r.rfd_0_100)}; 0-200 ms {fmt(r.rfd_0_200)}; "
              f"20-80 % {fmt(r.rfd_20_80)}; peak ({r.peak_rfd_window_s * 1000:.0f} ms window) {fmt(r.peak_rfd)}")
    quiet = [x for tt, x in zip(t, f) if tt < 0.5]
    if len(quiet) > 5:
        print(f"noise       : {statistics.pstdev(quiet):.3f} N RMS over the first 0.5 s")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fenrir.diagnostics")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sim", action="store_true", help="use the software simulator")
    src.add_argument("--ble", action="store_true", help="connect to a real device")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--dwell", type=float, help="record this many seconds and print raw-count statistics")
    ap.add_argument("--rate", type=int, default=P.RATE_LOW, choices=(P.RATE_LOW, P.RATE_HIGH))
    ap.add_argument("--loss", type=float, default=0.0, help="simulated notification loss probability")
    ap.add_argument("--peak", type=float, default=450.0, help="simulated pull peak, N")
    ap.add_argument("--name", help="BLE device name, e.g. FENRIR-1A2B")
    ap.add_argument("--csv")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    seconds = a.dwell or a.seconds
    if a.sim:
        print("*** SIMULATED DEVICE — not a measurement ***")
        rec, cal = record_sim(seconds, a.loss, a.rate, 0.0 if a.dwell else a.peak)
    else:
        rec, cal = asyncio.run(record_ble(seconds, a.rate, a.name))
    report(rec, cal, bool(a.dwell))
    if a.csv:
        open(a.csv, "w", newline="").write(rec.to_csv())
    if a.json:
        open(a.json, "w").write(rec.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

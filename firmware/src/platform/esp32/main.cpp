/*
 * FENRIR — ESP32 (Arduino core 3.x + NimBLE-Arduino 2.x) platform layer.
 *
 * Everything that decides a measurement lives in the portable core
 * (src/core, host-tested). This file only wires it to SPI (ADS1220), I2C
 * (MAX17048 fuel gauge), flash and BLE.
 *
 * Target: the FENRIR PCB (ESP32-C6-MINI-1 + ADS1220, decisions D-023 to D-025).
 * Pin numbers follow hardware/pcb-design.md and are provisional until the
 * schematic exists.
 *
 * STATUS: not yet executed on hardware. Do not treat as validated.
 */
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <SPI.h>
#include <Wire.h>
#include <esp_sleep.h>

extern "C" {
#include "fenrir/ads1220.h"
#include "fenrir/measure.h"
#include "fenrir/protocol.h"
}

#ifndef FENRIR_FW_VERSION
#define FENRIR_FW_VERSION "0.0.0"
#endif
#ifndef FENRIR_HW_REV
#define FENRIR_HW_REV "unknown"
#endif

namespace {

constexpr uint32_t kI2cHz = 400000;
constexpr uint32_t kSpiHz = 2000000;         // well inside the ADS1220 SCLK limit
constexpr int kPinSclk = 21, kPinMosi = 22, kPinMiso = 23, kPinCs = 20, kPinDrdy = 2;
constexpr int kPinSda = 6, kPinScl = 7;
constexpr uint32_t kAdcTimeoutMs = 100;      // no conversion for this long -> ADC_TIMEOUT
constexpr int32_t kOverloadCn = 220000;      // 2200 N: 110 % of the nominal range
constexpr int32_t kMaxSlewCn = 100000;       // 1000 N between consecutive samples
constexpr uint16_t kStuckSamples = 40;       // identical codes (0.44 s at 90 SPS, 0.11 s at 350 SPS)
constexpr uint16_t kTareSamples = 40;
constexpr int32_t kTareMaxSpanCounts = 2200; // ~2 N at the nominal scale
constexpr uint32_t kIdleSleepMs = 10UL * 60UL * 1000UL;
constexpr uint8_t kLowBatteryPct = 10;
constexpr uint8_t kMax17048Addr = 0x36;

Preferences prefs;
fenrir_config_t cfg;
fenrir_filter_t filter;
fenrir_guard_t guard;
fenrir_tare_t tare;
ads1220_bus_t adcBus;

NimBLECharacteristic *chForce, *chControl, *chStatus, *chCal, *chBattery;
bool connected = false;
uint16_t attMtu = 23;

uint8_t state = FENRIR_STATE_BOOT;
uint8_t lastError = 0;
uint16_t stickyFlags = 0;  // flags that persist until the next packet goes out
uint16_t configFlags = 0;  // CONFIG_CRC / ADC_FAULT, persist until reboot
uint8_t streamFormat = FENRIR_FMT_RAW_FORCE;
uint8_t streamBatch = 4;
uint16_t seq = 0;

fenrir_sample_t batch[FENRIR_MAX_SAMPLES_PER_PACKET];
uint8_t batchFill = 0;
uint32_t batchT0 = 0;
uint32_t lastSampleUs = 0, lastSampleMs = 0;
uint32_t periodUsQ8 = 12500u << 8; // running estimate of the real sample period
uint32_t lastActivityMs = 0, lastStatusMs = 0;
uint8_t batteryPct = FENRIR_BATTERY_UNKNOWN;
uint16_t batteryMv = 0;

// Control-point writes arrive on the BLE task; hand them to loop() so that all
// bus and state changes happen on one thread.
portMUX_TYPE cmdMux = portMUX_INITIALIZER_UNLOCKED;
uint8_t pendingCmd[20];
size_t pendingLen = 0;

// ---- SPI HAL for the ADS1220 driver ----------------------------------------
// SPI mode 1 (CPOL 0, CPHA 1). CS is held low for one whole command or read.
bool spiTransfer(void *, const uint8_t *tx, uint8_t *rx, size_t len) {
  SPI.beginTransaction(SPISettings(kSpiHz, MSBFIRST, SPI_MODE1));
  digitalWrite(kPinCs, LOW);
  delayMicroseconds(1); // td(CSSC) >= 50 ns
  for (size_t i = 0; i < len; i++) {
    uint8_t v = SPI.transfer(tx[i]);
    if (rx) rx[i] = v;
  }
  delayMicroseconds(1); // td(SCCS) >= 25 ns
  digitalWrite(kPinCs, HIGH);
  SPI.endTransaction();
  return true; // SPI has no acknowledge; the driver verifies by register read-back
}
bool spiDataReady(void *) { return digitalRead(kPinDrdy) == LOW; }
void spiDelayUs(void *, uint32_t us) { delayMicroseconds(us); }

// ---- Battery (MAX17048 fuel gauge) -----------------------------------------
void readBattery() {
#if FENRIR_HAS_MAX17048
  auto rd16 = [](uint8_t reg, uint16_t &out) {
    Wire.beginTransmission(kMax17048Addr);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(kMax17048Addr, (uint8_t)2) != 2) return false;
    out = (uint16_t)(Wire.read() << 8);
    out |= (uint16_t)Wire.read();
    return true;
  };
  uint16_t vcell, soc;
  if (rd16(0x02, vcell) && rd16(0x04, soc)) {
    batteryMv = (uint16_t)(((uint32_t)vcell * 78125UL) / 1000000UL); // 78.125 uV/LSB
    uint8_t pct = (uint8_t)(soc >> 8);                                // 1 %/256 LSB
    batteryPct = pct > 100 ? 100 : pct;
  } else {
    batteryPct = FENRIR_BATTERY_UNKNOWN; // never report a guessed level
    batteryMv = 0;
  }
#endif
}

// ---- Persistent configuration ----------------------------------------------
void loadConfig() {
  uint8_t blob[FENRIR_CONFIG_BLOB_LEN];
  size_t n = prefs.getBytes("cfg", blob, sizeof blob);
  if (n == 0) {
    fenrir_config_defaults(&cfg); // first boot: nominal scale, flagged uncalibrated
  } else if (!fenrir_config_deserialize(&cfg, blob, n)) {
    configFlags |= FENRIR_ST_CONFIG_CRC; // corrupt: defaults loaded, host is told
  }
}
bool saveConfig() {
  uint8_t blob[FENRIR_CONFIG_BLOB_LEN];
  size_t n = fenrir_config_serialize(&cfg, blob, sizeof blob);
  return n && prefs.putBytes("cfg", blob, n) == n;
}

// ---- GATT values ------------------------------------------------------------
uint16_t baseFlags() {
  uint16_t f = configFlags;
  if (state == FENRIR_STATE_STREAMING) f |= FENRIR_ST_STREAMING;
  if (cfg.cal.valid) f |= FENRIR_ST_CAL_VALID;
  if (cfg.cal.tare_counts != 0) f |= FENRIR_ST_TARED;
  if (cfg.filter_type != FENRIR_FILTER_NONE) f |= FENRIR_ST_FILTERED;
  if (batteryPct != FENRIR_BATTERY_UNKNOWN && batteryPct <= kLowBatteryPct) f |= FENRIR_ST_LOW_BATTERY;
  return f;
}

void publishStatus(bool notify) {
  fenrir_status_t s = {};
  s.state = state;
  s.last_error = lastError;
  s.flags = (uint16_t)(baseFlags() | stickyFlags);
  s.battery_pct = batteryPct;
  s.battery_mv = batteryMv;
  s.sample_rate = cfg.sample_rate;
  s.filter_type = cfg.filter_type;
  s.filter_param = cfg.filter_param;
  s.uptime_s = millis() / 1000;
  uint8_t buf[FENRIR_STATUS_LEN];
  chStatus->setValue(buf, fenrir_status_encode(buf, sizeof buf, &s));
  if (notify && connected) chStatus->notify();
  if (batteryPct != FENRIR_BATTERY_UNKNOWN) {
    chBattery->setValue(&batteryPct, 1);
    if (notify && connected) chBattery->notify();
  }
}

void publishCal() {
  fenrir_calinfo_t c = {};
  c.valid = cfg.cal.valid;
  c.n_points = cfg.cal.n_points;
  c.max_ref_n = cfg.cal.max_ref_n;
  c.scale_n_per_count = cfg.cal.scale_n_per_count;
  c.zero_counts = cfg.cal.zero_counts;
  c.tare_counts = cfg.cal.tare_counts;
  c.unix_time = cfg.cal.unix_time;
  uint8_t buf[FENRIR_CALINFO_LEN];
  chCal->setValue(buf, fenrir_calinfo_encode(buf, sizeof buf, &c));
}

void respond(uint8_t op, uint8_t result) {
  uint8_t buf[2];
  if (result != FENRIR_RES_OK) lastError = result;
  chControl->setValue(buf, fenrir_response_encode(buf, sizeof buf, op, result));
  if (connected) chControl->notify();
}

void flushBatch() {
  if (batchFill == 0) return;
  fenrir_force_header_t h = {};
  h.seq = seq++;
  h.t0_us = batchT0;
  h.dt_us = (uint16_t)(periodUsQ8 >> 8);
  h.status = (uint16_t)(baseFlags() | stickyFlags);
  h.format = streamFormat;
  h.count = batchFill;
  uint8_t buf[FENRIR_FORCE_HEADER_LEN + 6 * FENRIR_MAX_SAMPLES_PER_PACKET];
  size_t n = fenrir_force_encode(buf, sizeof buf, &h, batch);
  if (n && connected) {
    chForce->setValue(buf, n);
    // A failed notify (stack buffers full) is reported in the next packet;
    // the sequence number still advances so the client can count the gap.
    stickyFlags = chForce->notify() ? 0 : FENRIR_ST_SAMPLE_DROPPED;
  }
  batchFill = 0;
}

void stopStreaming() {
  flushBatch();
  state = (configFlags & FENRIR_ST_ADC_FAULT) ? FENRIR_STATE_ERROR : FENRIR_STATE_IDLE;
}

// ---- Commands ---------------------------------------------------------------
void handleCommand(const uint8_t *data, size_t len) {
  fenrir_command_t cmd;
  uint8_t res = fenrir_command_parse(data, len, &cmd);
  uint8_t op = len ? data[0] : 0;
  lastActivityMs = millis();
  if (res != FENRIR_RES_OK) return respond(op, res);

  const bool adcOk = !(configFlags & FENRIR_ST_ADC_FAULT);
  switch (cmd.op) {
    case FENRIR_OP_START: {
      if (!adcOk) return respond(op, FENRIR_RES_HW_ERROR);
      uint8_t cap = fenrir_force_capacity(attMtu, cmd.u.start.format);
      if (cap == 0) return respond(op, FENRIR_RES_BAD_STATE);
      streamFormat = cmd.u.start.format;
      streamBatch = cmd.u.start.batch < cap ? cmd.u.start.batch : cap; // clamp to the MTU
      batchFill = 0;
      seq = 0;
      stickyFlags = 0;
      fenrir_filter_init(&filter, cfg.filter_type, cfg.filter_param);
      fenrir_guard_init(&guard, kOverloadCn, kMaxSlewCn, kStuckSamples);
      state = FENRIR_STATE_STREAMING;
      break;
    }
    case FENRIR_OP_STOP:
      stopStreaming();
      break;
    case FENRIR_OP_TARE:
      if (!adcOk) return respond(op, FENRIR_RES_HW_ERROR);
      if (tare.active) return respond(op, FENRIR_RES_BAD_STATE);
      fenrir_tare_begin(&tare, kTareSamples);
      return; // response is sent when the averaging window completes
    case FENRIR_OP_CLEAR_TARE:
      cfg.cal.tare_counts = 0;
      publishCal();
      break;
    case FENRIR_OP_SET_RATE:
      if (state == FENRIR_STATE_STREAMING) return respond(op, FENRIR_RES_BAD_STATE);
      if (!adcOk || ads1220_set_rate(&adcBus, cmd.u.rate.sps) != ADS1220_OK)
        return respond(op, FENRIR_RES_HW_ERROR);
      cfg.sample_rate = cmd.u.rate.sps;
      periodUsQ8 = (1000000UL / cfg.sample_rate) << 8;
      if (!saveConfig()) return respond(op, FENRIR_RES_HW_ERROR);
      break;
    case FENRIR_OP_SET_FILTER:
      cfg.filter_type = cmd.u.filter.type;
      cfg.filter_param = cmd.u.filter.param;
      fenrir_filter_init(&filter, cfg.filter_type, cfg.filter_param);
      if (!saveConfig()) return respond(op, FENRIR_RES_HW_ERROR);
      break;
    case FENRIR_OP_CAL_WRITE:
      if (state == FENRIR_STATE_STREAMING) return respond(op, FENRIR_RES_BAD_STATE);
      cfg.cal.scale_n_per_count = cmd.u.cal.scale_n_per_count;
      cfg.cal.zero_counts = cmd.u.cal.zero_counts;
      cfg.cal.tare_counts = 0;
      cfg.cal.max_ref_n = cmd.u.cal.max_ref_n;
      cfg.cal.n_points = cmd.u.cal.n_points;
      cfg.cal.unix_time = cmd.u.cal.unix_time;
      cfg.cal.valid = 1;
      if (!saveConfig()) return respond(op, FENRIR_RES_HW_ERROR);
      publishCal();
      break;
    case FENRIR_OP_CAL_CLEAR:
      if (state == FENRIR_STATE_STREAMING) return respond(op, FENRIR_RES_BAD_STATE);
      fenrir_cal_set_nominal(&cfg.cal);
      if (!saveConfig()) return respond(op, FENRIR_RES_HW_ERROR);
      publishCal();
      break;
    case FENRIR_OP_GET_STATUS:
      break;
    case FENRIR_OP_SLEEP:
      respond(op, FENRIR_RES_OK);
      delay(100);
      ads1220_power_down(&adcBus);
      esp_deep_sleep_start(); // wake source (button on GPIO3) not wired in firmware yet
      return;
  }
  respond(op, FENRIR_RES_OK);
  publishStatus(true);
}

// ---- BLE callbacks ------------------------------------------------------------
class ServerCb : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer *, NimBLEConnInfo &info) override {
    connected = true;
    attMtu = info.getMTU();
    lastActivityMs = millis();
  }
  void onDisconnect(NimBLEServer *, NimBLEConnInfo &, int) override {
    connected = false;
    attMtu = 23;
    // Never keep streaming into the void; a reconnecting client must START again.
    if (state == FENRIR_STATE_STREAMING) state = FENRIR_STATE_IDLE;
    batchFill = 0;
    NimBLEDevice::startAdvertising();
  }
  void onMTUChange(uint16_t mtu, NimBLEConnInfo &) override { attMtu = mtu; }
};

class ControlCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic *c, NimBLEConnInfo &) override {
    NimBLEAttValue v = c->getValue();
    portENTER_CRITICAL(&cmdMux);
    pendingLen = v.size() > sizeof pendingCmd ? sizeof pendingCmd : v.size();
    memcpy(pendingCmd, v.data(), pendingLen);
    if (pendingLen == 0) pendingLen = SIZE_MAX; // empty write still needs a BAD_LENGTH reply
    portEXIT_CRITICAL(&cmdMux);
  }
};

void setupBle() {
  uint64_t mac = ESP.getEfuseMac();
  char name[20], serial[13];
  snprintf(serial, sizeof serial, "%012llX", (unsigned long long)(mac & 0xFFFFFFFFFFFFULL));
  snprintf(name, sizeof name, "FENRIR-%s", serial + 8);

  NimBLEDevice::init(name);
  NimBLEDevice::setMTU(247);
  NimBLEServer *server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCb());

  NimBLEService *svc = server->createService(FENRIR_UUID_SERVICE);
  chForce = svc->createCharacteristic(FENRIR_UUID_FORCE, NIMBLE_PROPERTY::NOTIFY);
  chControl = svc->createCharacteristic(FENRIR_UUID_CONTROL, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::NOTIFY);
  chStatus = svc->createCharacteristic(FENRIR_UUID_STATUS, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  chCal = svc->createCharacteristic(FENRIR_UUID_CALIBRATION, NIMBLE_PROPERTY::READ);
  NimBLECharacteristic *chProto = svc->createCharacteristic(FENRIR_UUID_PROTOCOL, NIMBLE_PROPERTY::READ);
  const uint8_t proto[2] = {FENRIR_PROTOCOL_MAJOR, FENRIR_PROTOCOL_MINOR};
  chProto->setValue(proto, 2);
  chControl->setCallbacks(new ControlCb());

  NimBLEService *dis = server->createService("180A");
  dis->createCharacteristic("2A29", NIMBLE_PROPERTY::READ)->setValue("LeBlond");
  dis->createCharacteristic("2A24", NIMBLE_PROPERTY::READ)->setValue("FENRIR");
  dis->createCharacteristic("2A25", NIMBLE_PROPERTY::READ)->setValue(serial);
  dis->createCharacteristic("2A26", NIMBLE_PROPERTY::READ)->setValue(FENRIR_FW_VERSION);
  dis->createCharacteristic("2A27", NIMBLE_PROPERTY::READ)->setValue(FENRIR_HW_REV);

  NimBLEService *bas = server->createService("180F");
  chBattery = bas->createCharacteristic("2A19", NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);

  server->start(); // starts every service created above (NimBLE-Arduino 2.x)

  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(FENRIR_UUID_SERVICE);
  adv->setName(name);
  adv->enableScanResponse(true);
  adv->start();
}

// ---- Acquisition ----------------------------------------------------------------
void onSample(int32_t raw, uint32_t nowUs) {
  if (lastSampleUs != 0) {
    uint32_t d = nowUs - lastSampleUs;
    // Track the ADC's real rate (its RC oscillator is not trimmed to the MCU
    // clock). Ignore gaps: those are missed samples, not a slower clock.
    uint32_t nominal = 1000000UL / cfg.sample_rate;
    if (d > nominal / 2 && d < nominal * 3 / 2) {
      periodUsQ8 += (int32_t)((d << 8) - periodUsQ8) / 64;
    } else if (d >= nominal * 3 / 2) {
      stickyFlags |= FENRIR_ST_SAMPLE_DROPPED;
    }
  }
  lastSampleUs = nowUs;
  lastSampleMs = millis();

  if (tare.active) {
    int32_t mean;
    bool ok;
    if (fenrir_tare_feed(&tare, raw, kTareMaxSpanCounts, &mean, &ok)) {
      if (ok) {
        cfg.cal.tare_counts = mean - cfg.cal.zero_counts; // volatile by design: re-tare each session
        publishCal();
      }
      respond(FENRIR_OP_TARE, ok ? FENRIR_RES_OK : FENRIR_RES_BAD_STATE);
      publishStatus(true);
    }
  }

  if (state != FENRIR_STATE_STREAMING) return;
  int32_t force = fenrir_cal_centinewtons(&cfg.cal, raw);
  uint16_t flags = fenrir_guard_check(&guard, raw, force);
  if (flags & FENRIR_ST_ADC_SATURATED) force = FENRIR_FORCE_INVALID; // clipped input is not a force
  stickyFlags |= flags;
  if (batchFill == 0) batchT0 = nowUs;
  batch[batchFill].raw = raw; // raw is always the untouched ADC code
  batch[batchFill].force_cn = fenrir_filter_apply(&filter, force);
  if (++batchFill >= streamBatch) flushBatch();
}

} // namespace

void setup() {
  Serial.begin(115200);
  prefs.begin("fenrir", false);
  loadConfig();

  Wire.begin(kPinSda, kPinScl);
  Wire.setClock(kI2cHz);
  pinMode(kPinCs, OUTPUT);
  digitalWrite(kPinCs, HIGH);
  pinMode(kPinDrdy, INPUT_PULLUP);
  SPI.begin(kPinSclk, kPinMiso, kPinMosi, kPinCs);
  delay(5); // supplies settle and the ADS1220 power-up reset completes (>= 50 us)
  adcBus = {nullptr, spiTransfer, spiDataReady, spiDelayUs};
  ads1220_result_t r = ads1220_init(&adcBus, cfg.sample_rate);
  if (r != ADS1220_OK) {
    configFlags |= FENRIR_ST_ADC_FAULT;
    lastError = FENRIR_RES_HW_ERROR;
    Serial.printf("ADS1220 init failed: %d\n", (int)r);
  }
  periodUsQ8 = (1000000UL / cfg.sample_rate) << 8;
  fenrir_filter_init(&filter, cfg.filter_type, cfg.filter_param);
  fenrir_guard_init(&guard, kOverloadCn, kMaxSlewCn, kStuckSamples);

  setupBle();
  readBattery();
  state = (configFlags & FENRIR_ST_ADC_FAULT) ? FENRIR_STATE_ERROR : FENRIR_STATE_IDLE;
  publishCal();
  publishStatus(false);
  lastActivityMs = lastSampleMs = millis();
  Serial.printf("FENRIR fw %s hw %s, cal %s\n", FENRIR_FW_VERSION, FENRIR_HW_REV,
                cfg.cal.valid ? "valid" : "NOMINAL (uncalibrated)");
}

void loop() {
  uint8_t cmd[sizeof pendingCmd];
  size_t len = 0;
  portENTER_CRITICAL(&cmdMux);
  if (pendingLen) {
    len = pendingLen;
    if (len != SIZE_MAX) memcpy(cmd, pendingCmd, len);
    pendingLen = 0;
  }
  portEXIT_CRITICAL(&cmdMux);
  if (len) handleCommand(cmd, len == SIZE_MAX ? 0 : len);

  uint32_t nowMs = millis();
  if (!(configFlags & FENRIR_ST_ADC_FAULT)) {
    int32_t raw;
    ads1220_result_t r = ads1220_read(&adcBus, &raw);
    if (r == ADS1220_OK) {
      onSample(raw, micros());
    } else if (r == ADS1220_ERR_BUS || nowMs - lastSampleMs > kAdcTimeoutMs) {
      stickyFlags |= FENRIR_ST_ADC_TIMEOUT;
      if (tare.active) {
        tare.active = false;
        respond(FENRIR_OP_TARE, FENRIR_RES_HW_ERROR);
      }
      if (nowMs - lastSampleMs > 1000) { // try to recover a hung ADC once a second
        lastSampleMs = nowMs;
        if (ads1220_init(&adcBus, cfg.sample_rate) != ADS1220_OK) lastError = FENRIR_RES_HW_ERROR;
        publishStatus(true);
      }
    }
  }

  if (nowMs - lastStatusMs >= 5000) {
    lastStatusMs = nowMs;
    readBattery();
    publishStatus(true);
  }
  if (connected || state == FENRIR_STATE_STREAMING) lastActivityMs = nowMs;
  if (nowMs - lastActivityMs > kIdleSleepMs) {
    ads1220_power_down(&adcBus);
    esp_deep_sleep_start();
  }
  delayMicroseconds(300); // poll DRDY at ~2 kHz (350 SPS needs < 2.9 ms); yields to the BLE stack
}

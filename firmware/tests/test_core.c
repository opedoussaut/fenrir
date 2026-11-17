/*
 * Host tests for the portable firmware core. No framework: CHECK() counts
 * failures and main() returns non-zero if any failed.
 *   make -C firmware/tests            (needs gcc; see README for the Docker form)
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "fenrir/ads1220.h"
#include "fenrir/measure.h"
#include "fenrir/nau7802.h"
#include "fenrir/protocol.h"

static int failures, checks;
#define CHECK(c) do { checks++; if (!(c)) { failures++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

/* ---- protocol ------------------------------------------------------------ */
static void test_force_roundtrip(void)
{
    fenrir_sample_t in[4] = { { 0, 0 }, { 123456, 11500 }, { -8388608, FENRIR_FORCE_INVALID }, { 8388607, -200000 } };
    fenrir_force_header_t h = { 0xFFFE, 0xFFFFFF00u, 12500, FENRIR_ST_STREAMING | FENRIR_ST_CAL_VALID, FENRIR_FMT_RAW_FORCE, 4 };
    uint8_t buf[64];
    size_t n = fenrir_force_encode(buf, sizeof buf, &h, in);
    CHECK(n == 12 + 4 * 6);
    fenrir_force_header_t g;
    fenrir_sample_t out[FENRIR_MAX_SAMPLES_PER_PACKET];
    CHECK(fenrir_force_decode(buf, n, &g, out));
    CHECK(g.seq == h.seq && g.t0_us == h.t0_us && g.dt_us == h.dt_us && g.status == h.status && g.count == 4);
    for (int i = 0; i < 4; i++) CHECK(out[i].raw == in[i].raw && out[i].force_cn == in[i].force_cn);

    h.format = FENRIR_FMT_FORCE;
    n = fenrir_force_encode(buf, sizeof buf, &h, in);
    CHECK(n == 12 + 4 * 3);
    CHECK(fenrir_force_decode(buf, n, &g, out));
    CHECK(out[1].force_cn == 11500 && out[2].force_cn == FENRIR_FORCE_INVALID);

    /* a real force can never alias the invalid sentinel */
    fenrir_sample_t big = { 0, -9000000 };
    h.count = 1;
    n = fenrir_force_encode(buf, sizeof buf, &h, &big);
    CHECK(fenrir_force_decode(buf, n, &g, out) && out[0].force_cn == FENRIR_I24_MIN);

    CHECK(fenrir_force_encode(buf, 10, &h, in) == 0);     /* buffer too small */
    CHECK(!fenrir_force_decode(buf, n - 1, &g, out));      /* truncated */
    h.format = 9;
    CHECK(fenrir_force_encode(buf, sizeof buf, &h, in) == 0);
}

static void test_capacity(void)
{
    CHECK(fenrir_force_capacity(23, FENRIR_FMT_RAW_FORCE) == 1);  /* default MTU */
    CHECK(fenrir_force_capacity(23, FENRIR_FMT_FORCE) == 2);
    CHECK(fenrir_force_capacity(247, FENRIR_FMT_RAW_FORCE) == 38);
    CHECK(fenrir_force_capacity(517, FENRIR_FMT_FORCE) == FENRIR_MAX_SAMPLES_PER_PACKET);
    CHECK(fenrir_force_capacity(17, FENRIR_FMT_FORCE) == 0);
}

static void test_commands(void)
{
    fenrir_command_t c;
    uint8_t start[] = { FENRIR_OP_START, FENRIR_FMT_RAW_FORCE, 4 };
    CHECK(fenrir_command_parse(start, 3, &c) == FENRIR_RES_OK && c.u.start.batch == 4);
    CHECK(fenrir_command_parse(start, 2, &c) == FENRIR_RES_BAD_LENGTH);
    start[2] = 0;
    CHECK(fenrir_command_parse(start, 3, &c) == FENRIR_RES_BAD_PARAM);
    uint8_t rate[] = { FENRIR_OP_SET_RATE, 0x5E, 0x01 }; /* 350 */
    CHECK(fenrir_command_parse(rate, 3, &c) == FENRIR_RES_OK && c.u.rate.sps == 350);
    rate[1] = 90; rate[2] = 0;
    CHECK(fenrir_command_parse(rate, 3, &c) == FENRIR_RES_OK && c.u.rate.sps == 90);
    rate[1] = 80; /* protocol 1.0 value: mapped to the real rate */
    CHECK(fenrir_command_parse(rate, 3, &c) == FENRIR_RES_OK && c.u.rate.sps == 90);
    rate[1] = 0x40; rate[2] = 0x01; /* 320 */
    CHECK(fenrir_command_parse(rate, 3, &c) == FENRIR_RES_OK && c.u.rate.sps == 350);
    rate[1] = 100; rate[2] = 0;
    CHECK(fenrir_command_parse(rate, 3, &c) == FENRIR_RES_BAD_PARAM);
    uint8_t unknown[] = { 0x77 };
    CHECK(fenrir_command_parse(unknown, 1, &c) == FENRIR_RES_UNKNOWN_OP);
    CHECK(fenrir_command_parse(unknown, 0, &c) == FENRIR_RES_BAD_LENGTH);
    uint8_t tare[] = { FENRIR_OP_TARE, 1 };
    CHECK(fenrir_command_parse(tare, 1, &c) == FENRIR_RES_OK);
    CHECK(fenrir_command_parse(tare, 2, &c) == FENRIR_RES_BAD_LENGTH);

    uint8_t cal[16] = { FENRIR_OP_CAL_WRITE };
    float s = 0.00093f;
    memcpy(cal + 1, &s, 4);
    cal[5] = 0x10; cal[6] = 0x27; /* zero = 10000 */
    cal[9] = 0xF4; cal[10] = 0x01; /* max_ref = 500 N */
    cal[11] = 5;
    CHECK(fenrir_command_parse(cal, 16, &c) == FENRIR_RES_OK);
    CHECK(c.u.cal.zero_counts == 10000 && c.u.cal.max_ref_n == 500 && c.u.cal.n_points == 5);
    float nan = NAN;
    memcpy(cal + 1, &nan, 4);
    CHECK(fenrir_command_parse(cal, 16, &c) == FENRIR_RES_BAD_PARAM);
    s = 0.0f;
    memcpy(cal + 1, &s, 4);
    CHECK(fenrir_command_parse(cal, 16, &c) == FENRIR_RES_BAD_PARAM);
}

/* ---- measurement chain ---------------------------------------------------- */
static void test_calibration(void)
{
    fenrir_cal_t c;
    fenrir_cal_set_nominal(&c);
    CHECK(c.valid == 0);
    /* nominal: 2 mV/V, gain 128 -> full 2000 N is about 2.147e6 counts */
    CHECK(fabsf(fenrir_cal_newtons(&c, 2147484) - 2000.0f) < 0.01f);
    c.scale_n_per_count = 0.001f;
    c.zero_counts = 5000;
    c.tare_counts = 1000;
    CHECK(fenrir_cal_centinewtons(&c, 6000) == 0);
    CHECK(fenrir_cal_centinewtons(&c, 1006000) == 100000); /* 1000 N */
    CHECK(fenrir_cal_centinewtons(&c, -994000) == -100000);
    c.scale_n_per_count = 5.0f; /* force overflow of the wire range */
    CHECK(fenrir_cal_centinewtons(&c, 8000000) == FENRIR_I24_MAX);
    CHECK(fenrir_cal_centinewtons(&c, -8000000) == FENRIR_I24_MIN);
}

static void test_config(void)
{
    fenrir_config_t a, b;
    fenrir_config_defaults(&a);
    a.cal.scale_n_per_count = 0.00091f;
    a.cal.zero_counts = -1234;
    a.cal.tare_counts = 77;
    a.cal.max_ref_n = 400;
    a.cal.n_points = 6;
    a.cal.valid = 1;
    a.cal.unix_time = 1794000000u;
    a.sample_rate = 350;
    a.filter_type = FENRIR_FILTER_IIR;
    a.filter_param = 3;
    uint8_t blob[FENRIR_CONFIG_BLOB_LEN];
    CHECK(fenrir_config_serialize(&a, blob, sizeof blob) == FENRIR_CONFIG_BLOB_LEN);
    CHECK(fenrir_config_deserialize(&b, blob, sizeof blob));
    CHECK(b.cal.scale_n_per_count == a.cal.scale_n_per_count && b.cal.zero_counts == -1234 &&
          b.cal.tare_counts == 77 && b.cal.max_ref_n == 400 && b.cal.valid == 1 &&
          b.cal.unix_time == a.cal.unix_time && b.sample_rate == 350 && b.filter_param == 3);
    /* every single-bit corruption must be rejected and fall back to defaults */
    int rejected = 0;
    for (size_t i = 0; i < sizeof blob; i++) {
        blob[i] ^= 0x04;
        if (!fenrir_config_deserialize(&b, blob, sizeof blob) && b.cal.valid == 0 && b.sample_rate == FENRIR_RATE_LOW) rejected++;
        blob[i] ^= 0x04;
    }
    CHECK(rejected == (int)sizeof blob);
    uint8_t erased[FENRIR_CONFIG_BLOB_LEN];
    memset(erased, 0xFF, sizeof erased);
    CHECK(!fenrir_config_deserialize(&b, erased, sizeof erased));
    CHECK(fenrir_crc16((const uint8_t *)"123456789", 9) == 0x29B1); /* CCITT-FALSE check value */
}

static void test_filter(void)
{
    fenrir_filter_t f;
    fenrir_filter_init(&f, FENRIR_FILTER_NONE, 0);
    CHECK(fenrir_filter_apply(&f, 1234) == 1234);
    fenrir_filter_init(&f, FENRIR_FILTER_MOVING_AVG, 4);
    CHECK(fenrir_filter_apply(&f, 100) == 100);
    CHECK(fenrir_filter_apply(&f, 200) == 150);
    fenrir_filter_apply(&f, 300);
    CHECK(fenrir_filter_apply(&f, 400) == 250);
    CHECK(fenrir_filter_apply(&f, 500) == 350); /* 100 dropped out */
    CHECK(fenrir_filter_apply(&f, FENRIR_FORCE_INVALID) == FENRIR_FORCE_INVALID);
    CHECK(fenrir_filter_apply(&f, 600) == 450); /* invalid did not enter the window */
    fenrir_filter_init(&f, FENRIR_FILTER_IIR, 2);
    CHECK(fenrir_filter_apply(&f, 1000) == 1000); /* primed on first sample */
    int32_t y = 0;
    for (int i = 0; i < 100; i++) y = fenrir_filter_apply(&f, 2000);
    CHECK(y >= 1999 && y <= 2000); /* converges to a step */
    fenrir_filter_init(&f, FENRIR_FILTER_IIR, 2);
    fenrir_filter_apply(&f, -1000);
    for (int i = 0; i < 100; i++) y = fenrir_filter_apply(&f, -2000);
    CHECK(y <= -1999 && y >= -2000);
}

static void test_guard(void)
{
    fenrir_guard_t g;
    fenrir_guard_init(&g, 220000, 50000, 8);
    CHECK(fenrir_guard_check(&g, 1000, 100) == 0);
    CHECK(fenrir_guard_check(&g, 1001, 150) == 0);
    CHECK(fenrir_guard_check(&g, 8388607, 150) & FENRIR_ST_ADC_SATURATED);
    CHECK(fenrir_guard_check(&g, -8388608, 150) & FENRIR_ST_ADC_SATURATED);
    CHECK(fenrir_guard_check(&g, 2000, 230000) & FENRIR_ST_OVERLOAD);
    CHECK(fenrir_guard_check(&g, 2001, -230000) & FENRIR_ST_OVERLOAD);
    fenrir_guard_init(&g, 220000, 50000, 8);
    fenrir_guard_check(&g, 10, 0);
    CHECK(fenrir_guard_check(&g, 11, 60000) & FENRIR_ST_SLEW);
    CHECK(!(fenrir_guard_check(&g, 12, 61000) & FENRIR_ST_SLEW));
    uint16_t fl = 0;
    for (int i = 0; i < 7; i++) fl = fenrir_guard_check(&g, 500, 61000);
    CHECK(!(fl & FENRIR_ST_ADC_STUCK));
    fl = fenrir_guard_check(&g, 500, 61000);
    fl = fenrir_guard_check(&g, 500, 61000);
    CHECK(fl & FENRIR_ST_ADC_STUCK);
    CHECK(!(fenrir_guard_check(&g, 501, 61000) & FENRIR_ST_ADC_STUCK)); /* recovers */
}

static void test_tare(void)
{
    fenrir_tare_t t;
    int32_t mean = 0;
    bool ok = false;
    fenrir_tare_begin(&t, 4);
    CHECK(!fenrir_tare_feed(&t, 100, 50, &mean, &ok));
    fenrir_tare_feed(&t, 104, 50, &mean, &ok);
    fenrir_tare_feed(&t, 96, 50, &mean, &ok);
    CHECK(fenrir_tare_feed(&t, 100, 50, &mean, &ok) && ok && mean == 100);
    CHECK(!fenrir_tare_feed(&t, 100, 50, &mean, &ok)); /* inactive after completion */
    fenrir_tare_begin(&t, 2);
    fenrir_tare_feed(&t, 0, 50, &mean, &ok);
    CHECK(fenrir_tare_feed(&t, 5000, 50, &mean, &ok) && !ok); /* moved during tare */
}

/* ---- NAU7802 against a register-level mock ------------------------------- */
typedef struct {
    uint8_t reg[0x20];
    int32_t next_sample;
    bool data_ready, present, never_powers_up, cal_fails;
    int cal_polls;
    uint32_t slept_ms;
} mock_adc_t;

static bool mock_read(void *ctx, uint8_t r, uint8_t *buf, size_t len)
{
    mock_adc_t *m = ctx;
    if (!m->present) return false;
    for (size_t i = 0; i < len; i++) {
        uint8_t a = (uint8_t)(r + i);
        uint8_t v = m->reg[a & 0x1F];
        if (a == NAU7802_REG_PU_CTRL) {
            if ((v & NAU7802_PU_PUD) && !m->never_powers_up) v |= NAU7802_PU_PUR;
            if (m->data_ready) v |= NAU7802_PU_CR;
        } else if (a == NAU7802_REG_CTRL2 && (v & NAU7802_CTRL2_CALS)) {
            if (++m->cal_polls >= 3) { /* calibration takes a few polls */
                m->reg[a] &= (uint8_t)~NAU7802_CTRL2_CALS;
                if (m->cal_fails) m->reg[a] |= NAU7802_CTRL2_CAL_ERR;
                v = m->reg[a];
                m->cal_polls = 0;
            }
        } else if (a >= NAU7802_REG_ADCO_B2 && a < NAU7802_REG_ADCO_B2 + 3) {
            v = (uint8_t)((uint32_t)m->next_sample >> (8 * (2 - (a - NAU7802_REG_ADCO_B2))));
            if (a == NAU7802_REG_ADCO_B2 + 2) m->data_ready = false;
        }
        buf[i] = v;
    }
    return true;
}
static bool mock_write(void *ctx, uint8_t r, uint8_t v)
{
    mock_adc_t *m = ctx;
    if (!m->present) return false;
    if (r == NAU7802_REG_PU_CTRL && (v & NAU7802_PU_RR)) memset(m->reg, 0, sizeof m->reg);
    m->reg[r & 0x1F] = v;
    return true;
}
static void mock_delay(void *ctx, uint32_t ms) { ((mock_adc_t *)ctx)->slept_ms += ms; }

static void test_nau7802(void)
{
    mock_adc_t m = { .present = true };
    nau7802_bus_t bus = { &m, mock_read, mock_write, mock_delay };
    CHECK(nau7802_init(&bus, 80) == NAU7802_OK);
    CHECK(m.reg[NAU7802_REG_CTRL1] == 0x2F);                 /* LDO 3.0 V (101), gain x128 (111) */
    CHECK((m.reg[NAU7802_REG_CTRL2] & 0x70) == 0x30);        /* CRS = 011 -> 80 SPS */
    CHECK((m.reg[NAU7802_REG_PU_CTRL] & 0x96) == 0x96);      /* AVDDS, CS, PUA, PUD */
    CHECK(m.reg[NAU7802_REG_ADC] == 0x30 && m.reg[NAU7802_REG_POWER] == 0x80);
    CHECK(!(m.reg[NAU7802_REG_CTRL2] & NAU7802_CTRL2_CALS)); /* calibration completed */

    int32_t raw = 0;
    CHECK(nau7802_read(&bus, &raw) == NAU7802_NOT_READY);
    m.next_sample = -123456; m.data_ready = true;
    CHECK(nau7802_read(&bus, &raw) == NAU7802_OK && raw == -123456); /* sign extension */
    m.next_sample = 0x7FFFFF; m.data_ready = true;
    CHECK(nau7802_read(&bus, &raw) == NAU7802_OK && raw == 8388607);
    CHECK(nau7802_read(&bus, &raw) == NAU7802_NOT_READY);

    CHECK(nau7802_set_rate(&bus, 320) == NAU7802_OK && (m.reg[NAU7802_REG_CTRL2] & 0x70) == 0x70);
    CHECK(nau7802_set_rate(&bus, 100) == NAU7802_ERR_PARAM);
    CHECK(nau7802_init(&bus, 10) == NAU7802_ERR_PARAM);

    mock_adc_t absent = { .present = false };
    bus.ctx = &absent;
    CHECK(nau7802_init(&bus, 80) == NAU7802_ERR_BUS);
    CHECK(nau7802_read(&bus, &raw) == NAU7802_ERR_BUS);
    mock_adc_t dead = { .present = true, .never_powers_up = true };
    bus.ctx = &dead;
    CHECK(nau7802_init(&bus, 80) == NAU7802_ERR_POWERUP);
    mock_adc_t badcal = { .present = true, .cal_fails = true };
    bus.ctx = &badcal;
    CHECK(nau7802_init(&bus, 80) == NAU7802_ERR_CAL);
}

/* ---- ADS1220 (SPI) ------------------------------------------------------- */
typedef struct {
    bool present;      /* false: MISO floats high, nothing is written */
    bool fail;         /* transfer reports an error */
    bool stuck_reg;    /* a register ignores writes (wiring fault) */
    uint8_t reg[4];
    bool converting, powered_down, drdy;
    int32_t next_sample;
    int resets, starts;
    uint8_t last_cmd;
    uint32_t waited_us;
} mock_spi_t;

static bool spi_transfer(void *ctx, const uint8_t *tx, uint8_t *rx, size_t len)
{
    mock_spi_t *m = ctx;
    if (m->fail) return false;
    if (rx) memset(rx, m->present ? 0x00 : 0xFF, len);
    if (!m->present || len == 0) return true;
    uint8_t c = tx[0];
    if (m->drdy && len == 3 && tx[0] == 0 && tx[1] == 0 && tx[2] == 0) { /* direct data read */
        uint32_t u = (uint32_t)m->next_sample;
        if (rx) { rx[0] = (uint8_t)(u >> 16); rx[1] = (uint8_t)(u >> 8); rx[2] = (uint8_t)u; }
        m->drdy = false;
        return true;
    }
    m->last_cmd = c;
    if ((c & 0xFE) == ADS1220_CMD_RESET) { memset(m->reg, 0, sizeof m->reg); m->converting = false; m->resets++; }
    else if ((c & 0xFE) == ADS1220_CMD_START) { m->converting = true; m->powered_down = false; m->starts++; }
    else if ((c & 0xFE) == ADS1220_CMD_POWERDOWN) { m->powered_down = true; }
    else if ((c & 0xF0) == 0x40 || (c & 0xF0) == 0x20) {
        size_t r0 = (size_t)((c >> 2) & 3), n = (size_t)(c & 3) + 1;
        for (size_t i = 0; i < n && 1 + i < len && r0 + i < 4; i++) {
            if ((c & 0xF0) == 0x40) { if (!(m->stuck_reg && r0 + i == 2)) m->reg[r0 + i] = tx[1 + i]; }
            else if (rx) rx[1 + i] = m->reg[r0 + i];
        }
    }
    return true;
}
static bool spi_drdy(void *ctx) { mock_spi_t *m = ctx; return m->present && m->drdy; }
static void spi_delay(void *ctx, uint32_t us) { ((mock_spi_t *)ctx)->waited_us += us; }

static void test_ads1220(void)
{
    mock_spi_t m = { .present = true };
    ads1220_bus_t bus = { &m, spi_transfer, spi_drdy, spi_delay };
    CHECK(ads1220_init(&bus, 90) == ADS1220_OK);
    CHECK(m.resets == 1 && m.waited_us >= 60);         /* RESET then >= 50 us + 32 tCLK */
    CHECK(m.reg[0] == 0x0E);                           /* AIN0/AIN1, gain 128, PGA on */
    CHECK(m.reg[1] == 0x34);                           /* DR 001 turbo = 90 SPS, continuous */
    CHECK(m.reg[2] == 0x40);                           /* external reference REFP0/REFN0 */
    CHECK(m.reg[3] == 0x00);                           /* DRDY pin only, IDACs off */
    CHECK(m.converting && m.starts == 1 && m.last_cmd == ADS1220_CMD_START);

    int32_t raw = 0;
    CHECK(ads1220_read(&bus, &raw) == ADS1220_NOT_READY);
    m.next_sample = -123456; m.drdy = true;
    CHECK(ads1220_read(&bus, &raw) == ADS1220_OK && raw == -123456); /* sign extension */
    m.next_sample = 0x7FFFFF; m.drdy = true;                         /* positive full scale: */
    CHECK(ads1220_read(&bus, &raw) == ADS1220_OK && raw == 8388607); /* returned untouched */
    m.next_sample = -8388608; m.drdy = true;
    CHECK(ads1220_read(&bus, &raw) == ADS1220_OK && raw == -8388608);
    CHECK(ads1220_read(&bus, &raw) == ADS1220_NOT_READY);

    CHECK(ads1220_set_rate(&bus, 350) == ADS1220_OK && m.reg[1] == 0x74 && m.starts == 2);
    CHECK(m.reg[0] == 0x0E && m.reg[2] == 0x40);       /* other registers untouched */
    CHECK(ads1220_set_rate(&bus, 320) == ADS1220_ERR_PARAM && m.reg[1] == 0x74);
    CHECK(ads1220_init(&bus, 80) == ADS1220_ERR_PARAM);
    CHECK(ads1220_rate_supported(90) && ads1220_rate_supported(350) && !ads1220_rate_supported(0));

    CHECK(ads1220_power_down(&bus) == ADS1220_OK && m.powered_down);

    mock_spi_t absent = { .present = false };          /* no device: read-back is all ones */
    bus.ctx = &absent;
    CHECK(ads1220_init(&bus, 90) == ADS1220_ERR_VERIFY);
    CHECK(ads1220_read(&bus, &raw) == ADS1220_NOT_READY);
    mock_spi_t broken = { .present = true, .fail = true };
    bus.ctx = &broken;
    CHECK(ads1220_init(&bus, 90) == ADS1220_ERR_BUS);
    broken.drdy = true;
    CHECK(ads1220_read(&bus, &raw) == ADS1220_ERR_BUS);
    mock_spi_t stuck = { .present = true, .stuck_reg = true };
    bus.ctx = &stuck;
    CHECK(ads1220_init(&bus, 90) == ADS1220_ERR_VERIFY && !stuck.converting);
}

int main(void)
{
    test_force_roundtrip();
    test_capacity();
    test_commands();
    test_calibration();
    test_config();
    test_filter();
    test_guard();
    test_tare();
    test_nau7802();
    test_ads1220();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}

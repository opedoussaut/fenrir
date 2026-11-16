#include "fenrir/measure.h"
#include "fenrir/protocol.h"

#include <math.h>
#include <string.h>

/* ---- Calibration -------------------------------------------------------- */
void fenrir_cal_set_nominal(fenrir_cal_t *c)
{
    memset(c, 0, sizeof *c);
    c->scale_n_per_count = FENRIR_NOMINAL_SCALE_N_PER_COUNT;
}

float fenrir_cal_newtons(const fenrir_cal_t *c, int32_t raw)
{
    int64_t net = (int64_t)raw - c->zero_counts - c->tare_counts;
    return (float)((double)net * (double)c->scale_n_per_count);
}

int32_t fenrir_cal_centinewtons(const fenrir_cal_t *c, int32_t raw)
{
    int64_t net = (int64_t)raw - c->zero_counts - c->tare_counts;
    double cn = (double)net * (double)c->scale_n_per_count * 100.0;
    if (cn != cn) return FENRIR_FORCE_INVALID;
    if (cn > (double)FENRIR_I24_MAX) return FENRIR_I24_MAX;
    if (cn < (double)FENRIR_I24_MIN) return FENRIR_I24_MIN;
    return (int32_t)llround(cn);
}

/* ---- Persistent configuration ------------------------------------------- */
uint16_t fenrir_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc = (uint16_t)(crc ^ ((uint16_t)data[i] << 8));
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x8000) ? (uint16_t)(((uint32_t)crc << 1) ^ 0x1021u) : (uint16_t)((uint32_t)crc << 1);
    }
    return crc;
}

void fenrir_config_defaults(fenrir_config_t *cfg)
{
    fenrir_cal_set_nominal(&cfg->cal);
    cfg->sample_rate = 80;
    cfg->filter_type = FENRIR_FILTER_NONE;
    cfg->filter_param = 0;
}

static void w32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static uint32_t r32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

/* Layout: magic u32 | scale f32 | zero i32 | tare i32 | unix u32 | max_ref u16 |
 * n_points u8 | valid u8 | rate u16 | ftype u8 | fparam u8 | reserved[4] | crc u16 (=32) */
size_t fenrir_config_serialize(const fenrir_config_t *cfg, uint8_t *b, size_t cap)
{
    if (cap < FENRIR_CONFIG_BLOB_LEN) return 0;
    memset(b, 0, FENRIR_CONFIG_BLOB_LEN);
    uint32_t s;
    memcpy(&s, &cfg->cal.scale_n_per_count, 4);
    w32(b, FENRIR_CONFIG_MAGIC);
    w32(b + 4, s);
    w32(b + 8, (uint32_t)cfg->cal.zero_counts);
    w32(b + 12, (uint32_t)cfg->cal.tare_counts);
    w32(b + 16, cfg->cal.unix_time);
    b[20] = (uint8_t)cfg->cal.max_ref_n;
    b[21] = (uint8_t)(cfg->cal.max_ref_n >> 8);
    b[22] = cfg->cal.n_points;
    b[23] = cfg->cal.valid;
    b[24] = (uint8_t)cfg->sample_rate;
    b[25] = (uint8_t)(cfg->sample_rate >> 8);
    b[26] = cfg->filter_type;
    b[27] = cfg->filter_param;
    uint16_t crc = fenrir_crc16(b, 30);
    b[30] = (uint8_t)crc;
    b[31] = (uint8_t)(crc >> 8);
    return FENRIR_CONFIG_BLOB_LEN;
}

bool fenrir_config_deserialize(fenrir_config_t *cfg, const uint8_t *b, size_t len)
{
    fenrir_config_defaults(cfg);
    if (len != FENRIR_CONFIG_BLOB_LEN || r32(b) != FENRIR_CONFIG_MAGIC) return false;
    uint16_t crc = (uint16_t)(b[30] | (b[31] << 8));
    if (crc != fenrir_crc16(b, 30)) return false;
    fenrir_config_t t;
    uint32_t s = r32(b + 4);
    memcpy(&t.cal.scale_n_per_count, &s, 4);
    t.cal.zero_counts = (int32_t)r32(b + 8);
    t.cal.tare_counts = (int32_t)r32(b + 12);
    t.cal.unix_time = r32(b + 16);
    t.cal.max_ref_n = (uint16_t)(b[20] | (b[21] << 8));
    t.cal.n_points = b[22];
    t.cal.valid = b[23];
    t.sample_rate = (uint16_t)(b[24] | (b[25] << 8));
    t.filter_type = b[26];
    t.filter_param = b[27];
    float a = fabsf(t.cal.scale_n_per_count);
    if (!(a == a) || a < 1e-6f || a > 10.0f) return false;
    if (t.sample_rate != 80 && t.sample_rate != 320) return false;
    if (t.filter_type > FENRIR_FILTER_IIR || t.cal.valid > 1) return false;
    *cfg = t;
    return true;
}

/* ---- Filter -------------------------------------------------------------- */
void fenrir_filter_init(fenrir_filter_t *f, uint8_t type, uint8_t param)
{
    memset(f, 0, sizeof *f);
    f->type = type;
    f->param = param;
    if (type == FENRIR_FILTER_MOVING_AVG) {
        if (f->param < 2) f->param = 2;
        if (f->param > FENRIR_FILTER_MAX_TAPS) f->param = FENRIR_FILTER_MAX_TAPS;
    } else if (type == FENRIR_FILTER_IIR) {
        if (f->param < 1) f->param = 1;
        if (f->param > 8) f->param = 8;
    }
}

static int32_t div_round(int64_t a, int64_t b)
{
    return (int32_t)(a >= 0 ? (a + b / 2) / b : -((-a + b / 2) / b));
}

int32_t fenrir_filter_apply(fenrir_filter_t *f, int32_t x)
{
    if (x == FENRIR_FORCE_INVALID) return x; /* never smear an invalid sample */
    switch (f->type) {
    case FENRIR_FILTER_MOVING_AVG:
        if (f->fill == f->param) f->sum -= f->buf[f->idx];
        else f->fill++;
        f->buf[f->idx] = x;
        f->sum += x;
        f->idx = (uint8_t)((f->idx + 1) % f->param);
        return div_round(f->sum, f->fill);
    case FENRIR_FILTER_IIR: /* y += (x - y) / 2^param, state kept in Q8 */
        if (!f->primed) { f->iir_acc = (int64_t)x * 256; f->primed = true; }
        else f->iir_acc += (((int64_t)x * 256) - f->iir_acc) / ((int64_t)1 << f->param);
        return div_round(f->iir_acc, 256);
    default:
        return x;
    }
}

/* ---- Guard --------------------------------------------------------------- */
void fenrir_guard_init(fenrir_guard_t *g, int32_t overload_cn, int32_t max_slew_cn, uint16_t stuck_count)
{
    memset(g, 0, sizeof *g);
    g->overload_cn = overload_cn;
    g->max_slew_cn = max_slew_cn;
    g->stuck_count = stuck_count;
}

uint16_t fenrir_guard_check(fenrir_guard_t *g, int32_t raw, int32_t force_cn)
{
    uint16_t flags = 0;
    /* The NAU7802 clips at the 24-bit rails; treat the last codes as saturated. */
    if (raw >= 8388607 - 15 || raw <= -8388608 + 15) flags |= FENRIR_ST_ADC_SATURATED;
    if (force_cn != FENRIR_FORCE_INVALID) {
        int32_t a = force_cn < 0 ? -force_cn : force_cn;
        if (a > g->overload_cn) flags |= FENRIR_ST_OVERLOAD;
    }
    if (g->has_last) {
        if (raw == g->last_raw) {
            if (g->same_run < UINT16_MAX) g->same_run++;
        } else {
            g->same_run = 0;
        }
        /* A live bridge at gain 128 always shows LSB noise; a frozen code means
         * a dead ADC, an open bridge wire or a stuck bus. */
        if (g->stuck_count && g->same_run >= g->stuck_count) flags |= FENRIR_ST_ADC_STUCK;
        if (force_cn != FENRIR_FORCE_INVALID && g->last_force_cn != FENRIR_FORCE_INVALID) {
            int64_t d = (int64_t)force_cn - g->last_force_cn;
            if (d < 0) d = -d;
            if (d > g->max_slew_cn) flags |= FENRIR_ST_SLEW;
        }
    }
    g->last_raw = raw;
    g->last_force_cn = force_cn;
    g->has_last = true;
    return flags;
}

/* ---- Tare ---------------------------------------------------------------- */
void fenrir_tare_begin(fenrir_tare_t *t, uint16_t n_samples)
{
    memset(t, 0, sizeof *t);
    t->target = n_samples ? n_samples : 1;
    t->active = true;
}

bool fenrir_tare_feed(fenrir_tare_t *t, int32_t raw, int32_t max_span, int32_t *mean, bool *ok)
{
    if (!t->active) return false;
    if (t->n == 0) { t->min = raw; t->max = raw; }
    if (raw < t->min) t->min = raw;
    if (raw > t->max) t->max = raw;
    t->sum += raw;
    t->n++;
    if (t->n < t->target) return false;
    t->active = false;
    *mean = div_round(t->sum, t->n);
    *ok = ((int64_t)t->max - t->min) <= max_span;
    return true;
}

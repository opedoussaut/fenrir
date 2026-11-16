#include "fenrir/protocol.h"

#include <string.h>

static void put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static void put_i24(uint8_t *p, int32_t v)
{
    uint32_t u = (uint32_t)v;
    p[0] = (uint8_t)u; p[1] = (uint8_t)(u >> 8); p[2] = (uint8_t)(u >> 16);
}
static uint16_t get_u16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t get_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static int32_t get_i24(const uint8_t *p)
{
    uint32_t u = (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16);
    if (u & 0x800000u) u |= 0xFF000000u;
    return (int32_t)u;
}
static void put_f32(uint8_t *p, float f) { uint32_t u; memcpy(&u, &f, 4); put_u32(p, u); }
static float get_f32(const uint8_t *p) { uint32_t u = get_u32(p); float f; memcpy(&f, &u, 4); return f; }

static int32_t clamp_i24(int32_t v, int32_t lo)
{
    if (v > FENRIR_I24_MAX) return FENRIR_I24_MAX;
    if (v < lo) return lo;
    return v;
}

size_t fenrir_sample_size(uint8_t format)
{
    if (format == FENRIR_FMT_RAW_FORCE) return 6;
    if (format == FENRIR_FMT_FORCE) return 3;
    return 0;
}

uint8_t fenrir_force_capacity(uint16_t att_mtu, uint8_t format)
{
    size_t ss = fenrir_sample_size(format);
    if (ss == 0 || att_mtu < 3u + FENRIR_FORCE_HEADER_LEN + ss) return 0;
    size_t n = ((size_t)att_mtu - 3u - FENRIR_FORCE_HEADER_LEN) / ss;
    if (n > FENRIR_MAX_SAMPLES_PER_PACKET) n = FENRIR_MAX_SAMPLES_PER_PACKET;
    return (uint8_t)n;
}

size_t fenrir_force_encode(uint8_t *buf, size_t cap, const fenrir_force_header_t *h,
                           const fenrir_sample_t *samples)
{
    size_t ss = fenrir_sample_size(h->format);
    if (ss == 0 || h->count == 0 || h->count > FENRIR_MAX_SAMPLES_PER_PACKET) return 0;
    size_t len = FENRIR_FORCE_HEADER_LEN + ss * h->count;
    if (cap < len) return 0;
    put_u16(buf, h->seq);
    put_u32(buf + 2, h->t0_us);
    put_u16(buf + 6, h->dt_us);
    put_u16(buf + 8, h->status);
    buf[10] = h->format;
    buf[11] = h->count;
    uint8_t *p = buf + FENRIR_FORCE_HEADER_LEN;
    for (uint8_t i = 0; i < h->count; i++) {
        if (h->format == FENRIR_FMT_RAW_FORCE) {
            /* raw is a true 24-bit ADC code: full signed range is legal */
            put_i24(p, clamp_i24(samples[i].raw, -8388608));
            p += 3;
        }
        int32_t f = samples[i].force_cn;
        /* the most negative code is reserved for "invalid" */
        put_i24(p, f == FENRIR_FORCE_INVALID ? FENRIR_FORCE_INVALID : clamp_i24(f, FENRIR_I24_MIN));
        p += 3;
    }
    return len;
}

bool fenrir_force_decode(const uint8_t *buf, size_t len, fenrir_force_header_t *h,
                         fenrir_sample_t *samples)
{
    if (len < FENRIR_FORCE_HEADER_LEN) return false;
    h->seq = get_u16(buf);
    h->t0_us = get_u32(buf + 2);
    h->dt_us = get_u16(buf + 6);
    h->status = get_u16(buf + 8);
    h->format = buf[10];
    h->count = buf[11];
    size_t ss = fenrir_sample_size(h->format);
    if (ss == 0 || h->count == 0 || h->count > FENRIR_MAX_SAMPLES_PER_PACKET) return false;
    if (len != FENRIR_FORCE_HEADER_LEN + ss * h->count) return false;
    const uint8_t *p = buf + FENRIR_FORCE_HEADER_LEN;
    for (uint8_t i = 0; i < h->count; i++) {
        if (h->format == FENRIR_FMT_RAW_FORCE) { samples[i].raw = get_i24(p); p += 3; }
        else samples[i].raw = 0;
        samples[i].force_cn = get_i24(p);
        p += 3;
    }
    return true;
}

uint8_t fenrir_command_parse(const uint8_t *buf, size_t len, fenrir_command_t *cmd)
{
    if (len < 1) return FENRIR_RES_BAD_LENGTH;
    memset(cmd, 0, sizeof *cmd);
    cmd->op = buf[0];
    const uint8_t *p = buf + 1;
    size_t n = len - 1;
    switch (cmd->op) {
    case FENRIR_OP_START:
        if (n != 2) return FENRIR_RES_BAD_LENGTH;
        cmd->u.start.format = p[0];
        cmd->u.start.batch = p[1];
        if (fenrir_sample_size(p[0]) == 0) return FENRIR_RES_BAD_PARAM;
        if (p[1] == 0 || p[1] > FENRIR_MAX_SAMPLES_PER_PACKET) return FENRIR_RES_BAD_PARAM;
        return FENRIR_RES_OK;
    case FENRIR_OP_SET_RATE:
        if (n != 2) return FENRIR_RES_BAD_LENGTH;
        cmd->u.rate.sps = get_u16(p);
        if (cmd->u.rate.sps != 80 && cmd->u.rate.sps != 320) return FENRIR_RES_BAD_PARAM;
        return FENRIR_RES_OK;
    case FENRIR_OP_SET_FILTER:
        if (n != 2) return FENRIR_RES_BAD_LENGTH;
        cmd->u.filter.type = p[0];
        cmd->u.filter.param = p[1];
        if (p[0] > FENRIR_FILTER_IIR) return FENRIR_RES_BAD_PARAM;
        if (p[0] == FENRIR_FILTER_MOVING_AVG && (p[1] < 2 || p[1] > 32)) return FENRIR_RES_BAD_PARAM;
        if (p[0] == FENRIR_FILTER_IIR && (p[1] < 1 || p[1] > 8)) return FENRIR_RES_BAD_PARAM;
        return FENRIR_RES_OK;
    case FENRIR_OP_CAL_WRITE: {
        if (n != 15) return FENRIR_RES_BAD_LENGTH;
        float s = get_f32(p);
        cmd->u.cal.scale_n_per_count = s;
        cmd->u.cal.zero_counts = (int32_t)get_u32(p + 4);
        cmd->u.cal.max_ref_n = get_u16(p + 8);
        cmd->u.cal.n_points = p[10];
        cmd->u.cal.unix_time = get_u32(p + 11);
        /* scale must be finite, non-zero, and of plausible magnitude (N per count) */
        if (!(s == s) || s == 0.0f) return FENRIR_RES_BAD_PARAM;
        float a = s < 0 ? -s : s;
        if (a < 1e-6f || a > 10.0f) return FENRIR_RES_BAD_PARAM;
        if (cmd->u.cal.n_points < 2) return FENRIR_RES_BAD_PARAM;
        return FENRIR_RES_OK;
    }
    case FENRIR_OP_STOP:
    case FENRIR_OP_TARE:
    case FENRIR_OP_CLEAR_TARE:
    case FENRIR_OP_CAL_CLEAR:
    case FENRIR_OP_GET_STATUS:
    case FENRIR_OP_SLEEP:
        return n == 0 ? FENRIR_RES_OK : FENRIR_RES_BAD_LENGTH;
    default:
        return FENRIR_RES_UNKNOWN_OP;
    }
}

size_t fenrir_response_encode(uint8_t *buf, size_t cap, uint8_t op, uint8_t result)
{
    if (cap < 2) return 0;
    buf[0] = op;
    buf[1] = result;
    return 2;
}

size_t fenrir_status_encode(uint8_t *buf, size_t cap, const fenrir_status_t *s)
{
    if (cap < FENRIR_STATUS_LEN) return 0;
    buf[0] = s->state;
    buf[1] = s->last_error;
    put_u16(buf + 2, s->flags);
    buf[4] = s->battery_pct;
    buf[5] = 0;
    put_u16(buf + 6, s->battery_mv);
    put_u16(buf + 8, s->sample_rate);
    buf[10] = s->filter_type;
    buf[11] = s->filter_param;
    put_u32(buf + 12, s->uptime_s);
    return FENRIR_STATUS_LEN;
}

size_t fenrir_calinfo_encode(uint8_t *buf, size_t cap, const fenrir_calinfo_t *c)
{
    if (cap < FENRIR_CALINFO_LEN) return 0;
    buf[0] = c->valid;
    buf[1] = c->n_points;
    put_u16(buf + 2, c->max_ref_n);
    put_f32(buf + 4, c->scale_n_per_count);
    put_u32(buf + 8, (uint32_t)c->zero_counts);
    put_u32(buf + 12, (uint32_t)c->tare_counts);
    put_u32(buf + 16, c->unix_time);
    return FENRIR_CALINFO_LEN;
}

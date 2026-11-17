/*
 * FENRIR GATT protocol v1 — wire format (see protocol/fenrir-gatt-v1.md).
 * Portable C11, no platform dependencies. All multi-byte fields little-endian.
 */
#ifndef FENRIR_PROTOCOL_H
#define FENRIR_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FENRIR_PROTOCOL_MAJOR 1
#define FENRIR_PROTOCOL_MINOR 1

/* Sample rates (protocol 1.1: ADS1220 turbo-mode rates). SET_RATE still accepts the 1.0 values
 * 80 and 320 and maps them to these; Status always reports the real rate. */
#define FENRIR_RATE_LOW  90
#define FENRIR_RATE_HIGH 350

/* 128-bit UUIDs: f3e7XXXX-6b1d-4c8a-9e2f-5a1c0d7e4b90 */
#define FENRIR_UUID_SERVICE     "f3e70001-6b1d-4c8a-9e2f-5a1c0d7e4b90"
#define FENRIR_UUID_FORCE       "f3e70002-6b1d-4c8a-9e2f-5a1c0d7e4b90"
#define FENRIR_UUID_CONTROL     "f3e70003-6b1d-4c8a-9e2f-5a1c0d7e4b90"
#define FENRIR_UUID_STATUS      "f3e70004-6b1d-4c8a-9e2f-5a1c0d7e4b90"
#define FENRIR_UUID_CALIBRATION "f3e70005-6b1d-4c8a-9e2f-5a1c0d7e4b90"
#define FENRIR_UUID_PROTOCOL    "f3e70006-6b1d-4c8a-9e2f-5a1c0d7e4b90"

/* ---- Force packet ------------------------------------------------------ */
#define FENRIR_FORCE_HEADER_LEN 12u
#define FENRIR_FMT_RAW_FORCE 0u /* per sample: i24 raw counts + i24 force (cN) */
#define FENRIR_FMT_FORCE     1u /* per sample: i24 force (cN) */
#define FENRIR_FORCE_INVALID (-8388608) /* i24 sentinel: no valid force value */
#define FENRIR_I24_MAX 8388607
#define FENRIR_I24_MIN (-8388607)
#define FENRIR_MAX_SAMPLES_PER_PACKET 40u

/* Status flags (u16), carried in every force packet and in the status char. */
enum {
    FENRIR_ST_STREAMING      = 1u << 0,
    FENRIR_ST_CAL_VALID      = 1u << 1,
    FENRIR_ST_TARED          = 1u << 2,
    FENRIR_ST_OVERLOAD       = 1u << 3,
    FENRIR_ST_ADC_SATURATED  = 1u << 4,
    FENRIR_ST_ADC_TIMEOUT    = 1u << 5,
    FENRIR_ST_ADC_STUCK      = 1u << 6,
    FENRIR_ST_SAMPLE_DROPPED = 1u << 7,
    FENRIR_ST_LOW_BATTERY    = 1u << 8,
    FENRIR_ST_FILTERED       = 1u << 9,
    FENRIR_ST_SLEW           = 1u << 10,
    FENRIR_ST_CONFIG_CRC     = 1u << 11,
    FENRIR_ST_ADC_FAULT      = 1u << 12
};

typedef struct {
    int32_t raw;      /* ADC counts, untouched (24-bit signed range) */
    int32_t force_cn; /* centinewtons, or FENRIR_FORCE_INVALID */
} fenrir_sample_t;

typedef struct {
    uint16_t seq;    /* increments by 1 per notification, wraps */
    uint32_t t0_us;  /* device time of first sample, microseconds, wraps */
    uint16_t dt_us;  /* sample period (measured), microseconds */
    uint16_t status; /* FENRIR_ST_* */
    uint8_t format;  /* FENRIR_FMT_* */
    uint8_t count;
} fenrir_force_header_t;

size_t fenrir_sample_size(uint8_t format);
/* Max samples fitting one notification for a given ATT MTU (payload = MTU-3). */
uint8_t fenrir_force_capacity(uint16_t att_mtu, uint8_t format);
/* Returns bytes written, 0 on error (bad format, count, or buffer too small). */
size_t fenrir_force_encode(uint8_t *buf, size_t cap, const fenrir_force_header_t *h,
                           const fenrir_sample_t *samples);
/* Returns true on success; samples must hold FENRIR_MAX_SAMPLES_PER_PACKET. */
bool fenrir_force_decode(const uint8_t *buf, size_t len, fenrir_force_header_t *h,
                         fenrir_sample_t *samples);

/* ---- Control point ------------------------------------------------------ */
enum {
    FENRIR_OP_START      = 0x01, /* format u8, batch u8 */
    FENRIR_OP_STOP       = 0x02,
    FENRIR_OP_TARE       = 0x03,
    FENRIR_OP_CLEAR_TARE = 0x04,
    FENRIR_OP_SET_RATE   = 0x05, /* sps u16: 90 or 350 (80/320 mapped) */
    FENRIR_OP_SET_FILTER = 0x06, /* type u8, param u8 */
    FENRIR_OP_CAL_WRITE  = 0x10, /* scale f32, zero i32, max_ref_n u16, n_points u8, unix u32 */
    FENRIR_OP_CAL_CLEAR  = 0x11,
    FENRIR_OP_GET_STATUS = 0x20,
    FENRIR_OP_SLEEP      = 0x30
};

enum {
    FENRIR_RES_OK = 0,
    FENRIR_RES_UNKNOWN_OP = 1,
    FENRIR_RES_BAD_LENGTH = 2,
    FENRIR_RES_BAD_PARAM = 3,
    FENRIR_RES_BAD_STATE = 4,
    FENRIR_RES_HW_ERROR = 5
};

enum { FENRIR_FILTER_NONE = 0, FENRIR_FILTER_MOVING_AVG = 1, FENRIR_FILTER_IIR = 2 };

typedef struct {
    uint8_t op;
    union {
        struct { uint8_t format, batch; } start;
        struct { uint16_t sps; } rate;
        struct { uint8_t type, param; } filter;
        struct {
            float scale_n_per_count;
            int32_t zero_counts;
            uint16_t max_ref_n;
            uint8_t n_points;
            uint32_t unix_time;
        } cal;
    } u;
} fenrir_command_t;

/* Parses and validates a control-point write. Returns a FENRIR_RES_* code. */
uint8_t fenrir_command_parse(const uint8_t *buf, size_t len, fenrir_command_t *cmd);
/* Response notification: [op, result]. Returns 2. */
size_t fenrir_response_encode(uint8_t *buf, size_t cap, uint8_t op, uint8_t result);

/* ---- Status characteristic (16 bytes) ----------------------------------- */
enum { FENRIR_STATE_BOOT = 0, FENRIR_STATE_IDLE = 1, FENRIR_STATE_STREAMING = 2, FENRIR_STATE_ERROR = 3 };
#define FENRIR_STATUS_LEN 16u
#define FENRIR_BATTERY_UNKNOWN 0xFFu

typedef struct {
    uint8_t state;
    uint8_t last_error; /* last FENRIR_RES_* / fault code, 0 = none */
    uint16_t flags;
    uint8_t battery_pct; /* FENRIR_BATTERY_UNKNOWN when not measured */
    uint16_t battery_mv; /* 0 when not measured */
    uint16_t sample_rate;
    uint8_t filter_type;
    uint8_t filter_param;
    uint32_t uptime_s;
} fenrir_status_t;

size_t fenrir_status_encode(uint8_t *buf, size_t cap, const fenrir_status_t *s);

/* ---- Calibration characteristic (20 bytes) ------------------------------ */
#define FENRIR_CALINFO_LEN 20u
typedef struct {
    uint8_t valid;
    uint8_t n_points;
    uint16_t max_ref_n;
    float scale_n_per_count;
    int32_t zero_counts;
    int32_t tare_counts;
    uint32_t unix_time;
} fenrir_calinfo_t;

size_t fenrir_calinfo_encode(uint8_t *buf, size_t cap, const fenrir_calinfo_t *c);

#ifdef __cplusplus
}
#endif
#endif

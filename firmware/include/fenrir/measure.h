/*
 * Measurement chain: calibration, tare, filtering, sample plausibility and
 * persistent configuration. Portable C11; no hardware access.
 *
 * Data integrity rule: raw ADC counts are never modified. Force is derived
 * from raw; filtering only ever applies to the derived force value and is
 * announced with FENRIR_ST_FILTERED.
 */
#ifndef FENRIR_MEASURE_H
#define FENRIR_MEASURE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- Calibration -------------------------------------------------------- */
typedef struct {
    float scale_n_per_count; /* newtons per ADC count */
    int32_t zero_counts;     /* counts at zero load when calibrated */
    int32_t tare_counts;     /* user tare, relative to zero_counts */
    uint16_t max_ref_n;      /* largest reference force used in calibration */
    uint8_t n_points;        /* number of reference points (incl. zero) */
    uint8_t valid;           /* 1 = user/lab calibration stored, 0 = nominal */
    uint32_t unix_time;      /* when calibrated (supplied by the host) */
} fenrir_cal_t;

/*
 * Nominal scale from datasheet values only (2.0 mV/V at 2000 N, gain 128,
 * ratiometric): counts/N = 2e-3 * 128 * 2^23 / 2000. NOT a calibration.
 */
#define FENRIR_NOMINAL_SCALE_N_PER_COUNT (2000.0f / (2.0e-3f * 128.0f * 8388608.0f))

void fenrir_cal_set_nominal(fenrir_cal_t *c);
float fenrir_cal_newtons(const fenrir_cal_t *c, int32_t raw);
/* Force in centinewtons, saturated to the i24 wire range. */
int32_t fenrir_cal_centinewtons(const fenrir_cal_t *c, int32_t raw);

/* ---- Persistent configuration blob -------------------------------------- */
#define FENRIR_CONFIG_MAGIC 0x464E5231u /* "FNR1" */
#define FENRIR_CONFIG_BLOB_LEN 32u

typedef struct {
    fenrir_cal_t cal;
    uint16_t sample_rate;
    uint8_t filter_type;
    uint8_t filter_param;
} fenrir_config_t;

uint16_t fenrir_crc16(const uint8_t *data, size_t len); /* CRC-16/CCITT-FALSE */
void fenrir_config_defaults(fenrir_config_t *cfg);
size_t fenrir_config_serialize(const fenrir_config_t *cfg, uint8_t *blob, size_t cap);
/* False (and cfg = defaults) on bad magic, length, CRC or implausible content. */
bool fenrir_config_deserialize(fenrir_config_t *cfg, const uint8_t *blob, size_t len);

/* ---- Filter (applied to force in cN) ------------------------------------ */
#define FENRIR_FILTER_MAX_TAPS 32
typedef struct {
    uint8_t type;
    uint8_t param;
    int32_t buf[FENRIR_FILTER_MAX_TAPS];
    int64_t sum;
    uint8_t idx, fill;
    int64_t iir_acc; /* Q8 accumulator */
    bool primed;
} fenrir_filter_t;

void fenrir_filter_init(fenrir_filter_t *f, uint8_t type, uint8_t param);
int32_t fenrir_filter_apply(fenrir_filter_t *f, int32_t x);

/* ---- Sample plausibility guard ------------------------------------------ */
typedef struct {
    int32_t overload_cn;  /* |force| above this sets OVERLOAD */
    int32_t max_slew_cn;  /* |delta force| per sample above this sets SLEW */
    uint16_t stuck_count; /* identical consecutive raw codes before STUCK */
    int32_t last_raw;
    int32_t last_force_cn;
    uint16_t same_run;
    bool has_last;
} fenrir_guard_t;

void fenrir_guard_init(fenrir_guard_t *g, int32_t overload_cn, int32_t max_slew_cn,
                       uint16_t stuck_count);
/* Returns FENRIR_ST_* flags raised by this sample (0 = plausible). */
uint16_t fenrir_guard_check(fenrir_guard_t *g, int32_t raw, int32_t force_cn);

/* ---- Tare averaging ------------------------------------------------------ */
typedef struct {
    int64_t sum;
    int32_t min, max;
    uint16_t n, target;
    bool active;
} fenrir_tare_t;

void fenrir_tare_begin(fenrir_tare_t *t, uint16_t n_samples);
/* Feed raw samples; returns true when done. *ok is false if the signal moved
 * more than max_span counts during the window (device was not at rest). */
bool fenrir_tare_feed(fenrir_tare_t *t, int32_t raw, int32_t max_span, int32_t *mean, bool *ok);

#ifdef __cplusplus
}
#endif
#endif

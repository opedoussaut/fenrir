/*
 * Texas Instruments ADS1220 24-bit delta-sigma ADC driver (FENRIR PCB, decision D-024).
 * Bus access goes through a small SPI HAL so the driver runs unchanged on the target and
 * in host tests. Commands, register fields and the start-up sequence follow the TI data
 * sheet SBAS501D (sections 8.5.3, 8.6.2 and 9.1.6).
 *
 * Configuration used by FENRIR:
 *   - AINP = AIN0, AINN = AIN1 (bridge A+ / A-), gain 128, PGA enabled;
 *   - external reference on REFP0/REFN0, wired to the bridge excitation (ratiometric);
 *   - turbo mode, continuous conversion, 90 or 350 SPS;
 *   - dedicated DRDY pin only (DRDYM = 0), IDACs off, burn-out sources off.
 *
 * The driver never offsets or scales the conversion result: the 24-bit code is returned
 * as the device produced it. Offset is absorbed by the calibration zero and the tare.
 */
#ifndef FENRIR_ADS1220_H
#define FENRIR_ADS1220_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Commands (section 8.5.3) */
#define ADS1220_CMD_POWERDOWN 0x02
#define ADS1220_CMD_RESET     0x06
#define ADS1220_CMD_START     0x08
#define ADS1220_CMD_RDATA     0x10
#define ADS1220_CMD_RREG(reg, n) ((uint8_t)(0x20 | (((reg) & 3) << 2) | (((n) - 1) & 3)))
#define ADS1220_CMD_WREG(reg, n) ((uint8_t)(0x40 | (((reg) & 3) << 2) | (((n) - 1) & 3)))

/* Register 0: MUX[7:4] = 0000 (AIN0/AIN1), GAIN[3:1] = 111 (128), PGA_BYPASS = 0 */
#define ADS1220_REG0_AIN0_AIN1_G128 0x0E
/* Register 1: DR[7:5], MODE[4:3] = 10 (turbo), CM[2] = 1 (continuous), TS = 0, BCS = 0 */
#define ADS1220_REG1_TURBO_CONT 0x14
#define ADS1220_DR_TURBO_90  (0x01 << 5)
#define ADS1220_DR_TURBO_350 (0x03 << 5)
/* Register 2: VREF[7:6] = 01 (REFP0/REFN0), 50/60 = 00, PSW = 0, IDAC = 000 */
#define ADS1220_REG2_EXTREF0 0x40
/* Register 3: IDACs not routed, DRDYM = 0 (dedicated DRDY pin only) */
#define ADS1220_REG3_DEFAULT 0x00

typedef struct {
    void *ctx;
    /* Full-duplex transfer of len bytes with CS held low for the whole transfer
     * (SPI mode 1). rx may be NULL. Returns false if the transfer could not be made. */
    bool (*transfer)(void *ctx, const uint8_t *tx, uint8_t *rx, size_t len);
    /* True when the DRDY pin is low (a new conversion is waiting). */
    bool (*data_ready)(void *ctx);
    void (*delay_us)(void *ctx, uint32_t us);
} ads1220_bus_t;

typedef enum {
    ADS1220_OK = 0,
    ADS1220_ERR_BUS,     /* transfer failed */
    ADS1220_ERR_VERIFY,  /* register read-back differs: device absent or bus wiring fault */
    ADS1220_ERR_PARAM,
    ADS1220_NOT_READY    /* no new conversion (not an error) */
} ads1220_result_t;

/* Rates FENRIR uses; anything else is ADS1220_ERR_PARAM. */
bool ads1220_rate_supported(uint16_t sps);
/* Reset, write and verify the configuration above, start continuous conversion. */
ads1220_result_t ads1220_init(const ads1220_bus_t *bus, uint16_t sps);
/* Change rate (90 or 350 SPS), verify, restart conversions. */
ads1220_result_t ads1220_set_rate(const ads1220_bus_t *bus, uint16_t sps);
/* Non-blocking: ADS1220_NOT_READY when DRDY is high. */
ads1220_result_t ads1220_read(const ads1220_bus_t *bus, int32_t *raw);
ads1220_result_t ads1220_power_down(const ads1220_bus_t *bus);

#ifdef __cplusplus
}
#endif
#endif

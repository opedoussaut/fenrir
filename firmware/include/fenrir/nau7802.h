/*
 * Nuvoton NAU7802 24-bit bridge ADC driver. Bus access goes through a small
 * HAL so the driver runs unchanged on the target and in host tests.
 * Register names and values follow the Nuvoton datasheet rev 1.7, section 10/11.
 */
#ifndef FENRIR_NAU7802_H
#define FENRIR_NAU7802_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NAU7802_I2C_ADDR 0x2A

#define NAU7802_REG_PU_CTRL 0x00
#define NAU7802_REG_CTRL1   0x01
#define NAU7802_REG_CTRL2   0x02
#define NAU7802_REG_ADCO_B2 0x12
#define NAU7802_REG_ADC     0x15
#define NAU7802_REG_POWER   0x1C

#define NAU7802_PU_RR    0x01
#define NAU7802_PU_PUD   0x02
#define NAU7802_PU_PUA   0x04
#define NAU7802_PU_PUR   0x08
#define NAU7802_PU_CS    0x10
#define NAU7802_PU_CR    0x20
#define NAU7802_PU_AVDDS 0x80

#define NAU7802_CTRL1_LDO_3V0  (0x05 << 3)
#define NAU7802_CTRL1_GAIN_128 0x07
#define NAU7802_CTRL2_CALS     0x04
#define NAU7802_CTRL2_CAL_ERR  0x08
#define NAU7802_CTRL2_CRS_80   (0x03 << 4)
#define NAU7802_CTRL2_CRS_320  (0x07 << 4)

typedef struct {
    void *ctx;
    bool (*read)(void *ctx, uint8_t reg, uint8_t *buf, size_t len);
    bool (*write)(void *ctx, uint8_t reg, uint8_t value);
    void (*delay_ms)(void *ctx, uint32_t ms);
} nau7802_bus_t;

typedef enum {
    NAU7802_OK = 0,
    NAU7802_ERR_BUS,      /* no ACK / transfer failed */
    NAU7802_ERR_POWERUP,  /* PUR never asserted */
    NAU7802_ERR_CAL,      /* internal offset calibration failed or timed out */
    NAU7802_ERR_PARAM,
    NAU7802_NOT_READY     /* no new conversion (not an error) */
} nau7802_result_t;

/* Reset, power up, 3.0 V LDO excitation, gain 128, requested rate (80 or 320
 * SPS), then internal offset calibration. */
nau7802_result_t nau7802_init(const nau7802_bus_t *bus, uint16_t sps);
nau7802_result_t nau7802_set_rate(const nau7802_bus_t *bus, uint16_t sps);
/* Non-blocking: NAU7802_NOT_READY when no conversion is waiting. */
nau7802_result_t nau7802_read(const nau7802_bus_t *bus, int32_t *raw);
nau7802_result_t nau7802_power_down(const nau7802_bus_t *bus);

#ifdef __cplusplus
}
#endif
#endif

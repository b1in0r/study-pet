// SPDX-FileCopyrightText: 2026 Waveshare
// SPDX-License-Identifier: Apache-2.0
// Modified by StudyPet: C-only SPI driver, checked errors, blocking DMA transfers.
// Register sequence and native pixel layout adapted from Waveshare display_bsp.cpp.
#include <stddef.h>
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_check.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "rlcd_panel.h"

static const char *TAG = "rlcd_panel";
static spi_device_handle_t spi;
static esp_err_t write_bytes(const uint8_t *data, size_t length)
{
    if (!length) return ESP_OK;
    spi_transaction_t transaction = {.length = length * 8, .tx_buffer = data};
    return spi_device_polling_transmit(spi, &transaction);
}
static esp_err_t command(uint8_t cmd, const uint8_t *data, size_t length)
{
    gpio_set_level(GPIO_NUM_40, 0);
    gpio_set_level(GPIO_NUM_5, 0);
    esp_err_t result = write_bytes(&cmd, 1);
    if (result == ESP_OK && length) {
        gpio_set_level(GPIO_NUM_5, 1);
        result = write_bytes(data, length);
    }
    gpio_set_level(GPIO_NUM_40, 1);
    return result;
}
esp_err_t rlcd_panel_init(void)
{
    gpio_config_t gpio_cfg = {.pin_bit_mask = (1ULL << 5) | (1ULL << 40) | (1ULL << 41),
        .mode = GPIO_MODE_OUTPUT, .pull_up_en = GPIO_PULLUP_ENABLE};
    ESP_RETURN_ON_ERROR(gpio_config(&gpio_cfg), TAG, "configure screen pins");
    gpio_set_level(GPIO_NUM_40, 1);
    spi_bus_config_t bus = {.mosi_io_num = 12, .miso_io_num = -1, .sclk_io_num = 11,
        .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = RLCD_FRAME_BYTES};
    ESP_RETURN_ON_ERROR(spi_bus_initialize(SPI3_HOST, &bus, SPI_DMA_CH_AUTO), TAG, "initialize SPI");
    spi_device_interface_config_t device = {.clock_speed_hz = 10000000, .mode = 0,
        .spics_io_num = -1, .queue_size = 1};
    ESP_RETURN_ON_ERROR(spi_bus_add_device(SPI3_HOST, &device, &spi), TAG, "add screen");
    gpio_set_level(GPIO_NUM_41, 1); vTaskDelay(pdMS_TO_TICKS(50));
    gpio_set_level(GPIO_NUM_41, 0); vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(GPIO_NUM_41, 1); vTaskDelay(pdMS_TO_TICKS(50));
    static const struct {uint8_t cmd, length, data[10];} init[] = {
    {0xD6, 2, {0x17, 0x02}},
    {0xD1, 1, {0x01}},
    {0xC0, 2, {0x11, 0x04}},
    {0xC1, 4, {0x69, 0x69, 0x69, 0x69}},
    {0xC2, 4, {0x19, 0x19, 0x19, 0x19}},
    {0xC4, 4, {0x4B, 0x4B, 0x4B, 0x4B}},
    {0xC5, 4, {0x19, 0x19, 0x19, 0x19}},
    {0xD8, 2, {0x80, 0xE9}},
    {0xB2, 1, {0x02}},
    {0xB3, 10, {0xE5, 0xF6, 0x05, 0x46, 0x77, 0x77, 0x77, 0x77, 0x76, 0x45}},
    {0xB4, 8, {0x05, 0x46, 0x77, 0x77, 0x77, 0x77, 0x76, 0x45}},
    {0x62, 3, {0x32, 0x03, 0x1F}},
    {0xB7, 1, {0x13}},
    {0xB0, 1, {0x64}},
    {0x11, 0, {0}},
    {0xC9, 1, {0x00}},
    {0x36, 1, {0x48}},
    {0x3A, 1, {0x11}},
    {0xB9, 1, {0x20}},
    {0xB8, 1, {0x29}},
    {0x21, 0, {0}},
    {0x2A, 2, {0x12, 0x2A}},
    {0x2B, 2, {0x00, 0xC7}},
    {0x35, 1, {0x00}},
    {0xD0, 1, {0xFF}},
    {0x38, 0, {0}},
    {0x29, 0, {0}},
    };
    for (size_t i = 0; i < sizeof(init) / sizeof(init[0]); ++i) {
        ESP_RETURN_ON_ERROR(command(init[i].cmd, init[i].data, init[i].length), TAG, "initialize panel");
        if (init[i].cmd == 0x11) vTaskDelay(pdMS_TO_TICKS(200));
    }
    return ESP_OK;
}
esp_err_t rlcd_panel_show(const uint8_t *frame)
{
    const uint8_t column[] = {0x12, 0x2A}, row[] = {0, 0xC7};
    ESP_RETURN_ON_ERROR(command(0x2A, column, 2), TAG, "set columns");
    ESP_RETURN_ON_ERROR(command(0x2B, row, 2), TAG, "set rows");
    return command(0x2C, frame, RLCD_FRAME_BYTES);
}

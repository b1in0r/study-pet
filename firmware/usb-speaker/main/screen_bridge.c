// SPDX-License-Identifier: MIT
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_rom_crc.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tusb.h"
#include "rlcd_panel.h"
#include "screen_bridge.h"
#include "screen_waiting.h"

static const char *TAG = "screen_bridge";

typedef struct {
    uint8_t header[16];
    size_t header_len;
    uint8_t *incoming;
    size_t payload_len;
    uint8_t *pages[2];
    bool valid[2];
    unsigned active_page;
    TickType_t last_byte;
} screen_state_t;

static void acknowledge(const char *message)
{
    tud_cdc_write_str(message);
    tud_cdc_write_flush();
}

static uint32_t read_u32(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 |
           (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static void receive_byte(screen_state_t *state, uint8_t byte)
{
    if (state->header_len < 16) {
        state->header[state->header_len++] = byte;
        if (state->header_len <= 4 && memcmp(state->header, "SPET", state->header_len)) {
            state->header_len = byte == 'S' ? 1 : 0;
            if (state->header_len) state->header[0] = 'S';
        }
        if (state->header_len != 16) return;
        if (state->header[4] != 1 || state->header[5] != 1 ||
            state->header[6] > 1 || state->header[7] != 0 ||
            read_u32(state->header + 8) != RLCD_FRAME_BYTES) {
            acknowledge("ERR HEADER\n");
            state->header_len = 0;
        }
        state->payload_len = 0;
        return;
    }
    state->incoming[state->payload_len++] = byte;
    if (state->payload_len != RLCD_FRAME_BYTES) return;
    unsigned page = state->header[6];
    uint32_t crc = esp_rom_crc32_le(0, state->incoming, RLCD_FRAME_BYTES);
    if (crc == read_u32(state->header + 12)) {
        memcpy(state->pages[page], state->incoming, RLCD_FRAME_BYTES);
        state->valid[page] = true;
        esp_err_t result = ESP_OK;
        if (page == state->active_page) result = rlcd_panel_show(state->pages[page]);
        if (result == ESP_OK) acknowledge(page == 0 ? "OK 0\n" : "OK 1\n");
        else acknowledge("ERR SCREEN\n");
    } else {
        acknowledge("ERR CRC\n");
    }
    state->header_len = state->payload_len = 0;
}

static void screen_task(void *arg)
{
    (void)arg;
    screen_state_t state = {0};
    uint8_t *memory = heap_caps_malloc(RLCD_FRAME_BYTES * 3, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!memory) {
        ESP_LOGE(TAG, "No framebuffer memory; speaker remains available");
        vTaskDelete(NULL);
        return;
    }
    state.incoming = memory;
    state.pages[0] = memory + RLCD_FRAME_BYTES;
    state.pages[1] = memory + RLCD_FRAME_BYTES * 2;
    esp_err_t result = rlcd_panel_init();
    if (result != ESP_OK) {
        ESP_LOGE(TAG, "Screen init failed (%s); speaker remains available", esp_err_to_name(result));
        free(memory);
        vTaskDelete(NULL);
        return;
    }
    memcpy(state.pages[0], screen_waiting, RLCD_FRAME_BYTES);
    rlcd_panel_show(state.pages[0]);
    gpio_config_t key_cfg = {
        .pin_bit_mask = 1ULL << GPIO_NUM_18, .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    gpio_config(&key_cfg);
    int previous_key = 1, stable_key = 1;
    TickType_t key_changed = xTaskGetTickCount();
    for (;;) {
        TickType_t now = xTaskGetTickCount();
        if (state.header_len && now - state.last_byte > pdMS_TO_TICKS(2000)) {
            state.header_len = state.payload_len = 0;
        }
        uint8_t chunk[512];
        uint32_t length = tud_cdc_read(chunk, sizeof(chunk));
        if (length) {
            state.last_byte = now;
            for (uint32_t i = 0; i < length; ++i) receive_byte(&state, chunk[i]);
        }
        int key = gpio_get_level(GPIO_NUM_18);
        if (key != previous_key) {
            previous_key = key;
            key_changed = now;
        }
        if (key != stable_key && now - key_changed >= pdMS_TO_TICKS(40)) {
            stable_key = key;
            unsigned next = 1 - state.active_page;
            if (key == 0 && state.valid[next]) {
                state.active_page = next;
                rlcd_panel_show(state.pages[next]);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(length ? 1 : 10));
    }
}

esp_err_t screen_bridge_start(void)
{
    return xTaskCreate(screen_task, "screen_bridge", 4096, NULL, 2, NULL) == pdPASS
        ? ESP_OK : ESP_ERR_NO_MEM;
}

// SPDX-License-Identifier: MIT
// Waveshare ESP32-S3-RLCD-4.2: Windows USB playback -> ES8311 -> mono speaker.
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include "driver/i2c_master.h"
#include "driver/i2s_std.h"
#include "esp_check.h"
#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "usb_device_uac.h"

static const char *TAG = "studypet_speaker";
static esp_codec_dev_handle_t speaker;
static atomic_uint requested_volume = 40;
static atomic_bool requested_mute = false;

static void open_speaker(void)
{
    // Pinout: Waveshare official 07_Audio_Test, board S3_RLCD_4_2.
    i2c_master_bus_handle_t bus;
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = GPIO_NUM_13,
        .scl_io_num = GPIO_NUM_14,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &bus));

    i2s_chan_handle_t tx;
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.auto_clear = true;
    ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, &tx, NULL));
    i2s_std_config_t i2s_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(48000),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = GPIO_NUM_16,
            .bclk = GPIO_NUM_9,
            .ws = GPIO_NUM_45,
            .dout = GPIO_NUM_8,
            .din = GPIO_NUM_NC,
        },
    };
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(tx, &i2s_cfg));
    ESP_ERROR_CHECK(i2s_channel_enable(tx));

    audio_codec_i2s_cfg_t data_cfg = { .port = I2S_NUM_0, .tx_handle = tx };
    const audio_codec_data_if_t *data_if = audio_codec_new_i2s_data(&data_cfg);
    ESP_ERROR_CHECK(data_if ? ESP_OK : ESP_ERR_NO_MEM);
    audio_codec_i2c_cfg_t ctrl_cfg = {
        .port = I2C_NUM_0,
        .addr = ES8311_CODEC_DEFAULT_ADDR,
        .bus_handle = bus,
    };
    const audio_codec_ctrl_if_t *ctrl_if = audio_codec_new_i2c_ctrl(&ctrl_cfg);
    const audio_codec_gpio_if_t *gpio_if = audio_codec_new_gpio();
    ESP_ERROR_CHECK(ctrl_if && gpio_if ? ESP_OK : ESP_ERR_NO_MEM);
    es8311_codec_cfg_t codec_cfg = {
        .ctrl_if = ctrl_if,
        .gpio_if = gpio_if,
        .codec_mode = ESP_CODEC_DEV_WORK_MODE_DAC,
        .pa_pin = GPIO_NUM_46,
        .use_mclk = true,
        .hw_gain.pa_gain = 6.0,
    };
    const audio_codec_if_t *codec_if = es8311_codec_new(&codec_cfg);
    ESP_ERROR_CHECK(codec_if ? ESP_OK : ESP_ERR_NO_MEM);
    esp_codec_dev_cfg_t dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_OUT,
        .codec_if = codec_if,
        .data_if = data_if,
    };
    speaker = esp_codec_dev_new(&dev_cfg);
    ESP_ERROR_CHECK(speaker ? ESP_OK : ESP_ERR_NO_MEM);
    esp_codec_dev_sample_info_t format = {
        .sample_rate = 48000, .channel = 2, .bits_per_sample = 16,
    };
    ESP_ERROR_CHECK(esp_codec_dev_open(speaker, &format));
    ESP_ERROR_CHECK(esp_codec_dev_set_out_vol(speaker, 40));
}

static esp_err_t play_usb_audio(uint8_t *buf, size_t len, void *ctx)
{
    (void)ctx;
    if (len % 4 != 0) {
        return ESP_ERR_INVALID_SIZE;
    }
    // Preserve both PC channels on the board's single physical speaker.
    // Average in 32 bits to avoid clipping; duplicate mono into both I2S slots.
    for (size_t i = 0; i < len; i += 4) {
        int16_t left = (int16_t)((uint16_t)buf[i] | (uint16_t)buf[i + 1] << 8);
        int16_t right = (int16_t)((uint16_t)buf[i + 2] | (uint16_t)buf[i + 3] << 8);
        uint16_t mono = (uint16_t)(int16_t)(((int32_t)left + right) / 2);
        buf[i] = buf[i + 2] = (uint8_t)mono;
        buf[i + 1] = buf[i + 3] = (uint8_t)(mono >> 8);
    }
    return esp_codec_dev_write(speaker, buf, (int)len) == ESP_CODEC_DEV_OK ? ESP_OK : ESP_FAIL;
}

static void set_usb_volume(uint32_t volume, void *ctx)
{
    (void)ctx;
    atomic_store(&requested_volume, volume > 100 ? 100 : volume);
}

static void set_usb_mute(uint32_t mute, void *ctx)
{
    (void)ctx;
    atomic_store(&requested_mute, mute != 0);
}

static void volume_task(void *ctx)
{
    (void)ctx;
    unsigned previous_volume = UINT32_MAX;
    bool previous_mute = false;
    for (;;) {
        unsigned volume = atomic_load(&requested_volume);
        bool mute = atomic_load(&requested_mute);
        if (mute != previous_mute) {
            ESP_ERROR_CHECK(esp_codec_dev_set_out_mute(speaker, mute));
            previous_mute = mute;
        }
        if (volume != previous_volume) {
            // The codec maps 0..100 to -50..0 dB (0 is silent). Scaling by
            // 0.70 imposed an extra 15 dB attenuation at the Windows maximum.
            // Preserve its full range; do not add PCM gain above full scale.
            ESP_ERROR_CHECK(esp_codec_dev_set_out_vol(speaker, (int)volume));
            previous_volume = volume;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void app_main(void)
{
    open_speaker();
    ESP_ERROR_CHECK(xTaskCreate(volume_task, "speaker_volume", 3072, NULL, 3, NULL) == pdPASS
                    ? ESP_OK : ESP_ERR_NO_MEM);
    uac_device_config_t usb_cfg = {
        .output_cb = play_usb_audio,
        .input_cb = NULL,
        .set_mute_cb = set_usb_mute,
        .set_volume_cb = set_usb_volume,
    };
    ESP_ERROR_CHECK(uac_device_init(&usb_cfg));
    ESP_LOGI(TAG, "Ready: StudyPet USB Speaker, 48 kHz / 16-bit, stereo mixed to mono");
}

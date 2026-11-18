// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
#include "esp_err.h"
#define RLCD_FRAME_BYTES 15000
esp_err_t rlcd_panel_init(void);
esp_err_t rlcd_panel_show(const uint8_t *frame);

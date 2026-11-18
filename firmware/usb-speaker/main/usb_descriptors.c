// SPDX-License-Identifier: MIT
// Composite UAC2 speaker + CDC screen data. No microphone interface.
#include <string.h>
#include "tusb.h"
#include "uac_descriptors.h"

static const tusb_desc_device_t device = {
    .bLength = sizeof(tusb_desc_device_t), .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200, .bDeviceClass = TUSB_CLASS_MISC,
    .bDeviceSubClass = MISC_SUBCLASS_COMMON, .bDeviceProtocol = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = 0x303A, .idProduct = 0x8001, .bcdDevice = 0x0101,
    .iManufacturer = 1, .iProduct = 2, .iSerialNumber = 3, .bNumConfigurations = 1,
};
static const uint8_t configuration[] = {
    TUD_CONFIG_DESCRIPTOR(1, 4, 0, TUD_CONFIG_DESC_LEN + TUD_AUDIO_DEVICE_DESC_LEN + TUD_CDC_DESC_LEN, 0, 100),
    // Audio control=0, speaker stream=1. OUT 1, feedback IN 1; mic endpoint unused.
    TUD_AUDIO_DESCRIPTOR(0, 4, 0x01, 0x84, 0x81),
    // CDC control=2, data=3. Notification IN 2, bulk OUT/IN 3.
    TUD_CDC_DESCRIPTOR(2, 6, 0x82, 8, 0x03, 0x83, 64),
};
const uint8_t *tud_descriptor_device_cb(void) { return (const uint8_t *)&device; }
const uint8_t *tud_descriptor_configuration_cb(uint8_t index) { (void)index; return configuration; }
const uint16_t *tud_descriptor_string_cb(uint8_t index, uint16_t language)
{
    (void)language;
    static uint16_t buffer[32];
    static const char *strings[] = {"", "StudyPet", "StudyPet Speaker + Display",
        "StudyPet-RLCD42-Prototype", "StudyPet Speaker", "Speaker", "StudyPet Screen"};
    size_t count;
    if (index == 0) {
        buffer[1] = 0x0409;
        count = 1;
    } else {
        if (index >= sizeof(strings) / sizeof(strings[0])) return NULL;
        count = strlen(strings[index]);
        if (count > 31) count = 31;
        for (size_t i = 0; i < count; ++i) buffer[1 + i] = (uint8_t)strings[index][i];
    }
    buffer[0] = (TUSB_DESC_STRING << 8) | (2 * count + 2);
    return buffer;
}

idf_component_register(SRCS "usb_speaker.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_i2c esp_driver_i2s esp_driver_gpio esp_codec_dev usb_device_uac)

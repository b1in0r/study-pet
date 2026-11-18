idf_component_register(SRCS "usb_speaker.c" "usb_descriptors.c" "rlcd_panel.c" "screen_bridge.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_i2c esp_driver_i2s esp_driver_gpio esp_driver_spi esp_codec_dev usb_device_uac tinyusb
    WHOLE_ARCHIVE)

idf_component_get_property(tusb_lib espressif__tinyusb COMPONENT_LIB)
idf_component_get_property(uac_dir espressif__usb_device_uac COMPONENT_DIR)
target_include_directories(${tusb_lib} PUBLIC "${CMAKE_CURRENT_LIST_DIR}" "${uac_dir}/tusb_uac")

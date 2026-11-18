# StudyPet USB Speaker — ESP32-S3-RLCD-4.2

让 Windows 将开发板识别为普通 USB 音频输出设备，播放系统、浏览器和播放器声音。
当前原型只实现扬声器；不包含 USB 麦克风、AI 对话、Wi-Fi 或屏幕界面。

## 硬件与格式

- 开发板：微雪 ESP32-S3-RLCD-4.2，板载 ES8311 DAC，配套单个扬声器。
- USB：接开发板原生 Type-C 数据口；电脑一端 USB-A 或 USB-C 均可。
- USB 产品名称：`StudyPet USB Speaker`，USB Audio Class 2。
  Windows 实测输出名称为 **扬声器（usb uac）**，来自乐鑫组件的音频接口描述。
- 固定 48 kHz / 16-bit / 双声道输入；固件将左右声道取平均并播放单声道。
- Windows 音量和静音通过 USB 控制；编解码器使用完整 0–100 音量范围，初始为 40。
  最大音量对应驱动音量曲线的 0 dB，不对 PCM 额外加增益。
- 此原型沿用乐鑫示例的 VID/PID，仅用于开发验证，量产需合法分配 USB 标识。

接线来自[微雪官方板级配置](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/blob/9e754fdf431ef4fce21e4e8b19bd4079ba043e86/examples/esp-idf/07_Audio_Test/components/ExternLib/codec_board/board_cfg.txt)：

| 功能 | GPIO |
|---|---|
| I2C SDA / SCL | 13 / 14 |
| I2S MCLK / BCLK / LRCLK | 16 / 9 / 45 |
| I2S 扬声器数据输出 | 8 |
| 功放使能（高电平） | 46 |

## 编译

安装官方 [ESP-IDF v5.5.5](https://github.com/espressif/esp-idf/releases/tag/v5.5.5)，
在已激活 ESP-IDF 的 PowerShell 中进入本目录：

```powershell
idf.py set-target esp32s3
idf.py build
```

Component Manager 安装锁定的 `espressif/usb_device_uac 1.3.2` 和
`espressif/esp_codec_dev 1.6.2`；保留 `dependencies.lock` 以复现依赖。
不需要配置 Wi-Fi、模型密钥或插入 SD 卡。

## 备份、烧录与恢复

首次烧录前，将设备现有 16 MB 闪存完整保存到仓库根目录的 `.local/hardware-backups/`。
此目录已被 Git 忽略，备份可能含设备配置，不应公开上传。
以下使用 esptool 5 的命令拼写；`COM3` 需要替换为自己电脑实际端口：

```powershell
python -m esptool --port COM3 --baud 921600 read-flash 0 ALL factory-backup.bin
Get-FileHash factory-backup.bin -Algorithm SHA256
```

确认备份完成后，在本固件目录执行：

```powershell
idf.py -p COM3 flash
```

烧录成功后原生 USB 改由音频协议使用，原 COM 口可能消失，这是预期行为。
需要重新烧录或恢复时，按住 **BOOT**，让开发板重新上电，再松开 **BOOT**。
未安装电池时，可按住 BOOT 拔插 USB 数据线；已安装电池则需要确认开发板真正重新上电。
本板实测可以保持 USB 连接，长按 PWR 后松开，再按住 BOOT、单击 PWR，约 2 秒后松开 BOOT。
等待 Windows 重新出现串口，核对新端口号再运行命令。
按键及下载模式说明见[微雪官方文档](https://docs.waveshare.net/ESP32-S3-RLCD-4.2/)。

完整恢复备份（esptool 5）：

```powershell
python -m esptool --port COM3 --baud 921600 write-flash 0 factory-backup.bin
```

无需预先执行全片擦除。恢复后重启开发板。

## Windows 验收

1. 设置 → 系统 → 声音 → 输出，选择 **扬声器（usb uac）**。
2. 先将音量调低，播放系统测试音，再播放正常人声或音乐。
3. 左、右声道测试都应能听见；只有一个物理扬声器，无法提供空间立体声。
4. 验证系统音量、静音、暂停后恢复、切换输出设备、重新插拔 USB。
5. 连续播放至少 10 分钟，检查断音、噪声和异常发热。

端点识别和播放流可以由电脑验证；实际听感需在设备旁确认。

### 2026-11-18 实测

以下听音记录对应最初限制编解码器最大音量为 70 的版本。
后续移除了 `volume * 0.70`，因为驱动将 70 映射为 −15 dB、100 映射为 0 dB；
原限制导致 Windows 满音量时仍有额外 15 dB 衰减。
音量修正版应用固件大小 287,568 字节，已重新烧录并通过数据校验；
Windows 重新识别为默认扬声器，30% 音量下音频播放调用成功；
用户随后用音视频试听并确认：“明显变大，已经够用”。

- ESP-IDF v5.5.5 编译通过，应用固件大小 287,584 字节。
- 烧录的 bootloader、分区表、应用均通过 esptool 数据校验。
- Windows 成功枚举 USB Audio 输出，已设为默认控制台与多媒体输出。
- Windows 音量设置为 25%；依次播放左声道、右声道、双声道测试音。
- 用户在设备旁确认：三段声音均正常。
- 重新插拔、系统休眠唤醒、长时间播放及不同主机的兼容性仍待补充测试。

## 来源与许可证

本目录应用代码采用仓库 MIT 许可证。通过组件管理器使用的乐鑫组件保留其原有许可证；
USB UAC/TinyUSB 及音频组件的许可证应随二进制再分发一并提供。

- [乐鑫 USB UAC 文档](https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_device/usb_device_uac.html)
- [乐鑫 USB UAC 示例](https://github.com/espressif/esp-iot-solution/tree/master/examples/usb/device/usb_uac)
- [ESP Codec Dev](https://github.com/espressif/esp-adf/tree/master/components/esp_codec_dev)
- [微雪官方例程](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2)

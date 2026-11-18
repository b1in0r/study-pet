# 日历、学习计划与 Codex 屏幕

硬件范围为 ESP32-S3-RLCD-4.2 的 **USB 扬声器 + 400×300 横屏**，不启用 USB 麦克风。
电脑渲染中文图像，通过同一根 USB 线上的 CDC 串口同步；音频继续由 USB Audio 输出。

## 两页界面

- 日历页：上海时区的日期、时钟、月历、今日最多三项任务、完成数量。
  任务来自已有的 StudyPet SQLite 数据库，不自动创建学习任务。
- Codex 页：真实配额窗口的剩余百分比、重置时间、所选对话最近已完成回复的文字摘录。
  官方接口返回 `usedPercent`，界面显示 `100 - usedPercent`，进度条也表示剩余额度，
  与 Codex 电脑端的“剩余”口径一致；两端各自刷新，采样时刻不同可能短暂有差异。
  第一版不另调模型生成摘要，不将配额百分比解释为 Token 数或 API 账单。
- 单击侧边 **KEY** 键翻页。BOOT 保留用于手动进入烧录模式。
- 电脑桥接程序未运行时，开机显示“等待电脑同步”，扬声器仍可单独工作。
  桥接退出后保留最后画面，可据底部同步时间判断数据新旧。

## 电脑端运行

Python 3.11+；先在仓库根目录安装可选依赖：

```powershell
python -m pip install -r requirements-display.txt
codex login status
python -m studypet.display --thread-id YOUR_THREAD_ID
```

最后一条先生成 `.local/display-preview/calendar.png` 和 `codex.png`，便于在电脑检查排版。
字体首次从固定版本的 Google Fonts 下载到 `.local/fonts/`，校验 Git blob 摘要。
字体采用 SIL OFL，许可证保存在固件目录的 `licenses/NotoSansSC-OFL.txt`。

`--thread-id` 指定要展示的 Codex 对话；从 Codex 启动的终端也可使用 `CODEX_THREAD_ID` 环境变量。
未选择对话时只显示用量，不自动读取其他对话。

设备烧录屏幕固件后：

```powershell
python -m studypet.display --port auto --watch --thread-id YOUR_THREAD_ID
```

每 30 秒同步两页，Ctrl+C 退出。`--port auto` 仅匹配本原型的 VID 303A / PID 8001，
不会把屏幕数据发给 ROM 下载串口或其他串口设备；多台设备请显式指定 `--port COM端口`。
可用 `--interval 60` 降低更新频率。

填写计划可以使用[本地网页](PLANNER.md)：双击仓库根目录的“打开计划管理.cmd”，
或运行 `python -m studypet.web` 后访问 `http://127.0.0.1:8765`。
网页与屏幕共用任务数据库，保存后约 30 秒同步。

也可以继续使用现有任务工具：

```powershell
python -m studypet add "阅读一篇论文" --due "2026-11-19T19:00:00+08:00"
python -m studypet list
python -m studypet done 1
```

请将示例日期换成自己的计划时间；只会在任务对应日期的“今日计划”里显示。

## 固件和数据协议

编译步骤见 [固件说明](../firmware/usb-speaker/README.md)。
已使用旧固件生成过 sdkconfig 的开发环境，需在 menuconfig 开启
`USB_DEVICE_UAC_AS_PART`，或保存个人配置后用项目的 sdkconfig.defaults 重新生成配置。

新增 USB 复合设备使用不同的测试 PID，以避免 Windows 沿用旧接口描述。
烧录后会同时出现 **StudyPet Speaker** 音频输出和一个屏幕 CDC 串口。
首次使用可能需要重新选择默认声音输出，先使用较低音量。

一张画面为 15,000 字节 ST7305 原生像素数据，数据包头为 16 字节、小端：

| 字段 | 大小 | 值 |
|---|---|---|
| 魔数 | 4 | SPET |
| 协议版本 | 1 | 1 |
| 数据类型 | 1 | 1（完整画面） |
| 页号 | 2 | 0（日历）/1（Codex） |
| 数据长度 | 4 | 15000 |
| CRC32 | 4 | 标准 zlib CRC32 |

开发板校验整帧后更新页缓存，回复 `OK 0` / `OK 1`；无效数据不替换现有画面。
显示任务低于音频任务优先级。2026-11-18 已上板收到双页确认，用户照片显示方向正常且已切换至 Codex 页；
Windows 同时识别扬声器和 COM4，用户确认声音正常。长时间播放、休眠唤醒等仍待补充测试。

## 数据来源与设计

用量和回复读取基于[官方 Codex app-server](https://learn.chatgpt.com/docs/app-server)：
`account/rateLimits/read`、`thread/items/list`。只读取所选对话的最终回复，
排除推理、工具日志、进度消息和交互式提问；不调用 `turn/start`。
账号凭据留在 Codex 管理的电脑环境中，不传到开发板。
用量读不到时显示暂不可用；若已有成功快照则保留并显示“更新失败”和旧采样时间。

界面针对黑白反射屏：纯黑/纯白、高对比中文、日历与计划双栏、无自动轮播。
用量页与计划页分开，确保 4.2 英寸屏上的字体可读。

参考了同款设备上的 [QuotaFrame](https://github.com/eMUQI/QuotaFrame) 功能范围；
本实现未复制其源码，采用 USB 图像桥接和官方 app-server 数据接口。
屏幕寄存器初始化及像素排列改编自[微雪官方例程](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2)，
驱动保留 Apache-2.0 许可证与修改说明。

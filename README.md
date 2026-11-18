# StudyPet · 学习桌宠

一个连接电脑的实体 AI 学习伙伴：陪你聊天、解释 AI 新知、安排学习任务、帮助复盘，并逐步集成电脑音响与麦克风。

**状态：已有本地任务管理，以及 ESP32-S3-RLCD-4.2 的 USB 扬声器原型；Windows 播放测试已通过。尚未接入大模型、语音识别、资讯抓取和硬件屏幕界面。**

## 项目目标

- Windows 电脑运行 Agent；带屏开发板负责表情、状态显示和按键交互。
- 每日精选少量 AI 资讯，保留来源、发布日期与抓取时间，支持追问。
- 根据学习目标和可用时间提出计划，经用户确认后保存。
- 在约定时间提醒，支持完成、延期、跳过与晚间复盘。
- 基础版本硬件预算目标为人民币 200 元，尽量使用无需焊接的模块。
- 成为电脑的外接音响、麦克风；USB 扬声器原型已验证，USB 麦克风仍待开发。

## 已验证的硬件功能

[USB 扬声器固件](firmware/usb-speaker/README.md)适配微雪 **ESP32-S3-RLCD-4.2**。
使用 USB 数据线连接电脑，Windows 可将其设为默认扬声器，播放浏览器、播放器和系统声音。
支持音量、静音，以及将左右声道合并到板上的单个扬声器。
2026-11-18 已完成编译、烧录、Windows 识别和用户现场听音确认。
编译、首次备份、烧录及恢复步骤见固件目录说明。

## 立即运行已有代码

需要 Python 3.11 或更新版本，无第三方运行依赖。在本目录打开终端：

```powershell
python -m studypet --help
python -m studypet add "阅读一篇 Agent 文章" --due "2026-11-14T19:00:00+08:00"
python -m studypet list
python -m studypet due
python -m studypet done 1
python -m unittest discover -s tests -v
```

请把示例时间改为实际计划时间；时间必须带时区。默认数据库位于 `.local/studypet.sqlite3`，不会纳入 Git。可用全局参数 `--db 路径` 指定其他数据库。

`due` 只列出已到时间、尚未完成的任务；当前版本没有后台计时、弹窗或语音提醒。

## 计划中的架构

```text
资讯来源 ── 检索与引用 ─┐
语音输入 ── 识别 ─────┤
                     电脑 Agent ── 本地任务与偏好数据
语音输出 ◀─ 合成 ─────┤
屏幕开发板 ◀─ 状态 ───┘
```

接电脑运行程序不等于本地运行模型；后续可接云端模型或本地模型。云端调用可能产生费用。

## 参与开发

请先阅读 [开发路线](docs/ROADMAP.md)、[设计约定](docs/DESIGN.md)、[硬件预算](docs/HARDWARE.md) 和 [贡献指南](CONTRIBUTING.md)。版本与分支约定见 [版本管理](docs/VERSION_CONTROL.md)，历史变化见 [更新记录](CHANGELOG.md)。

小范围修复、安装文档、硬件实测记录、资讯引用质量反馈都欢迎。尚未购买硬件也能参与软件开发。

## 参考项目

- [小智 AI](https://github.com/78/xiaozhi-esp32)：硬件语音终端与设备交互。
- [Stack-chan](https://github.com/stack-chan/stack-chan)：表情与桌面角色交互。
- [Reachy Mini](https://github.com/pollen-robotics/reachy_mini)：电脑与实体机器人协作。

本项目目前独立编写，未复制上述项目源码；未来复用代码、字体、声音、模型或外壳时，需分别核对许可证并保留署名。

## 许可证

项目代码以 [MIT License](LICENSE) 发布。用户数据、第三方文章、模型及硬件资料不因本仓库的许可证而自动获得再分发许可。

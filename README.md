# StudyPet · 学习桌宠

一个连接电脑的实体 AI 学习伙伴：安排学习任务、展示日历与 Codex 用量，并集成电脑音响和实体屏幕。

**状态：USB 扬声器、日历学习屏和 Codex 真实用量/回复摘录已上板运行。已提供网页计划管理、本地记忆本、任务历史及电脑通知＋网页提醒；大模型 Agent 对话待接入。**

## 直接填写今日计划

双击仓库根目录的 **打开计划管理.cmd**，即可打开[本地计划页面](http://127.0.0.1:8765)。
支持添加、修改、完成、恢复待完成、删除，以及按日期查看计划；右侧可查看小屏预览。
计划与实体桌历共用数据，屏幕桥接运行时约 30 秒同步一次。详细说明见[网页计划管理](docs/PLANNER.md)。

“记忆本”可以记录目标、偏好与复盘，“历史记录”保留计划和提醒的变化。
后台服务运行时，到点显示电脑通知和网页提醒，可完成、延期 10 分钟或确认收到。
数据只保存在本机，使用条件与数据保留方式见[桌宠记忆与提醒](docs/AGENT_MEMORY.md)。

也可以在本目录运行 `python -m studypet.web` 后打开上述地址。网页本身不需要额外 Python 依赖。

## 保存个人资料

[本地资料库](http://127.0.0.1:8765/library)支持 PDF、Word（.docx）、Markdown、文本与常见图片的导入、原件保存、文字提取和关键词检索。
保留来源位置，支持文字校正、暂停检索和删除。Windows 使用本地 OCR，资料不上传云端。
完整依赖安装 `python -m pip install -r requirements-knowledge.txt`，使用说明与格式边界见[个人资料库](docs/LIBRARY.md)。
模型读取资料与自动提取个人记忆仍待接入。

## 项目目标

- Windows 电脑运行 Agent；带屏开发板负责表情、状态显示和按键交互。
- 每日精选少量 AI 资讯，保留来源、发布日期与抓取时间，支持追问。
- 根据学习目标和可用时间提出计划，经用户确认后保存。
- 在约定时间提醒，支持完成、延期、跳过与晚间复盘。
- 基础版本硬件预算目标为人民币 200 元，尽量使用无需焊接的模块。
- 当前硬件范围为 USB 扬声器、日历学习屏及 Codex 数据展示，不启用 USB 麦克风。

## 已验证的硬件功能

[USB 扬声器固件](firmware/usb-speaker/README.md)适配微雪 **ESP32-S3-RLCD-4.2**。
使用 USB 数据线连接电脑，Windows 可将其设为默认扬声器，播放浏览器、播放器和系统声音。
支持音量、静音，以及将左右声道合并到板上的单个扬声器。
2026-11-18 已完成编译、烧录、Windows 识别和用户现场听音确认。
编译、首次备份、烧录及恢复步骤见固件目录说明。

屏幕预览、USB 同步、按键翻页和 Codex 数据说明见[屏幕开发说明](docs/SCREEN.md)。
屏幕程序的可选依赖独立列在 `requirements-display.txt`，不影响已有任务工具。

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

`due` 只列出已到时间、尚未完成的任务；启动 `python -m studypet.web` 才会在后台检查并提醒，没有语音提醒。

## 当前架构与后续扩展

```text
计划网页 / CLI ── SQLite（任务、历史、记忆、提醒）
                         ├─ 后台调度 ── Windows 通知＋网页提醒
                         └─ 屏幕桥接 ── 实体桌历
Codex app-server ── 用量 / 完成回复 ── 屏幕桥接
电脑系统音频 ── USB ── 开发板扬声器

后续：模型适配、带来源的 AI 资讯、对话规划与复盘
```

接电脑运行程序不等于本地运行模型；后续可接云端模型或本地模型。云端调用可能产生费用。

## 参与开发

个人助理的目录、数据存储和上下文设计见 [架构规划](docs/architecture/README.md)。当前正式库为 v3，已落地资料库、资料分类与统一迁移入口。

请先阅读 [开发路线](docs/ROADMAP.md)、[设计约定](docs/DESIGN.md)、[硬件预算](docs/HARDWARE.md) 和 [贡献指南](CONTRIBUTING.md)。版本与分支约定见 [版本管理](docs/VERSION_CONTROL.md)，历史变化见 [更新记录](CHANGELOG.md)。

小范围修复、安装文档、硬件实测记录、资讯引用质量反馈都欢迎。尚未购买硬件也能参与软件开发。

## 参考项目

- [小智 AI](https://github.com/78/xiaozhi-esp32)：硬件语音终端与设备交互。
- [Stack-chan](https://github.com/stack-chan/stack-chan)：表情与桌面角色交互。
- [Reachy Mini](https://github.com/pollen-robotics/reachy_mini)：电脑与实体机器人协作。

屏幕驱动的初始化和像素排列改编自微雪官方例程，保留 Apache-2.0 许可证；
中文显示使用 Noto Sans SC（SIL OFL）。第三方许可见固件目录的 `licenses/`，来源见[屏幕开发说明](docs/SCREEN.md)。

## 许可证

项目代码以 [MIT License](LICENSE) 发布。用户数据、第三方文章、模型及硬件资料不因本仓库的许可证而自动获得再分发许可。

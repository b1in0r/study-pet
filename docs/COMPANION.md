# 快速日记与助理

「快速日记」使用浏览器选定的系统麦克风。开始录音后，最长两分钟自动停止，也可随时点击停止。中文在本机转写成可编辑的文字。点击保存才会写入数据库。时间轴支持补记日期、编辑和删除。已有录音转写失败时，可以重试或改用手动输入。

「问助理」使用个人档案片段、近期任务和关键词检索到的资料片段。勾选「本次参考近一周日记」后才会附上最近七天内的最多五篇日记片段。每个回答列出模型选用的来源。若出现「保存为计划」，确认日期和时间后才会保存。StudyPet 不将助理对话写入数据库，继续追问时会发送近期对话片段。

在快速日记点「复盘今天」，可查看当天日记、按实际完成时间统计的任务，以及今天和明天的待办。模型会根据这些记录和明天可用时间生成建议。模型不可用时会显示原记录和按时间选出的待办。填写提醒时间并确认后，已有待办会调整到明天，新的建议会添加到明天的计划。

## 默认文字模型

「问助理」和「晚间复盘」通过 [Codex CLI](https://learn.chatgpt.com/docs/non-interactive-mode) 复用本机的 ChatGPT 登录。点击发送或复盘时，页面提示列出的文字片段会发给 OpenAI 生成回复。录音转写和日记存储在本机进行。助理只检索相关文字片段，原始附件留在本机。

如果本机还未登录，在终端运行 `codex login` 并选择 ChatGPT。运行 `codex login status` 可检查登录状态。可在启动网页前设置 `STUDYPET_TEXT_MODEL=ollama`，或用 `python -m studypet.web --text-model ollama` 切换到本机生成。

## 准备语音转写和可选的本地模型

使用启动脚本所选的同一个 Python 环境，在项目根目录执行以下命令。首次下载模型需要联网。

```powershell
python -m pip install -r requirements-voice.txt
python -c "from faster_whisper.utils import download_model; download_model('small', output_dir='.local/models/whisper-small')"
```

语音识别使用已下载的 [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) 模型。录音仅在转写过程中处理，数据库保存确认后的文字。启用 [Ollama](https://docs.ollama.com/api/chat) 时，可以用 `ollama pull qwen3:4b` 准备模型，也可以使用已安装的 `qwen3:0.6b` 或 `qwen2.5:0.5b`。

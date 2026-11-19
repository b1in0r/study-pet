# 快速日记与助理

「快速日记」使用浏览器选定的系统麦克风。开始录音后，最长两分钟自动停止，也可随时点击停止。中文在本机转写成可编辑的文字。点击保存才会写入数据库。时间轴支持补记日期、编辑和删除。已有录音转写失败时，可以重试或改用手动输入。

「问助理」使用个人档案、近期任务和关键词检索到的资料片段。勾选「本次参考近一周日记」后才会读取最近七天内的最多五篇日记。每个回答列出模型选用的来源。若出现「保存为计划」，确认日期和时间后才会保存。当前对话只留在页面内。

## 初次准备

使用启动脚本所选的同一个 Python 环境，在项目根目录执行以下命令。首次下载模型需要联网。

```powershell
python -m pip install -r requirements-voice.txt
python -c "from faster_whisper.utils import download_model; download_model('small', output_dir='.local/models/whisper-small')"
ollama pull qwen3:4b
```

语音识别使用已下载的 [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) 模型。文字助理使用 [Ollama 的本机聊天接口](https://docs.ollama.com/api/chat)。点击发送时，StudyPet 会检查本机 Ollama，必要时启动它。若本机只有 `qwen3:0.6b`，也可以回答。模型未就绪时显示本地资料概览。录音仅在转写过程中处理，数据库保存确认后的文字。两个页面都可以通过原来的启动脚本进入。

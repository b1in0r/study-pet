"""Loopback-only text generation and offline voice transcription."""
import io
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

OLLAMA_MODELS = ('qwen3:4b', 'qwen3:0.6b', 'qwen2.5:0.5b')
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class LocalAIError(RuntimeError):
    pass


class Ollama:
    def __init__(self, state_dir):
        self.state_dir = Path(state_dir)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.start_lock = threading.Lock()

    def request(self, path, payload=None, timeout=5):
        request = urllib.request.Request('http://127.0.0.1:11434' + path)
        if payload is not None:
            request.add_header('Content-Type', 'application/json')
            request.data = json.dumps(payload, ensure_ascii=False).encode()
        with self.opener.open(request, timeout=timeout) as response:
            return json.load(response)

    def available_models(self):
        with self.start_lock:
            try:
                return self.request('/api/tags', timeout=2)['models']
            except (OSError, ValueError, KeyError):
                executable = shutil.which('ollama')
                if not executable and os.name == 'nt':
                    installed = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Ollama/ollama.exe'
                    if installed.is_file():
                        executable = str(installed)
                if not executable:
                    raise LocalAIError('找不到 Ollama，请先安装并下载 qwen3:4b。')
                self.state_dir.mkdir(parents=True, exist_ok=True)
                env = {**os.environ, 'OLLAMA_HOST': '127.0.0.1:11434', 'OLLAMA_NO_CLOUD': '1'}
                try:
                    with (self.state_dir / 'ollama-service.log').open('ab') as log:
                        subprocess.Popen([executable, 'serve'], env=env, stdout=log, stderr=log,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                except OSError as error:
                    raise LocalAIError('本地模型服务未能启动，请检查 Ollama。') from error
                for _ in range(30):
                    try:
                        return self.request('/api/tags', timeout=1)['models']
                    except (OSError, ValueError, KeyError):
                        time.sleep(0.2)
                raise LocalAIError('本地模型服务未能启动，请检查 Ollama。')

    def generate(self, instruction, content, *, output_schema='json'):
        names = {model.get('name') for model in self.available_models()}
        model = next((name for name in OLLAMA_MODELS if name in names), None)
        if model is None:
            raise LocalAIError('本机还没有助理所需的 Ollama 模型。')
        try:
            result = self.request('/api/chat', {
                'model': model, 'stream': False, 'format': output_schema,
                **({'think': False} if model.startswith('qwen3:') else {}),
                'messages': [{'role': 'system', 'content': instruction},
                             {'role': 'user', 'content': json.dumps(content, ensure_ascii=False)}],
                'options': {'num_ctx': 8192, 'num_predict': 850, 'temperature': 0.2},
                'keep_alive': '3m',
            }, timeout=120)
            return json.loads(result['message']['content'])
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise LocalAIError('本地模型未能完成回答，请稍后再试。') from error


class Transcriber:
    def __init__(self, state_dir):
        self.model_dir = Path(state_dir) / 'models' / 'whisper-small'
        self.lock = threading.Lock()
        self.model = None

    def transcribe(self, recording):
        try:
            from faster_whisper import WhisperModel
            from faster_whisper.audio import decode_audio
        except ImportError as error:
            raise LocalAIError('语音组件尚未安装，可以先手动写日记。') from error
        if not (self.model_dir / 'model.bin').is_file():
            raise LocalAIError('本地语音模型尚未准备好，可以先手动写日记。')
        if not self.lock.acquire(blocking=False):
            raise LocalAIError('另一段录音正在转写，请稍后重试。')
        try:
            if self.model is None:
                self.model = WhisperModel(str(self.model_dir), device='cpu', compute_type='int8',
                                          local_files_only=True, cpu_threads=min(6, os.cpu_count() or 2))
            samples = decode_audio(io.BytesIO(recording), sampling_rate=16000)
            if len(samples) > 125 * 16000:
                raise LocalAIError('单段录音最长 2 分钟，请分段录入。')
            segments, _ = self.model.transcribe(samples, language='zh',
                                                vad_filter=True, beam_size=3, condition_on_previous_text=False,
                                                initial_prompt='以下是简体中文日记。')
            text = ''.join(segment.text for segment in segments).strip()
        except LocalAIError:
            raise
        except Exception as error:
            raise LocalAIError('没能转写这段录音，请重试或手动输入。') from error
        finally:
            self.lock.release()
        if not text:
            raise LocalAIError('没有识别到讲话，请检查麦克风或重录。')
        return text

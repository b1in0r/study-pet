'use strict';

const $ = selector => document.querySelector(selector);
const day = $('#journal-day');
const body = $('#journal-body');
const record = $('#record');
const save = $('#save-journal');
const retry = $('#retry-recording');
const older = $('#older-journal');
let today, editing, oldest, recorder, retainedRecording, timer;
let working = false;
let departing = false;

async function request(url, options) {
  const response = await fetch(url, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || '操作未完成，请重试。');
  return value;
}

function status(text, error = false) {
  const label = $('#journal-status');
  label.textContent = text;
  label.classList.toggle('error', error);
}

function refreshControls() {
  const recording = recorder?.state === 'recording';
  record.textContent = recording ? '停止并转写' : '开始录音';
  record.classList.toggle('recording', recording);
  record.disabled = working;
  save.disabled = working || recording;
  retry.hidden = !retainedRecording || recording || working;
}

async function transcribe() {
  if (!retainedRecording || working) return;
  working = true;
  refreshControls();
  status('正在本机转成文字…');
  try {
    const {text} = await request('/api/journal/transcribe', {
      method: 'POST',
      headers: {'Content-Type': retainedRecording.type},
      body: retainedRecording,
    });
    body.value = [body.value.trim(), text].filter(Boolean).join('\n').slice(0, body.maxLength);
    retainedRecording = null;
    status('转写完成。核对文字后，点「保存日记」。');
    body.focus();
  } catch (error) {
    status(error.message, true);
  } finally {
    working = false;
    refreshControls();
  }
}

async function toggleRecording() {
  if (recorder?.state === 'recording') {
    stopRecording();
    return;
  }
  working = true;
  refreshControls();
  let stream;
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      throw new Error('这个浏览器无法录音，可以先手动填写。');
    }
    stream = await navigator.mediaDevices.getUserMedia({audio: true});
    recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.addEventListener('dataavailable', event => {
      if (event.data.size) chunks.push(event.data);
    });
    recorder.addEventListener('stop', () => {
      clearTimeout(timer);
      stream.getTracks().forEach(track => track.stop());
      working = false;
      if (departing) return;
      retainedRecording = new Blob(chunks, {type: recorder.mimeType});
      transcribe();
    }, {once: true});
    recorder.start();
    retainedRecording = null;
    status('正在录音，最多 2 分钟。说完点「停止并转写」。');
    timer = setTimeout(() => {
      if (recorder.state === 'recording') stopRecording();
    }, 120000);
  } catch (error) {
    stream?.getTracks().forEach(track => track.stop());
    status(error.name === 'NotAllowedError' ? '请允许浏览器使用麦克风，或手动填写。' : error.message, true);
  } finally {
    working = false;
    refreshControls();
  }
}

function stopRecording() {
  working = true;
  recorder.stop();
  refreshControls();
}

function resetEditor() {
  editing = null;
  body.value = '';
  day.value = today;
  retainedRecording = null;
  $('#cancel-edit').hidden = true;
}

function action(label, listener) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'text-button';
  button.textContent = label;
  button.addEventListener('click', listener);
  return button;
}

function canEdit() {
  return !working && recorder?.state !== 'recording';
}

function showEntry(entry) {
  const article = document.createElement('article');
  article.className = 'companion-entry';
  const heading = document.createElement('h3');
  heading.textContent = entry.day;
  const text = document.createElement('p');
  text.textContent = entry.body;
  const buttons = document.createElement('div');
  buttons.className = 'companion-actions';
  buttons.append(action('编辑', () => {
    if (!canEdit()) return;
    editing = entry.id;
    day.value = entry.day;
    body.value = entry.body;
    retainedRecording = null;
    refreshControls();
    $('#cancel-edit').hidden = false;
    status('正在编辑已保存的日记。');
    body.focus();
  }), action('删除', async () => {
    if (!canEdit() || !confirm('删除这篇日记？')) return;
    try {
      await request(`/api/journal/${entry.id}`, {method: 'DELETE'});
      if (editing === entry.id) resetEditor();
      await load();
      status('已删除日记。');
    } catch (error) {
      status(error.message, true);
    }
  }));
  article.append(heading, text, buttons);
  return article;
}

async function load(before) {
  const suffix = before ? `?before=${encodeURIComponent(before)}` : '';
  const result = await request('/api/journal' + suffix);
  today = result.today;
  if (!day.value) day.value = today;
  const list = $('#journal-entries');
  if (!before) list.replaceChildren();
  list.append(...result.entries.map(showEntry));
  if (!before && !result.entries.length) {
    const note = document.createElement('p');
    note.className = 'companion-intro';
    note.textContent = '还没有日记。可以从今天的一件小事开始。';
    list.append(note);
  }
  oldest = result.entries.at(-1)?.id;
  older.hidden = !result.has_more;
}

record.addEventListener('click', toggleRecording);
retry.addEventListener('click', transcribe);
$('#cancel-edit').addEventListener('click', () => {
  if (!canEdit()) return;
  resetEditor();
  refreshControls();
  status('');
});
older.addEventListener('click', async () => {
  older.disabled = true;
  try { await load(oldest); }
  catch (error) { status(error.message, true); }
  finally { older.disabled = false; }
});
$('#journal-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!canEdit()) return;
  working = true;
  refreshControls();
  try {
    await request(editing ? `/api/journal/${editing}` : '/api/journal', {
      method: editing ? 'PATCH' : 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({day: day.value, body: body.value}),
    });
    resetEditor();
    await load();
    status('已保存到本机。');
  } catch (error) {
    status(error.message, true);
  } finally {
    working = false;
    refreshControls();
  }
});
window.addEventListener('pagehide', () => {
  departing = true;
  if (recorder?.state === 'recording') recorder.stop();
  recorder?.stream.getTracks().forEach(track => track.stop());
});
window.addEventListener('pageshow', () => {
  departing = false;
  refreshControls();
});
load().catch(error => status(error.message, true));

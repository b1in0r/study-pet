'use strict';
const $ = (selector) => document.querySelector(selector);
const state = { date: '', today: '', tasks: [], days: {}, filter: 'all', preview: 'calendar', editing: null, deleting: null, request: 0 };
const dateLabel = new Intl.DateTimeFormat('zh-CN', {year:'numeric',month:'long',day:'numeric',weekday:'long',timeZone:'Asia/Shanghai'});
const timeLabel = new Intl.DateTimeFormat('zh-CN', {hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Shanghai'});
let toastTimer;

async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: options.body ? {'Content-Type':'application/json'} : {}, cache:'no-store'});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || '操作未完成，请重试');
  return payload;
}
function notify(message, error = false) {
  clearTimeout(toastTimer);
  $('#toast').textContent = message;
  $('#toast').classList.toggle('error', error);
  $('#toast').hidden = false;
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, error ? 7000 : 4000);
}
function dayString(day) {
  return `${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`;
}
function localDay(value) { return new Date(`${value}T12:00:00+08:00`); }
function shiftDay(count) {
  const [year, month, day] = state.date.split('-').map(Number);
  selectDate(dayString(new Date(year, month-1, day+count)));
}
function shiftMonth(count) {
  const [year, month] = state.date.split('-').map(Number);
  selectDate(dayString(new Date(year, month-1+count, 1)));
}
async function selectDate(value) {
  state.date = value;
  $('#task-date').value = value;
  renderHeading();
  renderCalendar();
  await loadTasks();
}
function renderHeading() {
  $('#day-label').textContent = dateLabel.format(localDay(state.date));
  $('#page-heading').textContent = state.date === state.today ? '今日计划' : `${Number(state.date.slice(5,7))}月${Number(state.date.slice(8))}日的计划`;
  document.title = `${$('#page-heading').textContent} · StudyPet`;
}
function renderCalendar() {
  const [year, month] = state.date.split('-').map(Number);
  $('#month-label').textContent = `${year}年 ${month}月`;
  const offset = (new Date(year,month-1,1).getDay()+6)%7;
  const count = new Date(year,month,0).getDate();
  const container = $('#calendar');
  container.replaceChildren();
  for (let n=0; n<offset; n++) container.append(document.createElement('span'));
  for (let day=1; day<=count; day++) {
    const value = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = day;
    button.classList.toggle('selected', value === state.date);
    button.classList.toggle('is-today', value === state.today);
    button.classList.toggle('has-tasks', Boolean(state.days[value]));
    button.setAttribute('aria-label', `${month}月${day}日${state.days[value] ? `，${state.days[value]}项计划` : ''}`);
    button.setAttribute('aria-pressed', String(value === state.date));
    button.addEventListener('click', () => selectDate(value));
    container.append(button);
  }
}
function taskButton(label, className, action) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.className = className;
  button.addEventListener('click', action);
  return button;
}
function renderTasks() {
  const tasks = state.tasks.filter(task => state.filter === 'all' || task.status === state.filter);
  const done = state.tasks.filter(task => task.status === 'done').length;
  $('#progress-text').textContent = `已完成 ${done} / ${state.tasks.length}`;
  const list = $('#task-list');
  list.replaceChildren();
  for (const task of tasks) {
    const row = document.createElement('article');
    row.className = `task-row${task.status === 'done' ? ' done' : ''}`;
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.className = 'task-check';
    check.checked = task.status === 'done';
    check.setAttribute('aria-label', `${check.checked ? '恢复未完成' : '标记完成'}：${task.title}`);
    check.addEventListener('change', async () => {
      check.disabled = true;
      try {
        await api(`/api/tasks/${task.id}`, {method:'PATCH',body:JSON.stringify({status:check.checked ? 'done' : 'pending'})});
        await loadTasks();
        notify(check.checked ? '完成了一项计划' : '已恢复为待完成');
      } catch (error) { check.checked = !check.checked; check.disabled = false; notify(error.message,true); }
    });
    const content = document.createElement('div');
    const title = document.createElement('p');
    title.className = 'task-title';
    title.textContent = task.title;
    const meta = document.createElement('p');
    meta.className = 'task-time';
    meta.textContent = timeLabel.format(new Date(task.due_at));
    if (task.status === 'done') {
      const label = document.createElement('span'); label.className = 'completed-label'; label.textContent = '已完成'; meta.append(label);
    }
    content.append(title,meta);
    const actions = document.createElement('div');
    actions.className = 'task-actions';
    const edit = taskButton('修改','edit-action',() => openEdit(task));
    edit.setAttribute('aria-label',`修改计划：${task.title}`);
    const remove = taskButton('删除','delete-action',() => {
      state.deleting = task.id;
      $('#delete-title').textContent = task.title;
      $('#delete-dialog').showModal();
      $('#cancel-delete').focus();
    });
    remove.setAttribute('aria-label',`删除计划：${task.title}`);
    actions.append(edit,remove);
    row.append(check,content,actions);
    list.append(row);
  }
  $('#empty-state').hidden = tasks.length !== 0;
  if (state.tasks.length === 0) {
    $('#empty-heading').textContent = state.date === state.today ? '今天还没有计划' : '这一天还没有计划';
    $('#empty-copy').textContent = '先写下最想完成的一件事。';
    $('#focus-compose').hidden = false;
  } else {
    $('#empty-heading').textContent = state.filter === 'done' ? '还没有完成的计划' : '这一天的计划都完成了';
    $('#empty-copy').textContent = state.filter === 'done' ? '完成一项，就在清单上打一个勾。' : '可以休息一下，也可以再安排一件小事。';
    $('#focus-compose').hidden = true;
  }
}
async function loadTasks() {
  const request = ++state.request;
  try {
    const data = await api(`/api/tasks?date=${encodeURIComponent(state.date)}`);
    if (request !== state.request) return;
    state.tasks = data.tasks;
    state.days = data.days;
    state.today = data.today;
    $('#load-error').hidden = true;
    renderHeading(); renderCalendar(); renderTasks();
  } catch (error) {
    if (request !== state.request) return;
    $('#load-error').textContent = '计划读取失败：' + error.message;
    $('#load-error').hidden = false;
    $('#empty-state').hidden = true;
  }
}
function refreshPreview() {
  const image = $('#preview-image');
  image.src = `/preview/${state.preview}.png?t=${Date.now()}`;
  image.alt = state.preview === 'calendar' ? '学习桌历最近生成的日历与计划画面' : '学习桌历最近生成的 Codex 用量与回复画面';
}
async function refreshStatus() {
  try {
    const data = await api('/api/status');
    $('#sync-dot').classList.toggle('online',data.connected);
    $('#sync-status').textContent = data.connected ? '桌历同步正常' : '等待桌历同步';
    $('#last-sync').textContent = data.last_sync_at ? `上次同步 ${new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(data.last_sync_at))}` : '等待首次同步';
    if (data.connected) refreshPreview();
  } catch (_) {
    $('#sync-dot').classList.remove('online');
    $('#sync-status').textContent = '本地服务未连接';
  }
}
function openEdit(task) {
  state.editing = task.id;
  $('#edit-title').value = task.title;
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(task.due_at));
  const get = name => parts.find(part => part.type === name).value;
  $('#edit-date').value = `${get('year')}-${get('month')}-${get('day')}`;
  $('#edit-time').value = timeLabel.format(new Date(task.due_at));
  $('#edit-dialog').showModal();
  $('#edit-title').focus();
}
$('#add-form').addEventListener('submit',async event => {
  event.preventDefault();
  const button = $('#add-button'); button.disabled = true;
  const payload = {title:$('#task-title').value,date:$('#task-date').value,time:$('#task-time').value};
  try {
    await api('/api/tasks',{method:'POST',body:JSON.stringify(payload)});
    $('#task-title').value = '';
    state.filter = 'all';
    document.querySelectorAll('[data-filter]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.filter === 'all')));
    await selectDate(payload.date);
    $('#task-title').focus();
    notify('计划已保存，稍后同步到桌历');
  } catch (error) { notify(error.message,true); }
  finally { button.disabled = false; }
});
$('#edit-form').addEventListener('submit',async event => {
  event.preventDefault();
  const button = $('#save-edit'); button.disabled = true;
  const payload = {title:$('#edit-title').value,date:$('#edit-date').value,time:$('#edit-time').value};
  try {
    await api(`/api/tasks/${state.editing}`,{method:'PATCH',body:JSON.stringify(payload)});
    $('#edit-dialog').close();
    await selectDate(payload.date);
    notify('修改已保存');
  } catch (error) { notify(error.message,true); }
  finally { button.disabled = false; }
});
$('#confirm-delete').addEventListener('click',async () => {
  const button = $('#confirm-delete'); button.disabled = true;
  try {
    await api(`/api/tasks/${state.deleting}`,{method:'DELETE'});
    $('#delete-dialog').close();
    await loadTasks();
    notify('计划已删除');
  } catch (error) { notify(error.message,true); }
  finally { button.disabled = false; }
});
$('#close-edit').addEventListener('click',() => $('#edit-dialog').close());
$('#cancel-edit').addEventListener('click',() => $('#edit-dialog').close());
$('#cancel-delete').addEventListener('click',() => $('#delete-dialog').close());
$('#focus-compose').addEventListener('click',() => $('#task-title').focus());
$('#previous-day').addEventListener('click',() => shiftDay(-1));
$('#next-day').addEventListener('click',() => shiftDay(1));
$('#previous-month').addEventListener('click',() => shiftMonth(-1));
$('#next-month').addEventListener('click',() => shiftMonth(1));
$('#back-today').addEventListener('click',() => selectDate(state.today));
$('#refresh-preview').addEventListener('click',() => {refreshPreview();refreshStatus();});
$('#preview-image').addEventListener('load',() => {$('#preview-image').hidden = false;$('#preview-empty').hidden = true;});
$('#preview-image').addEventListener('error',() => {$('#preview-image').hidden = true;$('#preview-empty').hidden = false;});
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click',() => {
  state.filter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(other => other.setAttribute('aria-pressed',String(other === button)));
  renderTasks();
}));
document.querySelectorAll('[data-preview]').forEach(button => button.addEventListener('click',() => {
  state.preview = button.dataset.preview;
  document.querySelectorAll('[data-preview]').forEach(other => other.setAttribute('aria-pressed',String(other === button)));
  refreshPreview();
}));
async function start() {
  try {
    const data = await api('/api/status');
    state.today = data.today;
    $('#task-time').value = '20:00';
    await selectDate(state.today);
    refreshPreview(); await refreshStatus();
    setInterval(refreshStatus, 10000);
    setInterval(loadTasks, 30000);
  } catch (error) {
    $('#load-error').hidden = false;
    $('#load-error').textContent = '无法连接本地服务，请刷新页面重试。';
    $('#sync-status').textContent = '本地服务未连接';
  }
}
start();

'use strict';

const $ = selector => document.querySelector(selector);
const form = $('#profile-form');
const kind = $('#profile-kind');
const title = $('#profile-title');
const details = $('#profile-details');
const supportingDocument = $('#profile-document');
const save = $('#save-profile');
const errorMessage = $('#profile-error');
const statusMessage = $('#profile-status');
let editing = null;
let busy = false;

async function request(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作未完成，请重试');
  return data;
}

function showError(error) {
  errorMessage.textContent = error.message;
  errorMessage.hidden = false;
}

function resetEditor() {
  editing = null;
  form.reset();
  $('#entry-heading').textContent = '添加记录';
  $('#cancel-profile').hidden = true;
}

function edit(entry) {
  if (busy) return;
  editing = entry;
  kind.value = entry.kind;
  title.value = entry.title;
  details.value = entry.details;
  supportingDocument.value = entry.document_title ? entry.document_id : '';
  $('#entry-heading').textContent = '编辑记录';
  $('#cancel-profile').hidden = false;
  statusMessage.textContent = '';
  errorMessage.hidden = true;
  title.focus();
}

async function remove(entry) {
  if (busy || !confirm(`删除档案「${entry.title}」？`)) return;
  busy = true;
  save.disabled = true;
  errorMessage.hidden = true;
  try {
    await request(`/api/profile/${entry.id}`, {method: 'DELETE'});
    if (editing?.id === entry.id) resetEditor();
    await loadProfile();
    statusMessage.textContent = '已删除记录';
  } catch (error) {
    showError(error);
  } finally {
    busy = false;
    save.disabled = false;
  }
}

function action(label, handler) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'text-button';
  button.textContent = label;
  button.addEventListener('click', handler);
  return button;
}

function displayEntry(entry, kindLabel) {
  const card = document.createElement('article');
  card.className = 'profile-entry';
  const meta = document.createElement('p');
  meta.className = 'profile-entry-meta';
  meta.textContent = kindLabel;
  if (entry.document_title) meta.textContent += ` · 关联资料：${entry.document_title}`;
  if (entry.document_id && !entry.document_title) meta.textContent += ' · 关联资料已移除';
  const heading = document.createElement('h3');
  heading.textContent = entry.title;
  const body = document.createElement('p');
  body.className = 'profile-details';
  body.textContent = entry.details;
  const actions = document.createElement('div');
  actions.className = 'profile-actions';
  actions.append(action('编辑', () => edit(entry)), action('删除', () => remove(entry)));
  card.append(meta, heading, body, actions);
  return card;
}

async function loadProfile() {
  const {entries, kinds} = await request('/api/profile');
  const list = $('#profile-list');
  $('#profile-count').textContent = `${entries.length} 条`;
  list.replaceChildren(...entries.map(entry => displayEntry(entry, kinds[entry.kind])));
  if (!entries.length) {
    const message = document.createElement('p');
    message.className = 'profile-intro';
    message.textContent = '还没有记录。可以先写一条当前阶段和一条近期目标。';
    list.append(message);
  }
  return kinds;
}

async function initialize() {
  try {
    const [kinds, {documents}] = await Promise.all([
      loadProfile(), request('/api/library/documents'),
    ]);
    for (const [value, label] of Object.entries(kinds)) kind.add(new Option(label, value));
    for (const item of documents) {
      if (item.state !== 'importing') supportingDocument.add(new Option(item.original_name, item.id));
    }
    save.disabled = false;
  } catch (error) {
    showError(error);
  }
}

$('#cancel-profile').addEventListener('click', () => {
  if (!busy) resetEditor();
});
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  save.disabled = true;
  errorMessage.hidden = true;
  statusMessage.textContent = '';
  const entry = editing;
  try {
    await request(entry ? `/api/profile/${entry.id}` : '/api/profile', {
      method: entry ? 'PATCH' : 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        kind: kind.value, title: title.value, details: details.value,
        document_id: supportingDocument.value || null, revision: entry?.revision,
      }),
    });
    resetEditor();
    await loadProfile();
    statusMessage.textContent = '已保存到本机';
  } catch (error) {
    showError(error);
  } finally {
    busy = false;
    save.disabled = false;
  }
});

initialize();

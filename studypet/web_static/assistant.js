'use strict';

const $ = selector => document.querySelector(selector);
const ask = $('#ask');
const question = $('#question');
const chatStatus = $('#chat-status');
const dialog = $('#plan-dialog');
const history = [];
let requestInProgress = false;
let activePlanButton;

async function jsonRequest(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '未完成请求，请重试。');
  return result;
}

function beijingDate() {
  return new Intl.DateTimeFormat('sv-SE', {timeZone: 'Asia/Shanghai'}).format(new Date());
}

function addMessage(speaker, content) {
  const article = document.createElement('article');
  article.className = 'companion-entry';
  const heading = document.createElement('h3');
  heading.textContent = speaker;
  const text = document.createElement('p');
  text.textContent = content;
  article.append(heading, text);
  $('#chat-messages').append(article);
  return article;
}

function showReply(reply) {
  const article = addMessage(reply.mode === 'source_summary' ? '本地资料概览' : 'StudyPet', reply.answer);
  if (reply.sources.length) {
    const list = document.createElement('ul');
    list.className = 'chat-source-list';
    list.setAttribute('aria-label', '回答依据');
    for (const source of reply.sources) {
      const row = document.createElement('li');
      row.textContent = `[${source.id}] ${source.label}`;
      list.append(row);
    }
    article.append(list);
  }
  if (reply.task_title) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'text-button';
    button.textContent = '保存为计划';
    button.addEventListener('click', () => {
      activePlanButton = button;
      $('#plan-title').value = reply.task_title;
      $('#plan-date').value = beijingDate();
      $('#plan-time').value = '';
      $('#plan-status').textContent = '';
      dialog.showModal();
    });
    article.append(button);
  }
}

$('#chat-form').addEventListener('submit', async event => {
  event.preventDefault();
  const message = question.value.trim();
  if (requestInProgress || !message) return;
  requestInProgress = true;
  ask.disabled = true;
  question.readOnly = true;
  chatStatus.classList.remove('error');
  chatStatus.textContent = '正在本机整理回答，首次加载模型可能需要稍等…';
  try {
    const includeJournal = $('#include-journal').checked;
    const reply = await jsonRequest('/api/assistant', {
      question: message, history: history.slice(-6), include_journal: includeJournal,
    });
    addMessage('你', message);
    showReply(reply);
    if (!includeJournal && reply.mode !== 'source_summary') {
      history.push({role: 'user', content: message.slice(0, 600)},
                   {role: 'assistant', content: reply.answer.slice(0, 600)});
      if (history.length > 6) history.splice(0, history.length - 6);
    }
    question.value = '';
    $('#include-journal').checked = false;
    chatStatus.textContent = '';
  } catch (error) {
    chatStatus.textContent = error.message;
    chatStatus.classList.add('error');
  } finally {
    requestInProgress = false;
    ask.disabled = false;
    question.readOnly = false;
    question.focus();
  }
});

$('#cancel-plan').addEventListener('click', () => dialog.close());
$('#plan-form').addEventListener('submit', async event => {
  event.preventDefault();
  const save = $('#save-plan');
  const planButton = activePlanButton;
  save.disabled = true;
  try {
    await jsonRequest('/api/tasks', {
      title: $('#plan-title').value, date: $('#plan-date').value, time: $('#plan-time').value,
    });
    planButton.disabled = true;
    planButton.textContent = '计划已保存';
    dialog.close();
    chatStatus.textContent = '计划已保存，按你选的时间提醒。';
    chatStatus.classList.remove('error');
  } catch (error) {
    $('#plan-status').textContent = error.message;
  } finally {
    save.disabled = false;
  }
});

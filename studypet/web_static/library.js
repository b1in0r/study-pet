'use strict';
const $=selector=>document.querySelector(selector);
const states={importing:'正在提取',ready:'可检索',needs_text:'待补充文字',failed:'待处理'};
const dates=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'short',day:'numeric',timeZone:'Asia/Shanghai'});
let currentDocument=null,toastTimer,uploading=false;
const categoryFilter = $('#category-filter');
const uploadCategory = $('#upload-category');
const targetCategory = $('#target-category');
const selectedDocuments = new Set();
let categories = {};
let visibleDocuments = [];
let managingCategories = false;
let savingCategories = false;
let libraryRequest = 0;
async function api(url,options={}){
  const response=await fetch(url,{cache:'no-store',...options});
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||'操作未完成，请重试');
  return data;
}
function notify(text,error=false){clearTimeout(toastTimer);$('#toast').textContent=text;$('#toast').classList.toggle('error',error);$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,6500);}
function locationLabel(locator){return locator.page?`第 ${locator.page} 页${locator.method==='ocr'?' · OCR':''}`:locator.paragraph?`第 ${locator.paragraph} 段`:locator.image?'图片文字':`第 ${locator.line_start||1} 行起`;}
function formatSize(size){return size<1024*1024?`${Math.max(1,Math.round(size/1024))} KB`:`${(size/1024/1024).toFixed(1)} MB`;}
function empty(title,description){const block=document.createElement('div');block.className='library-empty';const heading=document.createElement('h3');heading.textContent=title;const body=document.createElement('p');body.textContent=description;block.append(heading,body);return block;}
function documentRow(document,result=null){
  const row=window.document.createElement('article');row.className='document-entry';
  const badge=window.document.createElement('div');badge.className='file-badge';badge.textContent=document.original_name?.split('.').pop().toUpperCase().slice(0,5)||'资料';
  const content=window.document.createElement('div');
  const title=window.document.createElement('button');title.className='document-title';title.textContent=document.title;title.addEventListener('click',()=>showDocument(document.id));
  const meta=window.document.createElement('p');meta.className='document-description';
  const category = categories[document.category] || '未分类';
  meta.textContent = result
    ? `${category} · ${locationLabel(result.locator)}`
    : `${category} · ${formatSize(document.size_bytes)} · ${dates.format(new Date(document.created_at))} · ${document.char_count.toLocaleString()} 字`;
  content.append(title,meta);
  if(result){const excerpt=window.document.createElement('p');excerpt.className='document-excerpt';excerpt.textContent=result.text;content.append(excerpt);}
  else if(document.message){const note=window.document.createElement('p');note.className='document-description';note.textContent=document.message;content.append(note);}
  const status=window.document.createElement('span');status.className='document-state';status.classList.toggle('attention',document.state!=='ready');status.textContent=result?'来源片段':!document.enabled?'已暂停检索':states[document.state]||document.state;
  const marker = window.document.createElement('div');
  marker.className = 'document-marker';
  marker.append(badge);
  if (managingCategories && !result) {
    const checkbox = window.document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = document.id;
    checkbox.checked = selectedDocuments.has(document.id);
    checkbox.setAttribute('aria-label', `选择 ${document.original_name}`);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) selectedDocuments.add(document.id);
      else selectedDocuments.delete(document.id);
      updateCategoryControls();
    });
    marker.append(checkbox);
  }
  row.append(marker,content,status);return row;
}

function setCategoryOptions(select, firstOption) {
  const previous = select.value;
  select.replaceChildren();
  if (firstOption) select.add(new Option(firstOption, ''));
  for (const [key, label] of Object.entries(categories)) {
    select.add(new Option(label, key));
  }
  if (Array.from(select.options).some(option => option.value === previous)) {
    select.value = previous;
  }
}

function updateCategoryControls() {
  const button = $('#manage-categories');
  button.hidden = !visibleDocuments.length;
  button.textContent = managingCategories ? '完成选择' : '批量分类';
  button.setAttribute('aria-pressed', String(managingCategories));
  button.disabled = savingCategories;
  $('#category-form').hidden = !managingCategories;
  const selectAll = $('#select-visible-documents');
  selectAll.checked = visibleDocuments.length > 0 && selectedDocuments.size === visibleDocuments.length;
  selectAll.indeterminate = selectedDocuments.size > 0 && !selectAll.checked;
  selectAll.disabled = savingCategories;
  $('#selected-document-count').textContent = `已选 ${selectedDocuments.size} 份`;
  $('#apply-category').disabled = savingCategories || !selectedDocuments.size || !targetCategory.value;
  targetCategory.disabled = savingCategories;
  for (const checkbox of document.querySelectorAll('.document-marker input')) {
    checkbox.checked = selectedDocuments.has(checkbox.value);
    checkbox.disabled = savingCategories;
  }
}

function renderDocumentList() {
  const list = $('#document-list');
  list.replaceChildren(...visibleDocuments.map(item => documentRow(item)));
  if (!visibleDocuments.length) {
    list.append(categoryFilter.value
      ? empty('这个分类还没有资料', '导入时选择该分类，或将已有资料归入此类。')
      : empty('从一份重要资料开始', '导入简历、学习笔记或截图，之后可以通过关键词找回内容。'));
  }
  updateCategoryControls();
}
async function loadLibrary(){
  const request = ++libraryRequest;
  const query = $('#library-query').value.trim();
  const category = categoryFilter.value;
  try{
    $('#library-error').hidden=true;
    const data = await api('/api/library/documents');
    if (request !== libraryRequest) return;
    if (!Object.keys(categories).length && data.categories) {
      categories = data.categories;
      setCategoryOptions(categoryFilter, '全部分类');
      setCategoryOptions(uploadCategory);
      setCategoryOptions(targetCategory, '选择目标分类');
    }
    const matchingDocuments = category
      ? data.documents.filter(item => item.category === category)
      : data.documents;
    $('#document-count').textContent = matchingDocuments.length;
    const list = $('#document-list');
    if(query){
      const params = new URLSearchParams({q: query});
      if (category) params.set('category', category);
      const results = await api(`/api/library/search?${params}`);
      if (request !== libraryRequest) return;
      visibleDocuments = [];
      selectedDocuments.clear();
      managingCategories = false;
      list.replaceChildren();$('#search-label').textContent=`“${query}” · ${results.results.length} 条匹配片段，最多展示 20 条`;$('#clear-search').hidden=false;
      for(const result of results.results){const document=matchingDocuments.find(item=>item.id===result.document_id);if(document)list.append(documentRow(document,result));}
      if(!results.results.length)list.append(empty('还没有找到相关文字','换一个关键词，或检查资料是否已提取文字并开启检索。'));
      updateCategoryControls();
    }else{
      visibleDocuments = matchingDocuments;
      const visibleIds = new Set(visibleDocuments.map(item => item.id));
      for (const id of selectedDocuments) {
        if (!visibleIds.has(id)) selectedDocuments.delete(id);
      }
      if (!visibleDocuments.length) managingCategories = false;
      $('#search-label').textContent = category ? categories[category] : '原件和提取文字均保存在这台电脑。';
      $('#clear-search').hidden = true;
      renderDocumentList();
    }
  }catch(error){
    if (request !== libraryRequest) return;
    $('#library-error').textContent=error.message;$('#library-error').hidden=false;
  }
}
async function showDocument(id){
  try{
    const data=await api(`/api/library/documents/${id}`);currentDocument=data;
    $('#document-heading').textContent=data.title;
    $('#document-format').textContent=`${categories[data.category] || '未分类'} · ${data.original_name}`;
    $('#document-message').textContent=data.message||'文字已提取，引用保留原始位置。';
    $('#download-document').href=`/api/library/documents/${id}/original`;
    $('#document-enabled').checked=Boolean(data.enabled);
    $('#document-enabled').disabled=data.state==='importing';$('#edit-transcript').disabled=data.state==='importing';
    $('#transcript-form').hidden=true;$('#document-content').hidden=false;
    const image=$('#document-image');image.hidden=!data.mime_type.startsWith('image/')||data.state==='failed';if(!image.hidden)image.src=`/api/library/documents/${id}/preview?v=${data.revision}`;else image.removeAttribute('src');
    const content=$('#document-content');content.replaceChildren();
    for(const chunk of data.chunks){const entry=document.createElement('section');entry.className='document-chunk';const label=document.createElement('h3');label.textContent=locationLabel(chunk.locator);const text=document.createElement('p');text.textContent=chunk.text_content;entry.append(label,text);content.append(entry);}
    if(!data.chunks.length)content.append(empty('这份资料还没有可检索文字','可以点击“补充／校正文字”，写下你希望助手查阅的内容。'));
    $('#document-meta').textContent=`版本 ${data.revision} · ${data.char_count.toLocaleString()} 字 · 本地处理`;
    if(!$('#document-dialog').open)$('#document-dialog').showModal();
  }catch(error){notify(error.message,true);}
}
const fileInput = $('#library-files');
const chooseFiles = $('#choose-files');
const uploadButton = $('#upload-button');
const fileQueue = $('#file-queue');
const uploadStatus = $('#upload-status');
let pendingFiles = [];

function renderFileQueue() {
  $('#selected-files').textContent = pendingFiles.length
    ? `待导入 ${pendingFiles.length} 份文件` : '尚未选择文件';
  chooseFiles.querySelector('strong').textContent = pendingFiles.length ? '继续选择文件' : '选择本地文件';
  chooseFiles.disabled = uploading;
  uploadCategory.disabled = uploading;
  uploadButton.disabled = uploading || !pendingFiles.length;
  fileQueue.hidden = !pendingFiles.length;
  fileQueue.replaceChildren();

  pendingFiles.forEach((entry, index) => {
    const item = document.createElement('li');
    const label = document.createElement('span');
    label.textContent = `${entry.file.name}（${formatSize(entry.file.size)}）`;
    if (entry.error) {
      const error = document.createElement('small');
      error.textContent = entry.error;
      label.append(error);
    }
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'text-button';
    remove.textContent = '移除';
    remove.setAttribute('aria-label', `移除 ${entry.file.name}`);
    remove.disabled = uploading;
    remove.addEventListener('click', () => {
      pendingFiles.splice(index, 1);
      renderFileQueue();
      const next = fileQueue.children[Math.min(index, pendingFiles.length - 1)]?.querySelector('button');
      (next || chooseFiles).focus();
    });
    item.append(label, remove);
    fileQueue.append(item);
  });
}

chooseFiles.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  for (const file of fileInput.files) {
    pendingFiles.push({file});
  }
  // A native file picker replaces its FileList each time it opens.
  fileInput.value = '';
  uploadStatus.textContent = '';
  renderFileQueue();
});

$('#upload-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (uploading || !pendingFiles.length) return;
  uploading = true;
  renderFileQueue();
  const batch = pendingFiles;
  const category = uploadCategory.value;
  const failed = [];
  let saved = 0;
  let duplicates = 0;
  try {
    for (const [index, {file}] of batch.entries()) {
      uploadStatus.textContent = `${index + 1}/${batch.length} · 正在导入 ${file.name}…`;
      try {
        if (!file.size || file.size > 20 * 1024 * 1024) {
          throw new Error('请选择 20 MB 以内的非空文件');
        }
        const params = new URLSearchParams({filename: file.name, category});
        const result = await api(`/api/library/documents?${params}`, {
          method: 'POST',
          headers: {'Content-Type': 'application/octet-stream'},
          body: file,
        });
        if (result.duplicate) duplicates++;
        else saved++;
      } catch (error) {
        failed.push({file, error: error.message});
      }
    }
    await loadLibrary();
    const status = [`已导入 ${saved} 份`];
    if (duplicates) status.push(`${duplicates} 份已存在`);
    if (failed.length) status.push(`${failed.length} 份失败，可查看原因后重试`);
    uploadStatus.textContent = status.join('，') + '。';
  } finally {
    pendingFiles = failed;
    uploading = false;
    renderFileQueue();
  }
});
$('#search-form').addEventListener('submit',event=>{event.preventDefault();loadLibrary();});
$('#clear-search').addEventListener('click',()=>{$('#library-query').value='';loadLibrary();});
$('#refresh-library').addEventListener('click',loadLibrary);
categoryFilter.addEventListener('change', () => {
  selectedDocuments.clear();
  updateCategoryControls();
  loadLibrary();
});
$('#manage-categories').addEventListener('click', () => {
  managingCategories = !managingCategories;
  selectedDocuments.clear();
  targetCategory.value = '';
  renderDocumentList();
});
$('#select-visible-documents').addEventListener('change', event => {
  selectedDocuments.clear();
  if (event.target.checked) {
    for (const item of visibleDocuments) selectedDocuments.add(item.id);
  }
  updateCategoryControls();
});
targetCategory.addEventListener('change', updateCategoryControls);
$('#category-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (savingCategories || !selectedDocuments.size || !targetCategory.value) return;
  savingCategories = true;
  updateCategoryControls();
  const category = targetCategory.value;
  try {
    const {count} = await api('/api/library/document-categories', {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({document_ids: [...selectedDocuments], category}),
    });
    selectedDocuments.clear();
    targetCategory.value = '';
    await loadLibrary();
    notify(`已将 ${count} 份资料归入「${categories[category]}」`);
  } catch (error) {
    notify(error.message, true);
  } finally {
    savingCategories = false;
    updateCategoryControls();
  }
});
$('#close-document').addEventListener('click',()=>$('#document-dialog').close());
$('#document-enabled').addEventListener('change',async()=>{
  if(!currentDocument)return;const checkbox=$('#document-enabled');checkbox.disabled=true;
  try{await api(`/api/library/documents/${currentDocument.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:checkbox.checked,revision:currentDocument.revision})});await showDocument(currentDocument.id);await loadLibrary();}
  catch(error){checkbox.checked=!checkbox.checked;notify(error.message,true);}finally{checkbox.disabled=false;}
});
$('#edit-transcript').addEventListener('click',()=>{
  let text='';for(const chunk of currentDocument.chunks){const start=chunk.locator.char_start||0;if(!start){if(text)text+='\n\n';text+=chunk.text_content;}else{text+=chunk.text_content.slice(100);}}
  $('#transcript-text').value=text;$('#transcript-form').hidden=false;$('#document-content').hidden=true;$('#transcript-text').focus();
});
$('#cancel-transcript').addEventListener('click',()=>{$('#transcript-form').hidden=true;$('#document-content').hidden=false;});
$('#transcript-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=$('#save-transcript');button.disabled=true;
  try{await api(`/api/library/documents/${currentDocument.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('#transcript-text').value,revision:currentDocument.revision})});await showDocument(currentDocument.id);await loadLibrary();notify('文字已保存，检索使用新版本');}
  catch(error){notify(error.message,true);}finally{button.disabled=false;}
});
$('#delete-document').addEventListener('click',async()=>{
  if(!currentDocument||!confirm('删除这份资料的本地原件和提取文字？它将停止参与检索。已有备份仍会保留。'))return;
  const button=$('#delete-document');button.disabled=true;
  try{await api(`/api/library/documents/${currentDocument.id}`,{method:'DELETE'});$('#document-dialog').close();currentDocument=null;await loadLibrary();notify('资料原件与提取文字已删除');}
  catch(error){notify(error.message,true);}finally{button.disabled=false;}
});
loadLibrary();

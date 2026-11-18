'use strict';
const $=selector=>document.querySelector(selector);
const states={importing:'正在提取',ready:'可检索',needs_text:'待补充文字',failed:'待处理'};
const dates=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'short',day:'numeric',timeZone:'Asia/Shanghai'});
let currentDocument=null,toastTimer,uploading=false;
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
  meta.textContent=result?locationLabel(result.locator):`${formatSize(document.size_bytes)} · ${dates.format(new Date(document.created_at))} · ${document.char_count.toLocaleString()} 字`;
  content.append(title,meta);
  if(result){const excerpt=window.document.createElement('p');excerpt.className='document-excerpt';excerpt.textContent=result.text;content.append(excerpt);}
  else if(document.message){const note=window.document.createElement('p');note.className='document-description';note.textContent=document.message;content.append(note);}
  const status=window.document.createElement('span');status.className='document-state';status.classList.toggle('attention',document.state!=='ready');status.textContent=result?'来源片段':!document.enabled?'已暂停检索':states[document.state]||document.state;
  row.append(badge,content,status);return row;
}
async function loadLibrary(){
  try{
    $('#library-error').hidden=true;
    const data=await api('/api/library/documents');$('#document-count').textContent=data.documents.length;
    const query=$('#library-query').value.trim();const list=$('#document-list');
    if(query){
      const results=await api(`/api/library/search?q=${encodeURIComponent(query)}`);
      list.replaceChildren();$('#search-label').textContent=`“${query}” · ${results.results.length} 条匹配片段，最多展示 20 条`;$('#clear-search').hidden=false;
      for(const result of results.results){const document=data.documents.find(item=>item.id===result.document_id);if(document)list.append(documentRow(document,result));}
      if(!results.results.length)list.append(empty('还没有找到相关文字','换一个关键词，或检查资料是否已提取文字并开启检索。'));
    }else{
      list.replaceChildren();$('#search-label').textContent='原件和提取文字均保存在这台电脑。';$('#clear-search').hidden=true;
      for(const document of data.documents)list.append(documentRow(document));
      if(!data.documents.length)list.append(empty('从一份重要资料开始','导入简历、学习笔记或截图，之后可以通过关键词找回内容。'));
    }
  }catch(error){$('#library-error').textContent=error.message;$('#library-error').hidden=false;}
}
async function showDocument(id){
  try{
    const data=await api(`/api/library/documents/${id}`);currentDocument=data;
    $('#document-heading').textContent=data.title;$('#document-format').textContent=data.original_name;
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
$('#library-files').addEventListener('change',()=>{$('#selected-files').textContent=[...$('#library-files').files].map(file=>`${file.name}（${formatSize(file.size)}）`).join('、')||'尚未选择文件';});
$('#upload-form').addEventListener('submit',async event=>{
  event.preventDefault();if(uploading)return;uploading=true;$('#upload-button').disabled=true;$('#library-files').disabled=true;
  const files=[...$('#library-files').files];let succeeded=0;
  try{
    for(let i=0;i<files.length;i++){
      const file=files[i];$('#upload-status').textContent=`${i+1}/${files.length} · 正在本地提取 ${file.name}，请保持此页打开…`;
      try{
        if(!file.size||file.size>20*1024*1024)throw new Error('请选择 20 MB 以内的非空文件');
        const result=await api(`/api/library/documents?filename=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
        const detail=await api(`/api/library/documents/${result.id}`);
        succeeded++;notify(result.duplicate?'资料已存在，未重复保存':detail.state==='ready'?'资料已保存并提取文字':'原件已保存，可打开详情补充文字');
        await loadLibrary();
      }catch(error){notify(`${file.name}：${error.message}`,true);}
    }
    $('#upload-status').textContent=`已保存 ${succeeded}/${files.length} 份资料。可在详情中核对或补充提取文字。`;
  }finally{uploading=false;$('#upload-button').disabled=false;$('#library-files').disabled=false;$('#library-files').value='';$('#selected-files').textContent='尚未选择文件';}
});
$('#search-form').addEventListener('submit',event=>{event.preventDefault();loadLibrary();});
$('#clear-search').addEventListener('click',()=>{$('#library-query').value='';loadLibrary();});
$('#refresh-library').addEventListener('click',loadLibrary);
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

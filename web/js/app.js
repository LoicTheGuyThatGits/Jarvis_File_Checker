const conversation = document.querySelector('#conversation');
const form = document.querySelector('#composer');
const input = document.querySelector('#message');
const thinking = document.querySelector('#thinking');
const welcome = document.querySelector('#welcome');
const chatsKey = 'jarvis-chats-v1';
const currentChatKey = 'jarvis-current-chat-v1';
const legacyHistoryKey = 'jarvis-history-v1';
let computerMode = false;
let autopilotMode = false;
let activeAutonomousId = null;
let autonomousRunning = false;
let screenFeedTimer = null;
let screenFeedBusy = false;
let latestScreen = null;
let latestScreenAt = 0;
let activePromptController = null;
let activePromptId = null;
const sendButton = document.querySelector('#composer .send-button');
function setPromptRunning(running) {
  sendButton.textContent=running?'Stop':'↑';
  sendButton.setAttribute('aria-label',running?'Stop current prompt':'Send message');
  sendButton.title=running?'Stop current prompt':'Send message';
  sendButton.classList.toggle('stop-mode',running);
}
function stopCurrentPrompt() {
  if(!activePromptController)return;
  window.dispatchEvent(new CustomEvent('jarvis:stop'));
  if(activeAutonomousId){
    fetch('/api/computer/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:activeAutonomousId})}).catch(()=>{});
    activePromptController.abort();
  }else if(!computerMode&&activePromptId){
    fetch('/api/chat/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:activePromptId})}).then(response=>{if(!response.ok)throw new Error('Could not stop the provider request')}).catch(()=>activePromptController?.abort());
  }else{
    activePromptController.abort();
  }
}
function newChatRecord(title='New chat', messages=[]) { return {id: crypto.randomUUID(), title, messages}; }
function loadChats() {
  try {
    const saved = JSON.parse(localStorage.getItem(chatsKey) || 'null');
    if (Array.isArray(saved) && saved.length) return saved.filter(c => c && typeof c.id==='string' && Array.isArray(c.messages));
  } catch {}
  try {
    const old = JSON.parse(localStorage.getItem(legacyHistoryKey) || '[]').filter(m => ['user','assistant'].includes(m.role) && typeof m.content==='string');
    if (old.length) {
      const migrated = newChatRecord('Previous chat', old.slice(-100));
      localStorage.setItem(chatsKey, JSON.stringify([migrated]));
      localStorage.removeItem(legacyHistoryKey);
      return [migrated];
    }
  } catch {}
  return [newChatRecord()];
}
let chats = loadChats();
let currentChatId = localStorage.getItem(currentChatKey);
if (!chats.some(c => c.id === currentChatId)) currentChatId = chats[0].id;
let history = chats.find(c => c.id === currentChatId).messages;
function activeChat() { return chats.find(c => c.id === currentChatId); }
function saveHistory() {
  const chat = activeChat();
  chat.messages = history.slice(-100);
  const firstUser = chat.messages.find(m => m.role==='user');
  if (firstUser && (chat.title==='New chat' || chat.title==='Previous chat')) chat.title = firstUser.content.slice(0,36) + (firstUser.content.length>36?'…':'');
  localStorage.setItem(chatsKey, JSON.stringify(chats));
  localStorage.setItem(currentChatKey, currentChatId);
  renderChatList();
}
let chatFilter='';
function chatSnippet(chat,query) {
  for(const message of chat.messages){
    const at=message.content.toLowerCase().indexOf(query);
    if(at>=0){const start=Math.max(0,at-18);return (start>0?'…':'')+message.content.slice(start,at+query.length+34).replace(/\s+/g,' ').trim()+'…'}
  }
  return '';
}
function renderChatList() {
  const list=document.querySelector('#chat-list');
  if(!list)return;
  list.replaceChildren();
  const query=chatFilter.trim().toLowerCase();
  let shown=0;
  for(const chat of [...chats].reverse()) {
    const titleHit=!query||(chat.title||'').toLowerCase().includes(query);
    const snippet=query&&!titleHit?chatSnippet(chat,query):'';
    if(query&&!titleHit&&!snippet)continue;
    shown++;
    const item=document.createElement('button');item.type='button';item.className='chat-item'+(chat.id===currentChatId?' active':'');
    const title=document.createElement('span');title.className='chat-title';title.textContent=chat.title||'New chat';item.append(title);
    if(snippet){const small=document.createElement('small');small.className='chat-snippet';small.textContent=snippet;item.append(small)}
    item.title=chat.title||'New chat';
    item.addEventListener('click',()=>{currentChatId=chat.id;history=chat.messages;localStorage.setItem(currentChatKey,currentChatId);renderConversation();renderChatList();input.focus()});
    list.append(item);
  }
  if(query&&!shown){const none=document.createElement('div');none.className='chat-empty';none.textContent='No chats match “'+chatFilter.trim()+'”';list.append(none)}
}
function renderConversation() {
  conversation.replaceChildren();
  history=activeChat().messages;
  welcome.classList.toggle('hidden',history.length>0);
  for(const item of history.slice(-100)) addMessage(item.role,item.content);
  if(!history.length) welcome.classList.remove('hidden');
}
function startNewChat() {
  const chat=newChatRecord();chats.push(chat);currentChatId=chat.id;history=chat.messages;
  localStorage.setItem(chatsKey,JSON.stringify(chats));localStorage.setItem(currentChatKey,currentChatId);
  renderConversation();renderChatList();input.focus();
}
function clearCurrentChat() {
  if(!window.confirm('Clear all messages in this chat? This cannot be undone.'))return;
  history=[];const chat=activeChat();chat.messages=[];chat.title='New chat';
  localStorage.setItem(chatsKey,JSON.stringify(chats));localStorage.setItem(currentChatKey,currentChatId);
  renderConversation();renderChatList();input.focus();
}
function deleteCurrentChat() {
  const chat=activeChat();
  if(!window.confirm(`Delete “${chat.title||'New chat'}” and all its saved messages? This cannot be undone.`))return;
  const oldIndex=chats.findIndex(item=>item.id===currentChatId);
  chats=chats.filter(item=>item.id!==currentChatId);
  if(!chats.length)chats=[newChatRecord()];
  currentChatId=chats[Math.max(0,oldIndex-1)].id;history=activeChat().messages;
  localStorage.setItem(chatsKey,JSON.stringify(chats));localStorage.setItem(currentChatKey,currentChatId);
  renderConversation();renderChatList();input.focus();
}
const CODE_EXTENSIONS={python:'py',py:'py',javascript:'js',js:'js',node:'js',typescript:'ts',ts:'ts',jsx:'jsx',tsx:'tsx',html:'html',css:'css',scss:'scss',json:'json',bash:'sh',sh:'sh',shell:'sh',powershell:'ps1',ps1:'ps1',bat:'bat',batch:'bat',sql:'sql',c:'c',cpp:'cpp','c++':'cpp',csharp:'cs','c#':'cs',cs:'cs',java:'java',kotlin:'kt',go:'go',rust:'rs',rs:'rs',ruby:'rb',php:'php',swift:'swift',lua:'lua',r:'r',yaml:'yml',yml:'yml',toml:'toml',xml:'xml',markdown:'md',md:'md'};
function appendInline(parent,text){
  text.split(/(`[^`\n]+`)/g).forEach(part=>{
    if(part.length>2&&part.startsWith('`')&&part.endsWith('`')){const c=document.createElement('code');c.className='inline-code';c.textContent=part.slice(1,-1);parent.append(c)}
    else if(part)parent.append(document.createTextNode(part));
  });
}
function parseCodeInfo(info){
  const tokens=info.trim().split(/\s+/).filter(Boolean);
  const fileToken=tokens.map(t=>t.replace(/^(?:file|filename|title|path)=/i,'').replace(/^["']|["']$/g,'')).reverse().find(t=>/^[\w .\/-]+\.[A-Za-z0-9]{1,10}$/.test(t)||/^(Dockerfile|Makefile)$/i.test(t));
  return {fileToken,lang:(tokens[0]||'').toLowerCase()};
}
function buildCodeBlock(info,code,ctx){
  const {fileToken,lang}=parseCodeInfo(info);
  const block=document.createElement('div');block.className='code-block';
  const head=document.createElement('div');head.className='code-block-head';
  const label=document.createElement('span');label.textContent=fileToken||lang||'code';
  const tools=document.createElement('span');tools.className='code-block-tools';
  const copy=document.createElement('button');copy.type='button';copy.textContent='Copy';
  copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(code);copy.textContent='Copied'}catch{copy.textContent='Press Ctrl+C'}setTimeout(()=>copy.textContent='Copy',1400)});
  const save=document.createElement('button');save.type='button';save.textContent='Download';
  save.addEventListener('click',()=>{
    const name=fileToken?fileToken.split('/').pop():`code.${CODE_EXTENSIONS[lang]||'txt'}`;
    const url=URL.createObjectURL(new Blob([code],{type:'text/plain;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  tools.append(copy,save);head.append(label,tools);
  const pre=document.createElement('pre');const codeEl=document.createElement('code');codeEl.textContent=code;pre.append(codeEl);
  block.append(head,pre);
  if(window.JarvisCode)try{window.JarvisCode.enhance(block,{lang,file:fileToken||'',code,complete:!ctx||ctx.complete,siblings:()=>(ctx&&ctx.all)||[]})}catch(e){console.warn('code block',e)}
  return block;
}
function renderBubble(bubble,text){
  bubble.textContent='';
  if(!text.includes('`')){bubble.textContent=text;return}
  const fence=/```([^\n`]*)\n([\s\S]*?)(?:```|$)/g;let last=0,m;
  const addText=chunk=>{chunk=chunk.replace(/^\n/,'').replace(/\n$/,'');if(!chunk)return;const span=document.createElement('span');appendInline(span,chunk);bubble.append(span)};
  const all=[];let n;const scan=/```([^\n`]*)\n([\s\S]*?)(?:```|$)/g;
  while((n=scan.exec(text))){const pi=parseCodeInfo(n[1]);all.push({name:pi.fileToken||'',lang:pi.lang,code:n[2].replace(/\n$/,'')});if(n[0]==='')scan.lastIndex++}
  while((m=fence.exec(text))){addText(text.slice(last,m.index));bubble.append(buildCodeBlock(m[1],m[2].replace(/\n$/,''),{complete:m[0].endsWith('```')&&m[0].length>=3+m[1].length+1+3,all}));last=fence.lastIndex;if(m[0]==='')fence.lastIndex++}
  addText(text.slice(last));
}
function addMessage(role, text) {
  welcome.classList.add('hidden');
  const row = document.createElement('div'); row.className = `message-row ${role}`;
  if (role === 'assistant') { const avatar = document.createElement('div'); avatar.className='avatar'; avatar.textContent='J'; row.append(avatar); }
  const bubble = document.createElement('div'); bubble.className='bubble'; if(role==='assistant')renderBubble(bubble,text); else bubble.textContent=text; row.append(bubble); conversation.append(row); scrollDown(); return row;
}
function addDownloadCard(dl, after=null) {
  if(!dl||!dl.url)return null;
  const card=document.createElement('section');card.className='file-results download-card';
  const heading=document.createElement('div');heading.className='file-results-heading';heading.textContent='EDITED DOCUMENT';card.append(heading);
  const name=document.createElement('strong');name.className='download-name';name.textContent=dl.name;card.append(name);
  const row=document.createElement('div');row.className='download-actions';
  const link=document.createElement('a');link.className='file-reveal';link.href=dl.url;link.download=dl.name;link.textContent='Download';row.append(link);
  if(dl.path){const show=document.createElement('button');show.type='button';show.className='file-reveal';show.textContent='Show in folder';
    show.addEventListener('click',async()=>{show.disabled=true;try{const r=await fetch('/api/files/reveal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:dl.path})});const d=await r.json();show.textContent=r.ok?'Opened':(d.error||'Could not open')}catch(e){show.textContent='Could not open'}setTimeout(()=>{show.disabled=false;show.textContent='Show in folder'},2500)});row.append(show)}
  card.append(row);
  if(after)after.after(card);else conversation.append(card);
  if(typeof scrollDown==='function')scrollDown();
  return card;
}
window.addDownloadCard=addDownloadCard;
function addFileResults(files, truncated=false, noteText='', headingText='') {
  if(!Array.isArray(files)||!files.length)return;
  const section=document.createElement('section');section.className='file-results';
  const heading=document.createElement('div');heading.className='file-results-heading';heading.textContent=headingText||'FILES FOUND ON THIS PC';section.append(heading);
  const list=document.createElement('ul');
  for(const file of files){
    const item=document.createElement('li');
    const name=document.createElement('strong');name.textContent=file.name||'File';
    const path=document.createElement('code');path.textContent=file.path||'';
    item.append(name,path);
    if(file.detail){const d=document.createElement('span');d.className='file-detail';d.textContent=file.detail;item.append(d)}
    const show=document.createElement('button');show.type='button';show.className='file-reveal';show.textContent='Show in folder';
    show.addEventListener('click',async()=>{show.disabled=true;try{const r=await fetch('/api/files/reveal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:file.path})});const d=await r.json();show.textContent=r.ok?'Opened':(d.error||'Could not open')}catch(e){show.textContent='Could not open'}setTimeout(()=>{show.disabled=false;show.textContent='Show in folder'},2500)});
    item.append(show);list.append(item);
  }
  section.append(list);
  if(truncated){const note=document.createElement('p');note.className='file-results-note';note.textContent=noteText||'Search stopped at its result or time limit. Try a more specific filename to narrow the results.';section.append(note)}
  conversation.append(section);scrollDown();
}
function addScreenPreview(base64) {
  const row=document.createElement('div');row.className='screen-preview-row';
  const image=document.createElement('img');image.className='screen-preview';image.alt='Screenshot shared with Jarvis for computer control';image.src=`data:image/jpeg;base64,${base64}`;
  row.append(image);conversation.append(row);scrollDown();
}
function followStream() { if(window.innerHeight+window.scrollY>=document.body.scrollHeight-160)window.scrollTo(0,document.body.scrollHeight); }
async function readReplyStream(response,onDelta) {
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',final=null;
  const handle=line=>{
    if(!line.trim())return;
    let event;try{event=JSON.parse(line)}catch{return}
    if(event.type==='delta'&&typeof event.text==='string')onDelta(event.text);
    else if(event.type==='status'&&typeof event.text==='string'){const label=thinking.querySelector('i');if(label)label.textContent=event.text}
    else if(event.type==='final')final=event;
    else if(event.type==='error')throw new Error(event.error||'Something went wrong.');
  };
  while(true){
    const {value,done}=await reader.read();
    if(done)break;
    buffer+=decoder.decode(value,{stream:true});
    let newline;while((newline=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);handle(line)}
  }
  buffer+=decoder.decode();handle(buffer);
  if(!final)throw new Error('The reply was cut off before it finished.');
  return final;
}
function scrollDown() { window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'}); }
function actionText(action) {
  if (action.type === 'computer_step') {
    const step=action.computer_action;
    const labels={click:'Click',double_click:'Double-click',right_click:'Right-click',type_text:'Type text',press_key:'Press a key',hotkey:'Press shortcut',scroll:'Scroll',wait:'Wait briefly',focus_window:'Bring to the front',window_state:'Change the window size of',open_app:'Open the app',open_url:'Open the web page',open_folder:'Open the folder',list_folder:'Look inside the folder',read_file:'Read the file',write_file:'Write the file'};
    const detail=step.type==='hotkey'?step.keys.join('+'):step.type==='press_key'?step.key:step.type==='scroll'?`${step.amount} notches`:'';
    return ['focus_window','window_state','open_app','open_url','open_folder','list_folder','read_file','write_file'].includes(step.type)?`${labels[step.type]} ${step.target||''}${step.state?` (${step.state})`:''}`:`${labels[step.type]||'Computer action'}${detail?` (${detail})`:''} on ${step.target||'the screen'}`;
  }
  if (action.type === 'routine') return `Run your “${action.name}” routine (${action.steps.length} step${action.steps.length===1?'':'s'})`;
  if (action.type === 'mcp_call') return `Let ${action.server} run its “${action.tool}” tool with:`;
  if (action.type === 'open_app') return `Open ${action.name}`;
  if (action.type === 'open_url') return `Open website: ${action.url}`;
  if (action.type === 'generate_image') return `Generate image: ${action.prompt}`;
  if (action.type === 'save_code') {const n=(action.files||[]).length;return `Review and save ${n===1?action.files[0].filename:n+' files'} to the Jarvis workspace${action.folder?` (folder: ${action.folder})`:''}`}
  return 'Run this PowerShell command';
}
function showAction(action) {
  const card=document.createElement('section'); card.className='action-card';
  const label=document.createElement('div'); label.className='action-label'; label.textContent='Approval required'; card.append(label);
  const desc=document.createElement('div'); desc.className='action-description'; desc.textContent=actionText(action);
  if(action.type==='run_command'){const code=document.createElement('code');code.textContent=action.command;desc.append(code)}
  if(action.type==='mcp_call'){const code=document.createElement('code');code.textContent=Object.keys(action.arguments||{}).length?Object.entries(action.arguments).map(([k,v])=>k+': '+(typeof v==='string'?v:JSON.stringify(v))).join('\n'):'(nothing)';desc.append(code)}
  if(action.type==='routine'){const list=document.createElement('ol');list.className='routine-steps';for(const step of action.steps){const li=document.createElement('li');li.textContent=step;list.append(li)}desc.append(list)}
  if(action.type==='save_code'){for(const file of action.files||[]){const details=document.createElement('details');details.className='file-preview';details.open=(action.files||[]).length===1;const summary=document.createElement('summary');summary.textContent=`${file.filename} · ${file.code.split('\n').length} lines`;const code=document.createElement('pre');code.className='code-preview';code.textContent=file.code;details.append(summary,code);desc.append(details)}}
  if(action.type==='computer_step'&&action.computer_action.type==='type_text'){const code=document.createElement('code');code.textContent=action.computer_action.text;desc.append(code)}if(action.type==='computer_step'&&action.computer_action.type==='write_file'){const details=document.createElement('details');details.className='file-preview';const summary=document.createElement('summary');summary.textContent=`New content · ${action.computer_action.text.split('\n').length} lines`;const code=document.createElement('pre');code.className='code-preview';code.textContent=action.computer_action.text;details.append(summary,code);desc.append(details)}
  card.append(desc);
  const buttons=document.createElement('div');buttons.className='action-buttons';
  const approve=document.createElement('button');approve.className='approve';approve.textContent=action.type==='generate_image'?'Generate image':action.type==='computer_step'?'Approve step':action.type==='save_code'?((action.files||[]).length>1?'Save files':'Save file'):action.type==='routine'?'Run routine':'Approve and run';
  const dismiss=document.createElement('button');dismiss.className='dismiss';dismiss.textContent='Dismiss';
  const result=document.createElement('div');result.className='result hidden';
  approve.addEventListener('click',async()=>{
    if(action.type==='run_command'&&!window.confirm(`Approve this command?\n\n${action.command}`))return;
    approve.disabled=true;dismiss.disabled=true;approve.textContent='Working…';
    let succeeded=false;
    let data={};
    try{const res=await fetch('/api/action/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approval_id:action.approval_id})});data=await res.json();if(!res.ok)throw new Error(data.error||'Action failed');result.textContent=data.output||'Action completed.';if(data.image){const image=document.createElement('img');image.className='generated-image';image.alt='Image generated by Jarvis';image.src=`data:image/${data.format||'png'};base64,${data.image}`;result.append(image);const download=document.createElement('a');download.className='image-download';download.href=image.src;download.download='jarvis-image.png';download.textContent='Download image';result.append(download)}succeeded=true}
    catch(e){result.textContent=e.message}
    result.classList.remove('hidden');approve.textContent=succeeded?(action.type==='generate_image'?'Generated':action.type==='computer_step'?'Step approved':action.type==='save_code'?'Saved':'Finished'):'Failed';
    if(succeeded&&action.type==='computer_step'){
      if(data.screenshot)addScreenPreview(data.screenshot);
      if(data.next_action){const status=data.reply||'Ready for the next step.';addMessage('assistant',status);history.push({role:'assistant',content:status});saveHistory();showAction(data.next_action)}
      else if(data.reply){addMessage('assistant',data.reply);history.push({role:'assistant',content:data.reply});saveHistory()}
    }
  });
  dismiss.addEventListener('click',async()=>{dismiss.disabled=true;approve.disabled=true;try{await fetch('/api/action/dismiss',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approval_id:action.approval_id})})}catch{}card.remove()});
  buttons.append(approve,dismiss);card.append(buttons,result);conversation.append(card);scrollDown();
}
async function sendMessage(text) {
  text=text.trim(); if(!text||autonomousRunning||activePromptController)return;
  const controller=new AbortController();activePromptController=controller;activePromptId=crypto.randomUUID();setPromptRunning(true);
  history.push({role:'user',content:text}); saveHistory(); addMessage('user',text); input.value=''; resizeInput(); {const label=thinking.querySelector('i');if(label)label.textContent='Jarvis is thinking'} thinking.classList.remove('hidden'); scrollDown();
  const autonomous=computerMode&&autopilotMode;
  const live={row:null,bubble:null,text:''};
  if(autonomous){activeAutonomousId=crypto.randomUUID();autonomousRunning=true;autopilotStop.disabled=false;autopilotStop.textContent='Stop';autopilotStop.classList.remove('hidden')}
  try {
    const freshScreen=latestScreen&&Date.now()-latestScreenAt<5000?latestScreen:null;
    const payload=computerMode?{task:text,screen:freshScreen,autonomous,task_id:activeAutonomousId,history:history.slice(-16)}: {messages:history.slice(-20),request_id:activePromptId,stream:true,use_documents:window.JARVIS_USE_DOCS===true};
    const response=await fetch(computerMode?'/api/computer/start':'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});
    let data;
    if((response.headers.get('Content-Type')||'').includes('application/x-ndjson')){
      data=await readReplyStream(response,piece=>{
        if(!live.row){thinking.classList.add('hidden');conversation.setAttribute('aria-busy','true');live.row=addMessage('assistant','');live.bubble=live.row.querySelector('.bubble')}
        live.text+=piece;renderBubble(live.bubble,live.text);followStream();window.dispatchEvent(new CustomEvent('jarvis:stream',{detail:{text:live.text}}));
      });
    }else{data=await response.json(); if(!response.ok)throw new Error(data.error||'Something went wrong.')}
    const reply=data.reply||'I do not have a response for that yet.';
    if(live.row&&data.cancelled&&live.text){history.push({role:'assistant',content:live.text})}
    let replyRow=live.row;
    if(live.row&&!data.cancelled)renderBubble(live.bubble,reply);else replyRow=addMessage('assistant',reply);
    history.push({role:'assistant',content:reply});saveHistory();window.dispatchEvent(new CustomEvent('jarvis:reply',{detail:{text:reply,streamed:!!live.row&&!data.cancelled,cancelled:!!data.cancelled,language:data.language||null}}));if(data.files)addFileResults(data.files,data.files_truncated,data.files_note,data.files_heading);if(data.download)addDownloadCard(data.download);if(data.sources)window.dispatchEvent(new CustomEvent('jarvis:sources',{detail:data.sources}));if(data.exchange_id&&replyRow)window.dispatchEvent(new CustomEvent('jarvis:exchange',{detail:{row:replyRow,id:data.exchange_id}}));if(data.decided&&data.decided.length&&replyRow){const why=document.createElement('div');why.className='decided-note';why.textContent='Jarvis chose: '+data.decided.map(d=>String(d).replace(/_/g,' ')).join(', ')+' · say “undo that” if this was wrong';const b=replyRow.querySelector('.bubble');if(b)b.append(why)}if(data.screenshot)addScreenPreview(data.screenshot);if(data.action)showAction(data.action);
  } catch(error) {
    if(error.name==='AbortError'){
      window.dispatchEvent(new CustomEvent('jarvis:stop'));const stopped='Stopped the current prompt, '+(window.JARVIS_ADDRESS||'sir')+'.';if(live.text)history.push({role:'assistant',content:live.text});history.push({role:'assistant',content:stopped});saveHistory();addMessage('assistant',stopped);
    }else addMessage('assistant',`I couldn't complete that: ${error.message}`);
  }
  finally { thinking.classList.add('hidden');conversation.removeAttribute('aria-busy');if(autonomous){autonomousRunning=false;activeAutonomousId=null;autopilotStop.classList.add('hidden');autopilotStop.disabled=false;autopilotStop.textContent='Stop'}if(activePromptController===controller){activePromptController=null;activePromptId=null;setPromptRunning(false)}input.focus(); }
}
form.addEventListener('submit',e=>{e.preventDefault();if(activePromptController){stopCurrentPrompt();return}sendMessage(input.value)});
input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit()}});
input.addEventListener('input',resizeInput);
function resizeInput(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px'}
document.querySelectorAll('.suggestion').forEach(button=>button.addEventListener('click',()=>sendMessage(button.dataset.prompt)));
document.querySelector('#new-chat').addEventListener('click',startNewChat);
document.querySelector('#clear-chat').addEventListener('click',clearCurrentChat);
document.querySelector('#delete-chat').addEventListener('click',deleteCurrentChat);
const computerButton=document.querySelector('#computer-mode');
const liveScreen=document.querySelector('#live-screen');
const liveScreenImage=document.querySelector('#live-screen-image');
const screenFeedStatus=document.querySelector('#screen-feed-status');
const autopilotButton=document.querySelector('#autopilot-mode');
const autopilotStop=document.querySelector('#autopilot-stop');
function setComputerMode(enabled){
  computerMode=enabled;computerButton.setAttribute('aria-pressed',String(computerMode));computerButton.textContent=computerMode?'▣ Computer on':'▣ Computer off';
  document.querySelector('#computer-note').classList.toggle('hidden',!computerMode);liveScreen.classList.toggle('hidden',!computerMode);autopilotButton.classList.toggle('hidden',!computerMode);
  input.placeholder=computerMode?'Describe what you want Jarvis to do on screen…':'Message Jarvis…';
  if(computerMode){updateLiveScreen();screenFeedTimer=setInterval(updateLiveScreen,1600)}
  else{clearInterval(screenFeedTimer);screenFeedTimer=null;latestScreen=null;latestScreenAt=0;liveScreenImage.removeAttribute('src');screenFeedStatus.textContent='Off';setAutopilotMode(false)}
}
async function updateLiveScreen(){
  if(!computerMode||screenFeedBusy)return;
  screenFeedBusy=true;
  try{
    const response=await fetch('/api/screenshot',{cache:'no-store'});const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Screen capture failed');
    latestScreen=data;latestScreenAt=Date.now();liveScreenImage.src=`data:image/jpeg;base64,${data.data}`;
    screenFeedStatus.textContent=`Updated ${new Date().toLocaleTimeString()}`;
  }catch(error){latestScreen=null;screenFeedStatus.textContent=error.message}
  finally{screenFeedBusy=false}
}
computerButton.addEventListener('click',()=>{
  setComputerMode(!computerMode);
});
function setAutopilotMode(enabled){
  autopilotMode=enabled;autopilotButton.setAttribute('aria-pressed',String(enabled));autopilotButton.textContent=enabled?'Autopilot on':'Autopilot off';
  document.querySelector('#computer-note').textContent=enabled
    ?'Autopilot will run up to 30 computer actions without asking at each step. Stay nearby. Stop with Ctrl+Shift+F10 or the Stop button. Frames sent for analysis may incur API charges.'
    :'The preview stays on this PC. Frames are sent to your AI provider when a task is analyzed and as it runs; API charges may apply. Actions normally need your approval.';
}
autopilotButton.addEventListener('click',()=>setAutopilotMode(!autopilotMode));
autopilotStop.addEventListener('click',async()=>{
  if(!activeAutonomousId)return;
  autopilotStop.disabled=true;autopilotStop.textContent='Stopping…';
  try{const response=await fetch('/api/computer/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:activeAutonomousId})});const data=await response.json();if(!response.ok)throw new Error(data.error||'Stop request failed');autopilotStop.textContent='Stop requested';activePromptController?.abort()}
  catch(error){autopilotStop.disabled=false;autopilotStop.textContent='Try stop again';screenFeedStatus.textContent=error.message}
});
renderConversation();
renderChatList();

const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
const mic=document.querySelector('#mic');
const voiceHint=document.querySelector('#voice-hint');
if(!SpeechRecognition){mic.disabled=true;mic.title='Speech recognition is not supported in this browser';voiceHint.textContent='Type a message';}
else {
  const recognition=new SpeechRecognition();recognition.lang=window.JARVIS_RECOGNITION_LANG||navigator.language||'en-US';window.addEventListener('jarvis:language',e=>{if(e.detail&&e.detail.recognition)recognition.lang=e.detail.recognition});recognition.interimResults=true;recognition.continuous=false;let finalText='';
  mic.addEventListener('click',()=>{if(mic.classList.contains('recording')){recognition.stop();return}finalText='';try{recognition.start()}catch{}});
  recognition.onstart=()=>{mic.classList.add('recording');voiceHint.textContent='Listening… press again to stop'};
  recognition.onresult=e=>{let interim='';for(let i=e.resultIndex;i<e.results.length;i++){if(e.results[i].isFinal)finalText+=e.results[i][0].transcript;else interim+=e.results[i][0].transcript}input.value=(finalText+interim).trim();resizeInput()};
  recognition.onerror=()=>{voiceHint.textContent='Microphone unavailable'};
  recognition.onend=()=>{mic.classList.remove('recording');voiceHint.textContent='Enter to send';if(finalText.trim())sendMessage(finalText)};
}
/* the status label (model and provider) is managed by features.js */

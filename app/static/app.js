'use strict';
const $ = (id) => document.getElementById(id);
const state = {projectId:null, conversationId:null, modeOverride:null, mode:'explore', provider:'demo',
  bootstrap:null, docs:[], conversations:[], selected:new Set(), targetDoc:'', editingDoc:null,
  widgetValues:{}, busy:false, contextSerial:0};
const MODE_TEXT = {
  explore:['Explore together','Keep an open conversation and explore a direction.'],
  draft:['Shape a new chapter','Set voice, perspective, and length before generating prose.'],
  continue:['Pick up the thread','Select an existing chapter to preserve its voice and events.'],
  character:['Develop a character','Explore motives, relationships, and dialogue.'],
  world:['Build your world','Deepen politics, culture, history, and fictional rules.'],
  research:['Investigate the question','Distinguish known facts from inference and invention. No live web search is connected.'],
  model:['Choose a model','Switching is local. Credentials stay on the server and are never shown here.'],
  workspace:['Run a command','Commands run locally. No model is called and nothing is sent to an AI service.'],
  project:['Manage projects','This runs locally. No model is called and nothing is sent to an AI service.'],
};
const TITLES = {workspace:'Run',model:'Model',project:'Project',explore:'Explore',draft:'Draft chapter',continue:'Continue',character:'Character',world:'Worldbuilding',research:'Research'};
const EXAMPLE_MODES = ['draft','continue','character','world','research','explore'];
function inferMode(text) {
  const p = text.toLowerCase().trim();
  if (/\b(resume|continue|pick up|carry on|finish|next scene|where we left off)\b/.test(p)) return 'continue';
  if (/\b(new chapter|start (a |the )?chapter|write chapter|draft (a |the )?chapter|chapter [0-9]+)\b/.test(p)) return 'draft';
  if (/\b(research|sources?|historical(ly)?|fact.check|verify|evidence|references?|accurate|scholarship)\b/.test(p)) return 'research';
  if (/\b(character|personality|motivation|arc|protagonist|antagonist|relationship|dialogue|backstory)\b/.test(p)) return 'character';
  if (/\b(world.?build|kingdom|faction|religion|culture|politics|magic system|geography|empire|institution|society|tribe)\b/.test(p)) return 'world';
  return 'explore';
}
async function api(path, options={}) {
  const response=await fetch(path, {headers:{'Content-Type':'application/json'},...options});
  const result=await response.json().catch(()=>({}));
  if (!response.ok) {
    const detail=result.detail;
    const message=typeof detail==='string' ? detail : detail?.error || `Request failed (${response.status})`;
    const error=new Error(message);error.detail=detail;throw error;
  }
  return result;
}
function setBusy(on){state.busy=on;const b=$('sendBtn');if(on)b.setAttribute('aria-busy','true');else b.removeAttribute('aria-busy')}
function option(el,value,label) {const o=document.createElement('option');o.value=value;o.textContent=label??value;el.append(o)}
function clear(node) {node.replaceChildren()}
function toast(message) {const el=$('toast');el.textContent=message;el.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.hidden=true,3700)}
const PROJECT_VERBS = {new:'new',create:'new',add:'new',switch:'switch',open:'switch',use:'switch',
  rename:'rename',delete:'delete',remove:'delete',list:'list',ls:'list'};
const PROJECT_LABELS = {new:'Create project',switch:'Switch project',rename:'Rename project',
  delete:'Delete project',list:'List projects',help:'Project',unknown:'Project'};
// Project management is parsed locally and never sent to a model.
function parseProjectCommand(text) {
  const t = text.trim();
  let m = t.match(/^\/project(?:\s+(\S+))?(?:\s+([\s\S]+))?$/i);
  if (m) {
    if (!m[1]) return {action:'help', arg:''};
    const action = PROJECT_VERBS[m[1].toLowerCase()];
    return action ? {action, arg:(m[2]||'').trim()} : {action:'unknown', arg:m[1]};
  }
  if ((m = t.match(/^(?:new|create)\s+project\s*:?\s+(.+)$/i))) return {action:'new', arg:m[1].trim()};
  if ((m = t.match(/^(?:switch to|switch|open)\s+project\s+(.+)$/i))) return {action:'switch', arg:m[1].trim()};
  if ((m = t.match(/^rename\s+(?:this\s+|the\s+)?project\s+(?:to\s+)?(.+)$/i))) return {action:'rename', arg:m[1].trim()};
  if ((m = t.match(/^delete\s+(?:this\s+|the\s+)?project\s*(.*)$/i))) return {action:'delete', arg:m[1].trim()};
  if (/^(?:list|show)\s+(?:my\s+)?projects$/i.test(t)) return {action:'list', arg:''};
  return null;
}
const PROVIDER_ALIASES = {demo:'demo',none:'demo',arc:'arc',local:'arc',intel:'arc','intel arc':'arc',bedrock:'bedrock',aws:'bedrock'};
const MODEL_NAMES = 'demo|arc|intel arc|local|bedrock|aws';
// Model selection is parsed locally and never sent to a model.
function parseModelCommand(text) {
  const t = text.trim(); let m;
  if ((m = t.match(/^\/model(?:\s+([\s\S]+))?$/i))) {
    const arg = (m[1]||'').trim().replace(/^(?:use|switch|set)\s+/i,'');
    if (!arg) return {action:'help', arg:''};
    if (/^(?:list|ls|status)$/i.test(arg)) return {action:'list', arg:''};
    return {action:'use', arg};
  }
  if ((m = t.match(new RegExp(`^(?:switch|change)\\s+model\\s+(?:to\\s+)?(${MODEL_NAMES})$`,'i')))) return {action:'use', arg:m[1]};
  if ((m = t.match(new RegExp(`^(?:use|switch to)\\s+(?:the\\s+)?(${MODEL_NAMES})(?:\\s+model)?$`,'i')))) return {action:'use', arg:m[1]};
  if (/^(?:list|show)\s+(?:my\s+)?models$/i.test(t)) return {action:'list', arg:''};
  return null;
}
function resolveProvider(arg) {
  const key = arg.trim().toLowerCase();
  if (PROVIDER_ALIASES[key]) return PROVIDER_ALIASES[key];
  const hits = Object.entries(state.bootstrap.providers).filter(([id,p])=>id.includes(key)||p.label.toLowerCase().includes(key));
  return hits.length===1 ? hits[0][0] : null;
}
const WORKSPACE_CMDS = ['new','search','doc','chat','export','help'];
const DOC_TYPES = ['chapter','character','world','research','note'];
// Workspace commands replace the old sidebar. Parsed locally; never sent to a model.
// Any other leading "/word" is refused locally so a typo is never sent to a model as a prompt.
function parseWorkspaceCommand(text) {
  const m = text.trim().match(/^\/([A-Za-z][\w-]*)(?:\s+([\s\S]*))?$/);
  if (!m) return null;
  const name = m[1].toLowerCase(); const rest = (m[2]||'').trim();
  if (name === 'project' || name === 'model') return null;
  if (!WORKSPACE_CMDS.includes(name)) return {cmd:'unknown', action:'unknown', arg:m[1]};
  if (name === 'doc' || name === 'chat') {
    const sub = (rest.split(/\s+/)[0]||'').toLowerCase();
    const arg = rest.slice(sub.length).trim();
    const allowed = name === 'doc' ? ['new','open','list'] : ['open','list'];
    if (!sub) return {cmd:name, action:'help', arg:''};
    return allowed.includes(sub) ? {cmd:name, action:sub, arg} : {cmd:name, action:'unknown', arg:sub};
  }
  return {cmd:name, action:name, arg:rest};
}
function parseCommand(text) {
  const p = parseProjectCommand(text); if (p) return {kind:'project', ...p};
  const m = parseModelCommand(text); if (m) return {kind:'model', ...m};
  const w = parseWorkspaceCommand(text); if (w) return {kind:'workspace', ...w};
  return null;
}
function fillPrompt(text){$('promptInput').value=text;onPrompt();$('promptInput').focus()}
function commandLineButton(parent,text,fillText){
  const b=document.createElement('button');b.type='button';b.className='command-line';b.textContent=text;
  b.onclick=()=>fillPrompt(fillText);parent.append(b);return b;
}
// ---- Slash-command autocomplete (one registry drives suggestions for every command) ----
const COMMANDS = [
  {name:'project', hint:'Create, switch, rename or delete projects', subs:[
    {name:'new', arg:true, hint:'Create a project'}, {name:'switch', arg:true, hint:'Switch to another project'},
    {name:'rename', arg:true, hint:'Rename the current project'}, {name:'delete', arg:true, hint:'Delete the current project (permanent)'},
    {name:'list', arg:false, hint:'Show all projects'}]},
  {name:'model', hint:'Choose the AI model', subs:[]},
  {name:'new', hint:'Start a new thought', subs:[]},
  {name:'doc', hint:'Create, open or list documents', subs:[
    {name:'new', arg:true, hint:'Create a document: /doc new [type] [title]'},
    {name:'open', arg:true, hint:'Open a document to edit'},
    {name:'list', arg:false, hint:'Show all documents'}]},
  {name:'chat', hint:'Open or list conversations', subs:[
    {name:'open', arg:true, hint:'Reopen a conversation'},
    {name:'list', arg:false, hint:'Show all conversations'}]},
  {name:'search', hint:'Search saved documents and conversations', subs:[]},
  {name:'export', hint:'Download this project as JSON', subs:[]},
  {name:'help', hint:'Show all commands', subs:[]},
];
const menu = {items:[], index:0, open:false};
function editDistance(a,b){
  const d=Array.from({length:a.length+1},(_,i)=>[i,...Array(b.length).fill(0)]);
  for(let j=1;j<=b.length;j++)d[0][j]=j;
  for(let i=1;i<=a.length;i++)for(let j=1;j<=b.length;j++)
    d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(a[i-1]===b[j-1]?0:1));
  return d[a.length][b.length];
}
function nearBy(word,names){return word?names.filter(n=>editDistance(n,word)<=2):[]}
function subSuggestions(cmd,arg,word,cmdLabel){
  const m=arg.match(/^(\S*)(\s+([\s\S]*))?$/); const verb=(m[1]||'').toLowerCase(); const tail=m[3];
  if(tail===undefined){
    let hits=cmd.subs.filter(s=>s.name.startsWith(verb)); let note='';
    if(!hits.length&&verb){hits=cmd.subs.filter(s=>nearBy(verb,[s.name]).length);note='Did you mean: '}
    return hits.map(s=>({label:`/${cmd.name} ${s.name}`,insert:`/${cmd.name} ${s.name}${s.arg?' ':''}`,hint:note+s.hint}));
  }
  return null;
}
function commandSuggestions(value){
  if(!value.startsWith('/')||value.includes('\n')||!state.bootstrap)return [];
  const m=value.match(/^\/(\S*)(\s+[\s\S]*)?$/); const head=m[1].toLowerCase(); const rest=m[2];
  if(rest===undefined){
    let hits=COMMANDS.filter(c=>c.name.startsWith(head)); let note='';
    if(!hits.length&&head){hits=COMMANDS.filter(c=>nearBy(head,[c.name]).length);note='Did you mean: '}
    return hits.map(c=>({label:'/'+c.name,insert:`/${c.name} `,hint:note+c.hint}));
  }
  const cmd=COMMANDS.find(c=>c.name===head); if(!cmd)return [];
  const arg=rest.replace(/^\s+/,'');
  if(cmd.name==='project'){
    const subs=subSuggestions(cmd,arg); if(subs)return subs;
    const verb=PROJECT_VERBS[arg.split(/\s+/)[0].toLowerCase()]; const tail=arg.replace(/^\S+\s+/,'');
    if(verb==='switch'){
      return state.bootstrap.projects.filter(p=>p.name.toLowerCase().includes(tail.toLowerCase()))
        .map(p=>({label:p.name,insert:`/project switch ${p.name}`,hint:p.id===state.projectId?'Current project':'Switch to this project'}));
    }
    if(verb==='delete'&&currentProject()){
      return [{label:currentProject().name,insert:`/project delete ${currentProject().name}`,danger:true,
        hint:'Permanent. Removes its documents and conversations. Export first.'}];
    }
    return [];
  }
  if(cmd.name==='doc'||cmd.name==='chat'){
    const subs=subSuggestions(cmd,arg); if(subs)return subs;
    const mm=arg.match(/^(\S+)\s+([\s\S]*)$/); const verb=mm[1].toLowerCase(); const tail=mm[2];
    const q=tail.trim().toLowerCase();
    if(cmd.name==='doc'&&verb==='new'){
      if(/\s/.test(tail))return [];
      return DOC_TYPES.filter(t=>t.startsWith(q)).map(t=>({label:t,insert:`/doc new ${t} `,hint:'Document type, then an optional title'}));
    }
    if(verb==='open'){
      const items=cmd.name==='doc'?state.docs:state.conversations;
      return items.filter(i=>!q||i.title.toLowerCase().includes(q)).slice(0,8)
        .map(i=>({label:i.title,insert:`/${cmd.name} open ${i.title}`,hint:cmd.name==='doc'?`${i.type} · open to edit`:'Reopen this conversation'}));
    }
    return [];
  }
  if(cmd.name==='model'){
    const q=arg.replace(/^(?:use|switch|set)\s+/i,'').toLowerCase(); const out=[];
    for(const [id,p] of Object.entries(state.bootstrap.providers)){
      if(q&&!id.startsWith(q)&&!p.label.toLowerCase().includes(q))continue;
      out.push({label:`/model ${id}`,insert:`/model ${id}`,disabled:!p.ready,
        hint:p.label+(id===state.provider?' (current)':p.ready?'':' (not configured on the server)')});
    }
    if(!q||'list'.startsWith(q))out.push({label:'/model list',insert:'/model list',hint:'Show all models'});
    return out;
  }
  return [];
}
function renderMenu(){
  const box=$('cmdMenu'), input=$('promptInput'); clear(box);
  menu.items.forEach((it,i)=>{
    const row=document.createElement('div'); row.id='cmd-opt-'+i; row.setAttribute('role','option');
    row.className='cmd-item'+(i===menu.index?' active':'')+(it.danger?' danger':'')+(it.disabled?' dim':'');
    row.setAttribute('aria-selected',String(i===menu.index));
    if(it.disabled)row.setAttribute('aria-disabled','true');
    const a=document.createElement('span'); a.className='cmd-label'; a.textContent=it.label;
    const b=document.createElement('span'); b.className='cmd-hint'; b.textContent=it.hint;
    row.append(a,b);
    row.addEventListener('mousedown',e=>{e.preventDefault();acceptSuggestion(i)});
    box.append(row);
  });
  box.hidden=!menu.open;
  input.setAttribute('aria-expanded',String(menu.open));
  if(menu.open)input.setAttribute('aria-activedescendant','cmd-opt-'+menu.index);else input.removeAttribute('aria-activedescendant');
}
function updateMenu(){
  const value=$('promptInput').value;
  let items=commandSuggestions(value);
  if(items.length===1&&items[0].insert===value)items=[];   // already complete
  menu.items=items; menu.open=items.length>0; menu.index=Math.min(menu.index,Math.max(items.length-1,0));
  renderMenu();
}
function closeMenu(){menu.open=false;menu.items=[];renderMenu()}
function acceptSuggestion(i){
  const it=menu.items[i]; if(!it)return;
  const input=$('promptInput'); input.value=it.insert; input.focus();
  input.setSelectionRange(it.insert.length,it.insert.length);
  menu.index=0; onPrompt();
}
function menuKeydown(e){
  if(!menu.open)return false;
  const n=menu.items.length;
  if(e.key==='ArrowDown'){menu.index=(menu.index+1)%n}
  else if(e.key==='ArrowUp'){menu.index=(menu.index-1+n)%n}
  else if(e.key==='Tab'&&!e.shiftKey||(e.key==='Enter'&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey)){acceptSuggestion(menu.index);e.preventDefault();return true}
  else if(e.key==='Escape'){closeMenu();e.preventDefault();e.stopPropagation();return true}
  else return false;
  e.preventDefault();renderMenu();
  $('cmd-opt-'+menu.index)?.scrollIntoView({block:'nearest'});
  return true;
}
function currentProject(){return state.bootstrap?.projects.find(p=>p.id===state.projectId)}
function findProject(query) {
  const q = query.trim().toLowerCase(); const all = state.bootstrap.projects;
  const exact = all.filter(p=>p.name.toLowerCase()===q); if (exact.length===1) return exact[0];
  const part = all.filter(p=>p.name.toLowerCase().includes(q));
  return part.length===1 ? part[0] : null;
}
function modeNow(){const v=$('promptInput').value;const c=parseCommand(v);return c?c.kind:(state.modeOverride || inferMode(v))}
function applyMode(force=false){
  const mode=modeNow();
  if(!force && state.mode===mode && !['project','model','workspace'].includes(mode))return;
  state.mode=mode;state.widgetValues={};
  $('modeStatusText').textContent=(state.modeOverride?'Selected: ':'Suggested: ')+(state.bootstrap?.modes[mode]||TITLES[mode]);
  $('sendBtn').firstChild.textContent=TITLES[mode]+' ';
  for(const btn of document.querySelectorAll('.mode-pills [data-mode]')){
    const on=state.modeOverride===btn.dataset.mode;
    btn.classList.toggle('active',on);
    btn.setAttribute('aria-pressed',String(on));
  }
  const mcmd=mode==='model'?parseModelCommand($('promptInput').value):null;
  const wcmd=mode==='workspace'?parseWorkspaceCommand($('promptInput').value):null;
  const cmd=mode==='project'?parseProjectCommand($('promptInput').value):null;
  if(mcmd){
    $('sendBtn').firstChild.textContent=(mcmd.action==='use'?'Switch model':'Models')+' ';
    $('modeStatusText').textContent='Model command · runs locally, no model call';
    $('contextTitle').textContent=MODE_TEXT.model[0];
    $('contextDescription').textContent=MODE_TEXT.model[1];
    renderModelPane(mcmd);
  }else if(wcmd){
    $('sendBtn').firstChild.textContent=(WS_LABELS[wcmd.cmd+':'+wcmd.action]||WS_LABELS[wcmd.cmd]||'Command')+' ';
    $('modeStatusText').textContent='Command · runs locally, no model call';
    $('contextTitle').textContent=MODE_TEXT.workspace[0];
    $('contextDescription').textContent=MODE_TEXT.workspace[1];
    renderWorkspacePane(wcmd);
  }else if(cmd){
    $('sendBtn').firstChild.textContent=PROJECT_LABELS[cmd.action]+' ';
    $('modeStatusText').textContent='Project command · runs locally, no model';
    $('contextTitle').textContent=MODE_TEXT.project[0];
    $('contextDescription').textContent=MODE_TEXT.project[1];
    renderProjectPane(cmd);
  }else if(Boolean($('promptInput').value.trim() || state.modeOverride)){
    $('contextTitle').textContent=MODE_TEXT[mode][0];
    $('contextDescription').textContent=MODE_TEXT[mode][1];
    renderWidgets();
  }else{
    $('contextTitle').textContent='Context, when needed.';
    $('contextDescription').textContent='Begin typing and the most useful writing controls will appear here.';
    const wrap=$('activeWidgets');clear(wrap);wrap.classList.add('empty-widgets');
    const placeholder=document.createElement('div');placeholder.className='context-placeholder';
    placeholder.innerHTML='<div class="placeholder-icon">⌘</div><strong>Start with an idea</strong><p>Chapter controls, character details, research options, and relevant notes will surface here.</p>';
    wrap.append(placeholder);
  }
}
function renderModelPane(cmd){
  const wrap=$('activeWidgets');wrap.classList.remove('empty-widgets');clear(wrap);
  $('contextRelated').hidden=true;
  const add=(cls,text)=>{const d=document.createElement('div');d.className=cls;d.textContent=text;wrap.append(d);return d};
  const fill=(text)=>{$('promptInput').value=text;onPrompt();$('promptInput').focus()};
  add('widget-label','MODELS');
  for(const [id,p] of Object.entries(state.bootstrap.providers)){
    const b=document.createElement('button');b.type='button';b.className='rail-item project-choice';
    b.classList.toggle('selected',id===state.provider);b.disabled=!p.ready;
    const icon=document.createElement('span');icon.className='symbol';icon.textContent=id===state.provider?'●':'○';
    const name=document.createElement('span');name.className='title';
    name.textContent=p.label+(p.ready?'':' — not configured on the server');
    b.append(icon,name);b.onclick=()=>fill(`/model ${id}`);wrap.append(b);
  }
  add('widget-label','COMMANDS');
  for(const line of ['/model demo','/model arc','/model bedrock','/model list']){
    commandLineButton(wrap,line,line);
  }
  if(cmd.action==='use'&&!resolveProvider(cmd.arg))add('target-note',`No model matches "${cmd.arg}".`);
  add('target-note','Arc and Bedrock are enabled by server environment variables (see README). Nothing secret is entered here.');
}
const WS_LABELS = {new:'New thought', search:'Search', export:'Export', help:'Help',
  'doc:new':'New document', 'doc:open':'Open document', 'doc:list':'Documents', 'doc:help':'Documents',
  'chat:open':'Open conversation', 'chat:list':'Conversations', 'chat:help':'Conversations'};
const WS_USAGE = {
  new:['/new'], export:['/export'], search:['/search <text>'],
  doc:['/doc new [type] [title]','/doc open <title>','/doc list'],
  chat:['/chat open <title>','/chat list'],
  help:['/project …','/model …','/new','/doc …','/chat …','/search <text>','/export','/help'],
  unknown:['/help'],
};
let paneSerial=0, paneTimer;
function searchResultButton(result){
  const b=document.createElement('button');b.type='button';b.className='search-result';
  const title=document.createElement('strong');title.textContent=result.title;
  const meta=document.createElement('small');meta.textContent=result.type.toUpperCase();
  const desc=document.createElement('p');desc.textContent=result.excerpt||'';b.append(title,meta,desc);
  b.onclick=()=>{$('searchModal').hidden=true;
    if(result.type==='conversation')openConversation(result.id);else openDoc(result.id)};
  return b;
}
function paneSearch(q,box){
  clearTimeout(paneTimer);
  if(!q.trim()){box.className='target-note';box.textContent='Type after /search to look through saved documents and conversations.';return}
  const serial=++paneSerial;
  paneTimer=setTimeout(async()=>{
    try{
      const res=await api(`/api/projects/${state.projectId}/search?q=${encodeURIComponent(q.trim().slice(0,200))}`);
      if(serial!==paneSerial||!box.isConnected)return;
      clear(box);const all=[...res.documents,...res.conversations];
      if(!all.length){box.className='target-note';box.textContent='Nothing found in this project yet.';return}
      box.className='';for(const r of all)box.append(searchResultButton(r));
    }catch(e){console.warn(e)}
  },250);
}
function renderWorkspacePane(cmd){
  const wrap=$('activeWidgets');wrap.classList.remove('empty-widgets');clear(wrap);
  $('contextRelated').hidden=true;
  const add=(cls,text)=>{const d=document.createElement('div');d.className=cls;d.textContent=text;wrap.append(d);return d};
  const choice=(icon,label,hint,selected,onclick)=>{
    const b=document.createElement('button');b.type='button';b.className='rail-item project-choice';
    b.classList.toggle('selected',Boolean(selected));
    const i=document.createElement('span');i.className='symbol';i.textContent=icon;
    const n=document.createElement('span');n.className='title';n.textContent=label;
    b.append(i,n);b.title=hint;b.onclick=onclick;wrap.append(b);
  };
  const q=(cmd.arg||'').toLowerCase();
  if(cmd.cmd==='doc'&&cmd.action==='new'){
    add('widget-label','DOCUMENT TYPE');
    for(const t of DOC_TYPES)choice('▤',t,`Create a ${t}`,false,()=>fillPrompt(`/doc new ${t} `));
  }else if(cmd.cmd==='doc'){
    add('widget-label','DOCUMENTS');
    const docs=state.docs.filter(d=>cmd.action!=='open'||!q||d.title.toLowerCase().includes(q));
    if(!docs.length)add('target-note',state.docs.length?'No document matches.':'No documents yet. Use /doc new to create one.');
    for(const d of docs)choice(d.type==='chapter'?'✎':d.type==='character'?'♙':'◈',d.title,`Edit ${d.title}`,false,()=>openDoc(d.id));
  }else if(cmd.cmd==='chat'){
    add('widget-label','CONVERSATIONS');
    const chats=state.conversations.filter(c=>cmd.action!=='open'||!q||c.title.toLowerCase().includes(q));
    if(!chats.length)add('target-note',state.conversations.length?'No conversation matches.':'No conversations yet. Your explorations appear here.');
    for(const c of chats)choice('☰',c.title,`Open ${c.title}`,c.id===state.conversationId,()=>openConversation(c.id));
  }else if(cmd.cmd==='search'){
    add('widget-label','RESULTS');
    const box=document.createElement('div');box.id='paneSearchResults';wrap.append(box);paneSearch(cmd.arg||'',box);
  }
  add('widget-label','COMMANDS');
  for(const line of WS_USAGE[cmd.cmd]||WS_USAGE.help)commandLineButton(wrap,line,line.split(/[<\[…]/)[0]);
}
function renderProjectPane(cmd){
  const wrap=$('activeWidgets');wrap.classList.remove('empty-widgets');clear(wrap);
  $('contextRelated').hidden=true;
  const cur=currentProject();
  const add=(cls,text)=>{const d=document.createElement('div');d.className=cls;d.textContent=text;wrap.append(d);return d};
  const fill=(text)=>{$('promptInput').value=text;onPrompt();$('promptInput').focus()};
  add('widget-label','PROJECTS');
  for(const p of state.bootstrap.projects){
    const b=document.createElement('button');b.type='button';b.className='rail-item project-choice';
    b.classList.toggle('selected',p.id===state.projectId);
    const icon=document.createElement('span');icon.className='symbol';icon.textContent=p.id===state.projectId?'●':'○';
    const name=document.createElement('span');name.className='title';name.textContent=p.name;
    b.append(icon,name);b.title=p.id===state.projectId?'Current project':`Switch to ${p.name}`;
    b.onclick=()=>fill(`/project switch ${p.name}`);wrap.append(b);
  }
  add('widget-label','COMMANDS');
  for(const line of ['/project new <name>','/project switch <name>','/project rename <new name>','/project delete <exact name>','/project list']){
    commandLineButton(wrap,line,line.split('<')[0]);
  }
  if(cmd.action==='delete'){
    const warn=add('context-search-box warn',cur
      ? `Deleting permanently removes "${cur.name}" with ${state.docs.length} document(s) and ${state.conversations.length} conversation(s). Export first if you may need them. To confirm, send: /project delete ${cur.name}`
      : 'No project is selected.');
    warn.setAttribute('role','alert');
  }else if(cmd.action==='unknown'){
    add('target-note',`Unknown project command "${cmd.arg}". Choose one of the commands above.`);
  }
}
function renderWidgets(){
  const wrap=$('activeWidgets');wrap.classList.remove('empty-widgets');clear(wrap);
  const relevant=state.docs.filter(d=>d.type===(state.mode==='continue'||state.mode==='draft'?'chapter':state.mode==='character'?'character':state.mode==='world'?'world':state.mode==='research'?'research':'note'));
  if(['continue','character','world','draft'].includes(state.mode)){
    const row=document.createElement('div');row.className='target-select';
    const label=document.createElement('label');label.className='widget-label';label.htmlFor='targetDocument';
    label.textContent=state.mode==='continue'?'Resume from':state.mode==='draft'?'Chapter context':'Focus document';
    const select=document.createElement('select');select.className='widget-select';select.id='targetDocument';
    option(select,'',state.mode==='draft'?'New chapter (no source)':`Select ${state.mode==='continue'?'a chapter':'a document'}...`);
    for(const d of relevant)option(select,d.id,d.title);
    if(relevant.some(d=>d.id===state.targetDoc))select.value=state.targetDoc;
    else state.targetDoc='';
    select.addEventListener('change',()=>{
      if(state.targetDoc)state.selected.delete(state.targetDoc);
      state.targetDoc=select.value;
      if(state.targetDoc)state.selected.add(state.targetDoc);
      renderRelated(state.lastRelated||[]);
    });
    row.append(label,select);
    const small=document.createElement('div');small.className='target-note';
    small.textContent='When selected, this document is passed as explicit reference context.';row.append(small);wrap.append(row);
  }
  const list=state.bootstrap?.widgets[state.mode]||[];
  for(const widget of list){
    const row=document.createElement('div');row.className='widget';
    const label=document.createElement('label');label.className='widget-label';label.textContent=widget.label;
    const select=document.createElement('select');select.className='widget-select';select.dataset.key=widget.key;
    select.id=`widget-${widget.key}`;label.htmlFor=select.id;
    for(const v of widget.choices)option(select,v,v);
    select.value=state.widgetValues[widget.key]||widget.choices[0];
    state.widgetValues[widget.key]=select.value;
    select.addEventListener('change',()=>state.widgetValues[widget.key]=select.value);
    row.append(label,select);wrap.append(row);
  }
  if(state.mode==='research'){
    const note=document.createElement('div');note.className='context-search-box';
    note.textContent='Archive search works locally. Live internet research and independently verified citations require a separate retrieval connector.';
    wrap.append(note);
  }
}
function renderRelated(list){
  state.lastRelated=list;
  const section=$('contextRelated');const box=$('relatedItems');clear(box);
  const shown=[...list];
  for(const did of state.selected){
    const d=state.docs.find(d=>d.id===did);
    if(d&&!shown.some(x=>x.id===did))shown.unshift(d);
  }
  section.hidden=shown.length===0;
  $('relatedCount').textContent=shown.length;
  for(const item of shown){
    const card=document.createElement('label');card.className='related-card';
    const input=document.createElement('input');input.type='checkbox';input.checked=state.selected.has(item.id);
    input.addEventListener('change',()=>{if(input.checked)state.selected.add(item.id);else state.selected.delete(item.id);
      if(item.id===state.targetDoc&&!input.checked){state.targetDoc='';renderWidgets()}});
    const body=document.createElement('div');const title=document.createElement('strong');title.textContent=item.title;
    const kind=document.createElement('small');kind.textContent=`${item.type.toUpperCase()} · ${input.checked?'Included in prompt':'Include as context'}`;
    body.append(title,kind);card.append(input,body);box.append(card);
  }
}
let debounce;
function onPrompt(){
  applyMode();updateMenu();
  const prompt=$('promptInput').value.trim();
  if(prompt&&parseCommand(prompt)){clearTimeout(debounce);state.contextSerial++;renderRelated([]);return}
  if(prompt){
    clearTimeout(debounce);
    debounce=setTimeout(async()=>{
      const serial=++state.contextSerial;
      try{
        const res=await api(`/api/projects/${state.projectId}/context?q=${encodeURIComponent(prompt.slice(0,600))}`);
        if(serial===state.contextSerial)renderRelated(res.related);
      }catch(e){console.warn(e)}
    },260);
  }else {state.contextSerial++;renderRelated([])}
}
async function loadOverview(){
  const data=await api(`/api/projects/${state.projectId}/overview`);
  state.docs=data.documents;state.conversations=data.conversations;
  renderStatus();refreshPane();renderRelated(state.lastRelated||[]);
}
function refreshPane(){
  const v=$('promptInput').value;
  if((!v.trim()&&!state.modeOverride)||parseCommand(v))applyMode(true);else renderWidgets();
}
function renderStatus(){
  const plural=(n,w)=>n===1?w:w+'s';
  $('docCount').textContent=state.docs.length;$('docWord').textContent=plural(state.docs.length,'document');
  $('chatCount').textContent=state.conversations.length;$('chatWord').textContent=plural(state.conversations.length,'conversation');
}
function resetCompose(){
  state.modeOverride=null;state.mode='explore';state.widgetValues={};
  $('promptInput').value='';applyMode(true);renderRelated([]);closeMenu();
}
function newThread(){
  state.conversationId=null;state.selected.clear();state.targetDoc='';state.lastRelated=[];
  $('conversation').hidden=true;clear($('messages'));$('mainArea').classList.remove('in-chat');
  resetCompose();$('promptInput').focus();renderStatus();
}
function activateThread(title){
  $('conversation').hidden=false;$('mainArea').classList.add('in-chat');
  $('threadTitle').textContent=title;$('messages').scrollTop=$('messages').scrollHeight;
}
function messageNode(m){
  const box=document.createElement('article');box.className='message '+(m.role==='user'?'message-user':'message-ai');
  const label=document.createElement('div');label.className='message-meta';
  label.textContent=m.role==='user'?'YOU':`${(m.provider||'AI').toUpperCase()} · ${(state.bootstrap?.modes[m.mode]||m.mode).toUpperCase()}`;
  const content=document.createElement('div');content.className='message-content';content.textContent=m.content;
  box.append(label,content);
  if(m.role==='assistant'){
    const actions=document.createElement('div');actions.className='message-actions';
    const save=document.createElement('button');save.textContent='＋ Save as note';save.onclick=()=>openDoc(null,{type:'note',title:'Selected passage',body:m.content});actions.append(save);
    const match={draft:['chapter','Save as chapter','New chapter'],character:['character','Save character notes','Character exploration'],world:['world','Save world notes','Worldbuilding exploration'],research:['research','Save research notes','Research notes']};
    const typed=match[m.mode];
    if(typed){const dedicated=document.createElement('button');dedicated.textContent='↳ '+typed[1];
      dedicated.onclick=()=>openDoc(null,{type:typed[0],title:typed[2],body:m.content});actions.append(dedicated);}
    if(state.docs.some(d=>d.type==='chapter')){
      const append=document.createElement('button');append.textContent='↳ Append to chapter';append.onclick=()=>appendChapter(m.content);actions.append(append);
    }
    box.append(actions);
  }
  return box;
}
async function openConversation(cid){
  try{
    const res=await api('/api/conversations/'+cid);
    if(res.conversation.project_id!==state.projectId)throw new Error('Conversation is from another project');
    state.conversationId=cid;activateThread(res.conversation.title);
    clear($('messages'));for(const m of res.messages)$('messages').append(messageNode(m));
    resetCompose();renderStatus();
  }catch(e){toast(e.message)}
}
async function sendPrompt(){
  if(state.busy)return;
  const prompt=$('promptInput').value.trim();if(!prompt){$('promptInput').focus();return}
  const parsed=parseCommand(prompt);
  if(parsed){
    if(parsed.kind==='project')return runProjectCommand(parsed);
    if(parsed.kind==='model')return runModelCommand(parsed);
    return runWorkspaceCommand(parsed);
  }
  setBusy(true);$('sendBtn').disabled=true;$('sendBtn').firstChild.textContent='Thinking ';
  const payload={project_id:state.projectId,prompt,mode:modeNow(),provider:state.provider,
    conversation_id:state.conversationId,context_ids:[...state.selected],options:state.widgetValues};
  try{
    const result=await api('/api/chat',{method:'POST',body:JSON.stringify(payload)});
    state.conversationId=result.conversation_id;
    activateThread(state.conversations.find(x=>x.id===result.conversation_id)?.title||prompt.slice(0,70));
    $('messages').append(messageNode(result.user_message),messageNode(result.assistant_message));
    $('messages').scrollTop=$('messages').scrollHeight;
    resetCompose();await loadOverview();
  }catch(e){
    // The server retains the user's message on upstream failures. Do not clear prompt.
    const cid=e.detail?.conversation_id;
    if(cid){state.conversationId=cid;await openConversation(cid);$('promptInput').value=prompt;onPrompt()}
    toast(e.message);
  }finally{setBusy(false);$('sendBtn').disabled=false;applyMode(true)}
}
function openDoc(id=null,seed=null){
  state.editingDoc=id;
  const d=state.docs.find(d=>d.id===id);
  $('docModalTitle').textContent=d?'Edit document':'New document';
  $('docType').value=d?.type||seed?.type||'note';$('docType').disabled=Boolean(d);
  $('docTitle').value=d?.title||seed?.title||'';$('docBody').value='';
  $('documentModal').hidden=false;
  if(d){
    if(seed && Object.prototype.hasOwnProperty.call(seed,'body')) $('docBody').value=seed.body;
    else api('/api/documents/'+id).then(full=>{$('docBody').value=full.body}).catch(e=>toast(e.message));
  }else $('docBody').value=seed?.body||'';
  setTimeout(()=>$('docTitle').focus(),50);
}
async function saveDoc(){
  const title=$('docTitle').value.trim();if(!title)return toast('A title is required.');
  const body=$('docBody').value;
  try{
    if(state.editingDoc){
      await api('/api/documents/'+state.editingDoc,{method:'PATCH',body:JSON.stringify({title,body})});
    }else{
      await api('/api/documents',{method:'POST',body:JSON.stringify({project_id:state.projectId,type:$('docType').value,title,body})});
    }
    $('documentModal').hidden=true;await loadOverview();toast('Document saved.');
  }catch(e){toast(e.message)}
}
async function appendChapter(content){
  const chapters=state.docs.filter(d=>d.type==='chapter');
  if(!chapters.length)return toast('Create a chapter first.');
  const selected=(state.targetDoc&&chapters.some(d=>d.id===state.targetDoc))?state.targetDoc:chapters[0].id;
  const full=await api('/api/documents/'+selected);
  openDoc(selected,{body:full.body+'\n\n'+content});
  $('docSaveStatus').textContent='Review before saving the appended text';
  toast('Review the proposed addition before saving.');
}
function openSearch(q=''){
  $('searchModal').hidden=false;$('archiveSearch').value=q;
  if(q.trim())searchArchive();
  else $('searchResults').innerHTML='<div class="search-hint">Search your project’s stored text, not the internet.</div>';
  $('archiveSearch').focus();
}
let searchTimer;
function searchArchive(){
  clearTimeout(searchTimer);
  const q=$('archiveSearch').value.trim();if(!q){$('searchResults').innerHTML='<div class="search-hint">Type to search chapters, notes, and conversations.</div>';return}
  searchTimer=setTimeout(async()=>{
    try{
      const res=await api(`/api/projects/${state.projectId}/search?q=${encodeURIComponent(q)}`);
      const box=$('searchResults');clear(box);
      const all=[...res.documents,...res.conversations];if(!all.length){box.innerHTML='<div class="search-hint">Nothing found in this project yet.</div>';return}
      for(const result of all)box.append(searchResultButton(result));
    }catch(e){toast(e.message)}
  },250);
}
function pickBy(items,query,key){
  const s=query.trim().toLowerCase();if(!s)return null;
  const exact=items.filter(i=>i[key].toLowerCase()===s);if(exact.length===1)return exact[0];
  const part=items.filter(i=>i[key].toLowerCase().includes(s));return part.length===1?part[0]:null;
}
async function runWorkspaceCommand(cmd){
  const clearPrompt=()=>{$('promptInput').value='';applyMode(true);closeMenu()};
  if(cmd.cmd==='unknown'||cmd.action==='unknown'){
    toast(cmd.cmd==='unknown'?`Unknown command /${cmd.arg}. Type /help to see what is available.`
      :`Unknown option "${cmd.arg}" for /${cmd.cmd}. Try /${cmd.cmd} ${cmd.cmd==='doc'?'new, open or list':'open or list'}.`);return;
  }
  if(cmd.cmd==='help'){toast('Commands: /project  /model  /new  /doc  /chat  /search  /export  /help');return}
  if(cmd.cmd==='new'){newThread();return}
  if(cmd.cmd==='export'){clearPrompt();window.location.href=`/api/projects/${state.projectId}/export`;toast('Exporting this project as JSON.');return}
  if(cmd.cmd==='search'){clearPrompt();openSearch(cmd.arg);return}
  if(cmd.cmd==='doc'){
    if(cmd.action==='list'||cmd.action==='help'){
      toast(state.docs.length?`${state.docs.length} document(s): ${state.docs.map(d=>d.title).join(', ')}`:'No documents yet. Use /doc new to create one.');return;
    }
    if(cmd.action==='new'){
      const first=(cmd.arg.split(/\s+/)[0]||'').toLowerCase();const typed=DOC_TYPES.includes(first);
      clearPrompt();openDoc(null,{type:typed?first:'chapter',title:typed?cmd.arg.slice(first.length).trim():cmd.arg,body:''});return;
    }
    if(cmd.action==='open'){
      if(!cmd.arg){toast('Usage: /doc open <title>');return}
      const d=pickBy(state.docs,cmd.arg,'title');
      if(!d){toast(`No single document matches "${cmd.arg}". Try /doc list.`);return}
      clearPrompt();openDoc(d.id);return;
    }
  }
  if(cmd.cmd==='chat'){
    if(cmd.action==='list'||cmd.action==='help'){
      toast(state.conversations.length?`${state.conversations.length} conversation(s): ${state.conversations.map(c=>c.title).join(', ')}`:'No conversations yet.');return;
    }
    if(cmd.action==='open'){
      if(!cmd.arg){toast('Usage: /chat open <title>');return}
      const c=pickBy(state.conversations,cmd.arg,'title');
      if(!c){toast(`No single conversation matches "${cmd.arg}". Try /chat list.`);return}
      await openConversation(c.id);
    }
  }
}
function runModelCommand(cmd){
  const providers=state.bootstrap.providers;
  const summary=Object.entries(providers).map(([id,p])=>`${id===state.provider?'▶ ':''}${p.label}${p.ready?'':' (not configured)'}`).join(' · ');
  if(cmd.action==='help'||cmd.action==='list'){toast(summary);return}
  const id=resolveProvider(cmd.arg);
  if(!id){toast(`No model matches "${cmd.arg}". ${summary}`);return}
  if(!providers[id].ready){
    toast(`${providers[id].label} is not configured on the server. Set its environment variables and restart (see README).`);return;
  }
  state.provider=id;updateProviderStatus();
  $('promptInput').value='';applyMode(true);closeMenu();
  toast(`Model set to ${providers[id].label}${id==='demo'?' — replies are placeholders.':'.'}`);
}
async function runProjectCommand(cmd){
  const cur=currentProject();const names=()=>state.bootstrap.projects.map(p=>p.name).join(', ');
  const need=(usage)=>{toast(`Usage: ${usage}`);return true};
  if(state.busy)return;setBusy(true);
  try{
    if(cmd.action==='list'){toast('Projects: '+names());return}
    if(cmd.action==='help'||cmd.action==='unknown'){toast('Try /project new, switch, rename, delete, or list.');return}
    if(cmd.action==='new'){
      if(!cmd.arg)return need('/project new <name>');
      const created=await api('/api/projects',{method:'POST',body:JSON.stringify({name:cmd.arg})});
      await refreshProjects(created.id);toast(`Created and switched to "${created.name}".`);return;
    }
    if(cmd.action==='switch'){
      if(!cmd.arg)return need('/project switch <name>');
      const target=findProject(cmd.arg);
      if(!target){toast(`No single project matches "${cmd.arg}". Available: ${names()}`);return}
      await refreshProjects(target.id);toast(`Switched to "${target.name}".`);return;
    }
    if(cmd.action==='rename'){
      if(!cmd.arg)return need('/project rename <new name>');
      const updated=await api('/api/projects/'+state.projectId,{method:'PATCH',body:JSON.stringify({name:cmd.arg})});
      await refreshProjects(updated.id);toast(`Renamed to "${updated.name}".`);return;
    }
    if(cmd.action==='delete'){
      if(cmd.arg!==cur.name){toast(`To delete, send: /project delete ${cur.name}`);return}
      const removed=await api(`/api/projects/${state.projectId}?confirm_name=${encodeURIComponent(cur.name)}`,{method:'DELETE'});
      state.projectId=null;await refreshProjects();
      toast(`Deleted "${cur.name}" (${removed.documents} documents, ${removed.conversations} conversations).`);
    }
  }catch(e){toast(e.message)}
  finally{setBusy(false)}
}
async function refreshProjects(selectedId){
  state.bootstrap=await api('/api/bootstrap');
  state.projectId=selectedId||state.projectId||state.bootstrap.projects[0].id;
  $('projectName').textContent=currentProject().name;
  if(!state.bootstrap.providers[state.provider]?.ready)state.provider='demo';
  updateProviderStatus();await loadOverview();newThread();
}
function updateProviderStatus(){
  const p=state.bootstrap.providers[state.provider];
  $('modelName').textContent=p.label;$('chipModel').title=state.provider==='demo'?'Demo replies are placeholders. Change the model from the prompt.':'Change the AI model from the prompt';
}
function bind(){
  $('promptInput').addEventListener('input',onPrompt);
  $('promptInput').addEventListener('blur',()=>closeMenu());
  $('promptInput').addEventListener('keydown',e=>{if(menuKeydown(e))return;if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();sendPrompt()}});
  $('sendBtn').addEventListener('click',sendPrompt);
  for(const b of document.querySelectorAll('.mode-pills button')){
    b.onclick=()=>{
      state.modeOverride=state.modeOverride===b.dataset.mode?null:b.dataset.mode;applyMode(true);$('promptInput').focus()};
  }
  for(const b of document.querySelectorAll('[data-example]')){
    b.onclick=()=>{$('promptInput').value=b.dataset.example;state.modeOverride=null;onPrompt();$('promptInput').focus()};
  }
  $('newThreadInChat').onclick=newThread;
  $('homeBrand').onclick=newThread;$('homeBrand').onkeydown=e=>{if(e.key==='Enter')newThread()};
  $('chipProject').onclick=()=>fillPrompt('/project ');
  $('chipModel').onclick=()=>fillPrompt('/model ');
  $('chipDocs').onclick=()=>fillPrompt('/doc list');
  $('chipChats').onclick=()=>fillPrompt('/chat list');
  $('closeDoc').onclick=()=>$('documentModal').hidden=true;$('saveDoc').onclick=saveDoc;
  $('closeSearch').onclick=()=>$('searchModal').hidden=true;
  $('archiveSearch').oninput=searchArchive;
  for(const modal of [$('documentModal'),$('searchModal')])modal.onclick=e=>{if(e.target===modal)modal.hidden=true};
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'){$('documentModal').hidden=true;$('searchModal').hidden=true}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openSearch()}
    if(e.key.toLowerCase()==='n'&&!(e.target instanceof HTMLInputElement)&&!(e.target instanceof HTMLTextAreaElement)&&!(e.target instanceof HTMLSelectElement)&&!(e.ctrlKey||e.metaKey)){newThread()}
  });
}
async function boot(){try{bind();await refreshProjects();applyMode(true);document.body.dataset.ready='true'}catch(e){toast('Initialization failed: '+e.message);console.error(e)}}
boot();

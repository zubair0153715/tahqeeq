"""Tahqeeq page — free research-answer engine UI (original design)."""

TAHQEEQ_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tahqeeq — Free Research Answers with Verified Citations</title>
<style>
body{font-family:system-ui,sans-serif;max-width:780px;margin:0 auto;padding:16px;color:#1a1a1a}
h1{margin-bottom:2px} .sub{color:#555;margin-top:0}
input,textarea,select{width:100%;padding:8px;margin:4px 0 12px;border:1px solid #bbb;border-radius:6px;box-sizing:border-box;font-size:15px}
textarea{min-height:90px} button{padding:10px 18px;border:0;border-radius:6px;background:#1e3a5f;color:#fff;font-size:16px;cursor:pointer}
button.sec{background:#eee;color:#111} .card{border:1px solid #ddd;border-radius:8px;padding:14px;margin:14px 0}
.small{color:#555;font-size:13px} .warn{background:#fff7e6;border:1px solid #e6c87a;border-radius:8px;padding:12px;margin:14px 0}
sup a{text-decoration:none;color:#1e3a5f} li{margin:6px 0}
#answer p{line-height:1.6} #answer h2{font-size:18px;margin:18px 0 6px}
.hist{cursor:pointer;color:#1e3a5f} .hist:hover{text-decoration:underline}
code{background:#f6f6f6;padding:1px 5px;border-radius:4px}
</style></head><body>
<h1>Tahqeeq — تحقیق</h1>
<p class="sub">Ask any question, get a sourced answer. Every citation number
is checked against the live search results it came from — a number only
appears if the source really backs that sentence. Free, unlimited, no
account, no card, no usage meter.</p>
<div class="warn"><b>Honest limits, stated plainly:</b> Tahqeeq answers
only from what its live search returns. If the search finds nothing, it
says so instead of guessing. Numbers must still be re-checked at the
source before you quote them — the citation check shows you exactly
how much of the answer the search actually supports. No file upload
in v1. Nothing is stored on our server: your history lives in your own
browser.</div>
<form id="f">
<label>Your question
<textarea name="question" id="q" placeholder="What is the current gold rate per tola in Pakistan?"></textarea></label>
<label>Mode <select name="mode">
<option value="quick" selected>Quick — one grounded answer</option>
<option value="deep">Deep — 3 angles, one structured brief (slower)</option>
</select></label>
<label>Answer language <select name="language">
<option value="en" selected>English</option>
<option value="roman">Roman-Urdu</option>
<option value="ur">Urdu (script, RTL)</option>
</select></label>
<button type="submit" id="askBtn">Research it</button>
<span id="aiState" class="small"></span>
</form>
<p class="small">Try: <a href="#" class="ex">What is the current gold rate per tola in Pakistan?</a> ·
<a href="#" class="ex">What are the side effects of metformin?</a> ·
<a href="#" class="ex">Who won the 2026 Nobel Prize in Physics?</a></p>
<div id="out"></div>
<div class="card" id="histCard" style="display:none"><b>Your recent questions</b>
<ul id="hist"></ul></div>
<script>
const $=s=>document.querySelector(s);
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function renderAnswer(text){
  return esc(text).split(/\\n\\n+/).map(par=>{
    if(par.startsWith('## ')) return '<h2>'+esc(par.slice(3))+'</h2>';
    return '<p>'+par.replace(/\\n/g,'<br>').replace(/\\[(\\d+(?:\\s*,\\s*\\d+)*)\\]/g,(m,g)=>{
      return g.split(',').map(n=>'<sup><a href="#src-'+n.trim()+'">['+n.trim()+']</a></sup>').join('');
    })+'</p>';
  }).join('');
}
function mdExport(d){
  const lang={en:'English',roman:'Roman-Urdu',ur:'Urdu'}[d.language]||'English';
  let s='# Tahqeeq — '+d.question+'\\n\\n_Mode: '+d.mode+' · Language: '+lang+'_\\n\\n'+d.answer+'\\n\\n## Sources\\n\\n';
  d.sources.forEach((x,i)=>{s+=(i+1)+'. ['+(x.title||x.domain)+']('+x.url+')\\n'});
  s+='\\n## Citation check\\n- Sources retrieved: '+d.audit.n_sources+'\\n- Sources cited: '+d.audit.cited.length+'\\n- Answer covered by retrieved sources: '+d.audit.coverage+'%\\n- Dangling citations: '+(d.audit.dangling.length?d.audit.dangling.join(', '):'none')+'\\n- Retrieved but never cited: '+(d.audit.uncited.length?d.audit.uncited.join(', '):'none')+'\\n';
  return s;
}
function saveHist(q){
  let h=[]; try{h=JSON.parse(localStorage.getItem('tahqeeq-hist')||'[]')}catch(e){}
  h=[q,...h.filter(x=>x!==q)].slice(0,10);
  localStorage.setItem('tahqeeq-hist',JSON.stringify(h)); showHist();
}
function showHist(){
  let h=[]; try{h=JSON.parse(localStorage.getItem('tahqeeq-hist')||'[]')}catch(e){}
  if(!h.length) return;
  $('#histCard').style.display='block';
  $('#hist').innerHTML=h.map(q=>'<li><span class="hist">'+esc(q)+'</span></li>').join('');
  document.querySelectorAll('.hist').forEach(el=>el.onclick=()=>{$('#q').value=el.textContent;$('#f').requestSubmit()});
}
fetch('/tahqeeq/api/ai-status').then(r=>r.json()).then(d=>{
  $('#aiState').textContent=d.ai_available?'AI ready — live search on':'AI unavailable: GEMINI_API_KEY not set on the server';
});
document.querySelectorAll('.ex').forEach(a=>a.onclick=e=>{e.preventDefault();$('#q').value=a.textContent;$('#f').requestSubmit()});
$('#f').addEventListener('submit',async e=>{
  e.preventDefault();
  const fd=new FormData(e.target), btn=$('#askBtn');
  btn.disabled=true; btn.textContent='Researching…';
  $('#out').innerHTML='<p class="small">Searching the live web and checking every citation…</p>';
  try{
    const r=await fetch('/tahqeeq/api/ask',{method:'POST',body:new URLSearchParams(fd)});
    const d=await r.json();
    if(!d.ok){$('#out').innerHTML='<div class="warn">'+esc(d.error||'Error')+'</div>';return}
    let h='<div class="card"><div id="answer"'+(d.language==='ur'?' dir="rtl"':'')+'>'+renderAnswer(d.answer)+'</div></div>';
    if(d.warning) h+='<div class="warn">'+esc(d.warning)+'</div>';
    h+='<div class="card"><b>Sources ('+d.sources.length+')</b><ol>'+d.sources.map((s,i)=>'<li id="src-'+(i+1)+'"><a href="'+esc(s.url)+'" target="_blank" rel="noopener">'+esc(s.title||s.domain)+'</a><br><span class="small">'+esc(s.domain)+'</span></li>').join('')+'</ol></div>';
    h+='<div class="card"><b>Citation check</b><ul>'
      +'<li>Answer covered by retrieved sources: <b>'+d.audit.coverage+'%</b></li>'
      +'<li>Sources retrieved: '+d.audit.n_sources+' · cited in the answer: '+d.audit.cited.length+'</li>'
      +'<li>Dangling citations (number with no source): '+(d.audit.dangling.length?'<b>'+d.audit.dangling.join(', ')+'</b>':'none')+'</li>'
      +'<li>Retrieved but never cited: '+(d.audit.uncited.length?d.audit.uncited.join(', '):'none')+'</li>'
      +'<li>Searches run: '+esc((d.queries||[]).join(' · ')||'—')+'</li></ul>'
      +'<button type="button" class="sec" id="copyMd">Copy as Markdown</button></div>';
    $('#out').innerHTML=h;
    $('#copyMd').onclick=()=>{navigator.clipboard.writeText(mdExport(d));$('#copyMd').textContent='Copied!';};
    saveHist(d.question);
  }catch(err){$('#out').innerHTML='<div class="warn">Request failed: '+esc(String(err))+'</div>'}
  finally{btn.disabled=false;btn.textContent='Research it'}
});
showHist();
</script></body></html>
"""

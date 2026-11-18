/* Isolated assistant. All model/source content is rendered as text, never HTML. */
(() => {
  'use strict';
  const locale = {
    'en-IN': {title:'MAERII Assistant',ask:'Ask about this material or MAERII',send:'Send',more:'More questions',listen:'Listen',stop:'Stop',replay:'Replay',clear:'Clear conversation',reset:'Reset language',close:'Close',wait:'Working…',error:'Assistant unavailable or limit reached. Please try again later.',missing:'Reopen this material to share its current information with the assistant.',sources:'Record references',cached:'Saved answer',helpful:'Helpful',notHelpful:'Not helpful',pilot:'Pilot: language content awaits fluent-speaker review.',privacy:'Answers may use Gemini and Sarvam. Avoid personal or sensitive information.',navigate:'Open section (main website may be English)',term:'Choose a term',context:'Current material',choose:'Select a product',none:'No material selected',confirm:'Feedback saved',unknownDate:'Observation date unknown',language:'Language'},
    'hi-IN': {title:'MAERII सहायक',ask:'इस सामग्री या MAERII के बारे में पूछें',send:'भेजें',more:'और प्रश्न',listen:'सुनें',stop:'रोकें',replay:'फिर सुनें',clear:'बातचीत साफ़ करें',reset:'भाषा रीसेट करें',close:'बंद करें',wait:'कृपया प्रतीक्षा करें…',error:'सहायक उपलब्ध नहीं है या सीमा पूरी हो गई। बाद में प्रयास करें।',missing:'जानकारी साझा करने के लिए सामग्री फिर खोलें।',sources:'जानकारी के संदर्भ',cached:'सहेजा उत्तर',helpful:'उपयोगी',notHelpful:'उपयोगी नहीं',pilot:'परीक्षण: भाषा की समीक्षा अभी बाकी है।',privacy:'उत्तर Gemini और Sarvam का उपयोग कर सकते हैं। निजी जानकारी न दें।',navigate:'अनुभाग खोलें (मुख्य वेबसाइट अंग्रेज़ी में हो सकती है)',term:'शब्द चुनें',context:'चुनी सामग्री',choose:'उत्पाद चुनें',none:'कोई सामग्री नहीं चुनी',confirm:'प्रतिक्रिया सहेजी गई',unknownDate:'जानकारी की तारीख अज्ञात',language:'भाषा'},
    'mr-IN': {title:'MAERII सहाय्यक',ask:'या साहित्याबद्दल किंवा MAERII बद्दल विचारा',send:'पाठवा',more:'आणखी प्रश्न',listen:'ऐका',stop:'थांबवा',replay:'पुन्हा ऐका',clear:'संभाषण पुसा',reset:'भाषा रीसेट करा',close:'बंद करा',wait:'कृपया थांबा…',error:'सहाय्यक उपलब्ध नाही किंवा मर्यादा संपली. नंतर प्रयत्न करा.',missing:'माहिती शेअर करण्यासाठी साहित्य पुन्हा उघडा.',sources:'नोंदींचे संदर्भ',cached:'जतन केलेले उत्तर',helpful:'उपयुक्त',notHelpful:'उपयुक्त नाही',pilot:'चाचणी: भाषेचे पुनरावलोकन बाकी आहे.',privacy:'उत्तरे Gemini आणि Sarvam वापरू शकतात. वैयक्तिक माहिती देऊ नका.',navigate:'विभाग उघडा (मुख्य संकेतस्थळ इंग्रजीत असू शकते)',term:'शब्द निवडा',context:'निवडलेले साहित्य',choose:'उत्पादन निवडा',none:'साहित्य निवडलेले नाही',confirm:'अभिप्राय जतन झाला',unknownDate:'माहितीची तारीख अज्ञात',language:'भाषा'}
  };
  const names = {'en-IN':'English','hi-IN':'हिन्दी','mr-IN':'मराठी'};
  const state = {language:null,material_id:null,section:'overview',product:null,records:new Map(),names:new Map(),epoch:0,open:false,audio:null};
  const objects = new WeakMap();
  let panel,launcher,controls,history,suggestions,status,input,form,languageBox,heading,contextLine,warning,capabilities;
  let questionAbort, suggestionAbort, suggestionTimer;
  const t = key => locale[state.language || 'en-IN'][key];
  const el = (tag,text,cls) => {const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e;};
  const button = (text,fn) => {const b=el('button',text); b.type='button'; b.addEventListener('click',fn); return b;};
  function storedLanguage() {try{return localStorage.getItem('maerii-assistant-language');}catch{return null;}}
  function stopAudio(){if(state.audio){state.audio.pause();state.audio.currentTime=0;state.audio=null;}}
  function invalidate(){state.epoch++; questionAbort?.abort(); suggestionAbort?.abort(); stopAudio(); if(form)form.querySelector('button').disabled=false;}
  function context(){return {material_id:state.material_id,section:state.section,product:state.product,refs:{...(state.records.get(state.material_id)||{})}};}
  async function api(path,body,signal){
    const response=await fetch('/api/assistant/'+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),credentials:'same-origin',signal});
    if(!response.ok){const err=new Error(t('error'));err.status=response.status;throw err;}
    return response.json();
  }
  function schedule(){clearTimeout(suggestionTimer);suggestionTimer=setTimeout(refresh,150);}
  window.addEventListener('maerii:selection',event=>{invalidate();state.material_id=event.detail.material_id;state.section='overview';state.product=null;schedule();});
  window.addEventListener('maerii:section',event=>{invalidate();state.section=event.detail.section;state.product=null;schedule();});
  window.addEventListener('maerii:response',event=>{
    const {url,data,contextRef}=event.detail;
    const match=String(url).match(/^\/api\/materials\/(\d+)(?:\/(categories|market|recommend|enhance))?$/);
    if(!match)return;
    const id=Number(match[1]);
    if(data.material?.name)state.names.set(id,data.material.name);
    if(!contextRef)return;
    const task=({categories:'categories',market:'market',recommend:'recommendations',enhance:'marketing'})[match[2]]||'material';
    objects.set(data,{id,task,ref:contextRef});
    const refs=state.records.get(id)||{};
    refs[task]=contextRef;
    if(task==='market'||task==='categories'){delete refs.recommendations;delete refs.marketing;}
    state.records.set(id,refs);
    if(id===state.material_id){invalidate();schedule();}
  });
  window.addEventListener('maerii:display',event=>{
    const {data,task,product}=event.detail;
    const entry=objects.get(data);
    if(!entry||entry.id!==state.material_id)return;
    const refs=state.records.get(entry.id)||{}; refs[task]=entry.ref; state.records.set(entry.id,refs);
    if(product){state.product=product;state.section='marketing';}
    invalidate();schedule();
  });
  function navigate(action){
    if(action==='search'){close();document.getElementById('searchInput')?.focus();return;}
    const map={overview:0,categories:1,market:2,recommendations:3};
    if(Object.hasOwn(map,action)){
      const b=document.querySelectorAll('.detail-tab')[map[action]];
      if(b){close();b.click();b.focus();}
    }
  }
  function close(){state.open=false;panel.hidden=true;invalidate();launcher.setAttribute('aria-expanded','false');launcher.focus();}
  function chooseLanguage(language){
    invalidate();state.language=language;
    try{localStorage.setItem('maerii-assistant-language',language);}catch{/* preference remains in memory */}
    layout();schedule();
  }
  function layout(){
    heading.textContent=t('title');panel.lang=(state.language||'en-IN').split('-')[0];
    controls.replaceChildren();languageBox.replaceChildren();
    controls.append(button('× '+t('close'),close));
    if(!state.language){
      languageBox.append(el('p','Choose your language / अपनी भाषा चुनें / आपली भाषा निवडा'));
      for(const [code,name] of Object.entries(names))languageBox.append(button(name,()=>chooseLanguage(code)));
      form.hidden=true;suggestions.hidden=true;warning.textContent='English · हिन्दी · मराठी';return;
    }
    const select=el('select');select.setAttribute('aria-label',t('language'));
    for(const [code,name] of Object.entries(names)){const o=el('option',name);o.value=code;o.selected=code===state.language;select.append(o);}
    select.addEventListener('change',()=>chooseLanguage(select.value));controls.append(select);
    controls.append(button(t('clear'),()=>{invalidate();history.replaceChildren();status.textContent='';schedule();}));
    controls.append(button(t('reset'),()=>{invalidate();state.language=null;try{localStorage.removeItem('maerii-assistant-language');}catch{}layout();}));
    form.hidden=false;suggestions.hidden=false;input.placeholder=t('ask');input.setAttribute('aria-label',t('ask'));form.querySelector('button').textContent=t('send');
    warning.textContent=t('privacy')+' '+t('pilot');
  }
  async function refresh(){
    if(!state.open||!state.language)return;
    const current=state.epoch;suggestionAbort?.abort();suggestionAbort=new AbortController();
    contextLine.textContent=state.material_id ? t('context')+': '+(state.names.get(state.material_id)||state.material_id) : t('none');
    try{
      const result=await api('suggestions',{language:state.language,context:context()},suggestionAbort.signal);
      if(current!==state.epoch)return;
      suggestions.replaceChildren();
      for(const q of result.suggestions)suggestions.append(button(q.label,()=>ask({question_id:q.id},q.label)));
      const more=el('details');more.append(el('summary',t('more')));
      for(const q of result.more)more.append(button(q.label,()=>ask({question_id:q.id},q.label)));
      suggestions.append(more);
    }catch(error){if(error.name!=='AbortError'&&current===state.epoch)status.textContent=t('error');}
  }
  async function ask(fields,label){
    invalidate();const epoch=state.epoch;const ctx=context();const lang=state.language;
    questionAbort=new AbortController();status.textContent=t('wait');form.querySelector('button').disabled=true;
    const user=el('p',label,'ma-chat-question');history.append(user);
    try{
      const answer=await api('answer',{...fields,language:lang,context:ctx},questionAbort.signal);
      if(epoch!==state.epoch)return;
      const card=el('article',undefined,'ma-chat-answer');card.lang=answer.language.split('-')[0];
      card.append(el('small',(state.names.get(ctx.material_id)||t('none'))+' · '+names[answer.language]+(answer.cache_hit?' · '+t('cached'):'')));
      for(const message of answer.warnings)card.append(el('p',message,'ma-chat-warning'));
      card.append(el('p',answer.text));
      if(answer.references.length){
        const refs=el('details');refs.append(el('summary',t('sources')));
        for(const ref of answer.references)refs.append(el('p',ref.id+' · '+(ref.observed_at||t('unknownDate'))+' · '+ref.version));card.append(refs);
      }
      for(const choice of answer.choices){
        card.append(button(choice,()=>{if(answer.question_id==='Q05')ask({question_id:'Q05',term:choice},choice);else{state.product=choice;ask({question_id:answer.question_id},choice);}}));
      }
      if(answer.action)card.append(button(t('navigate'),()=>navigate(answer.action)));
      if(answer.audio_available){
        const listen=button(t('listen'),async()=>{
          const audioEpoch=state.epoch;stopAudio();listen.disabled=true;
          try{
            const result=await api('audio',{answer_id:answer.answer_id});
            if(audioEpoch!==state.epoch)return;
            state.audio=new Audio(result.url);await state.audio.play();listen.textContent=t('replay');
          }catch{status.textContent=t('error');}finally{listen.disabled=false;}
        });card.append(listen,button(t('stop'),()=>{state.epoch++;stopAudio();}));
      }
      for(const [key,value] of [['helpful',true],['notHelpful',false]])card.append(button(t(key),async()=>{try{await api('feedback',{answer_id:answer.answer_id,helpful:value});status.textContent=t('confirm');}catch{status.textContent=t('error');}}));
      history.append(card);status.textContent='';card.scrollIntoView({block:'nearest'});
    }catch(error){if(error.name!=='AbortError'&&epoch===state.epoch)status.textContent=t('error');}
    finally{if(epoch===state.epoch)form.querySelector('button').disabled=false;}
  }
  async function init(){
    try{capabilities=await api('capabilities');}catch{return;}
    if(!capabilities.enabled)return;
    state.language=Object.hasOwn(names,storedLanguage())?storedLanguage():null;
    launcher=button('MAERII · Help / मदद / मदत',()=>{state.open=true;panel.hidden=false;launcher.setAttribute('aria-expanded','true');layout();refresh();panel.querySelector('button')?.focus();});
    launcher.id='ma-assistant-launcher';launcher.setAttribute('aria-controls','ma-assistant-panel');launcher.setAttribute('aria-expanded','false');document.body.append(launcher);
    panel=el('section');panel.id='ma-assistant-panel';panel.hidden=true;panel.setAttribute('role','dialog');panel.setAttribute('aria-labelledby','ma-assistant-heading');
    heading=el('h2',t('title'));heading.id='ma-assistant-heading';controls=el('div',undefined,'ma-chat-controls');
    languageBox=el('div');contextLine=el('p',undefined,'ma-chat-context');warning=el('p',undefined,'ma-chat-notice');
    history=el('div',undefined,'ma-chat-history');history.setAttribute('role','log');history.setAttribute('aria-live','polite');
    suggestions=el('div',undefined,'ma-chat-suggestions');status=el('p');status.setAttribute('role','status');
    form=el('form');input=el('input');input.maxLength=500;input.autocomplete='off';const send=el('button',t('send'));send.type='submit';form.append(input,send);
    form.addEventListener('submit',e=>{e.preventDefault();const text=input.value.trim();if(text){input.value='';ask({text},text);}});
    panel.append(heading,controls,languageBox,contextLine,warning,history,suggestions,status,form);document.body.append(panel);
    panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();close();}});
    layout();
  }
  init();
})();

(() => {
  'use strict';
  const token = location.hash.slice(1);
  history.replaceState(null, '', '/');
  let frame, dirty = false, mode, opening = false;
  const notice = document.getElementById('notice');
  async function rpc(action, payload) {
    const response = await fetch('/rpc', {method:'POST', credentials:'omit', headers:{'Content-Type':'application/json','X-Alex-Session':token}, body:JSON.stringify({action,payload})});
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || 'Connexion Python interrompue.');
    return data.result;
  }
  async function open(next, force=false) {
    if (opening || (frame && next===mode && !force)) return;
    if(dirty&&!confirm('Des modifications ne sont pas enregistrées. Quitter et les abandonner ?'))return;
    opening = true;
    try {
      const response = await fetch('/'+next+'.html');
      if(!response.ok)throw new Error('Impossible de charger cet espace.');
      const html = await response.text();
      mode=next;dirty=false;
      frame=document.createElement('iframe');frame.title=next==='analyst'?'ALEX — Analyste':'ALEX — Manager et Déontologie';
      frame.setAttribute('sandbox','allow-scripts allow-modals allow-downloads');
      document.getElementById('frame').replaceChildren(frame);frame.srcdoc=html;
    } catch(e) {notice.textContent=e.message;} finally {opening=false;}
  }
  window.addEventListener('message',async event=>{
    if(!frame||event.source!==frame.contentWindow||!event.data?.alex)return;
    const {id,action,payload}=event.data;
    if(action==='dirty'){dirty=!!payload;return;}
    if(!Number.isInteger(id))return;
    const source=event.source;
    try {source.postMessage({alex:true,id,result:await rpc(action,payload)},'*');}
    catch(e){source.postMessage({alex:true,id,error:e.message},'*');}
  });
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  function button(label,handler){const b=document.createElement('button');b.textContent=label;b.onclick=handler;document.querySelector('nav').append(b);}
  (async()=>{
    if(!token)throw new Error('Ouvrez le lien complet fourni par alex serve (avec son fragment de session).');
    const roles=await rpc('roles');
    if(roles.analyst)button('Espace analyste',()=>open('analyst'));
    if(roles.manager||roles.deontology)button('Manager / Déontologie',()=>open('manager'));
    if(!roles.analyst&&!roles.manager&&!roles.deontology)throw new Error('Votre compte ne fait partie d’aucun groupe ALEX.');
    button('Actualiser les dossiers',()=>open(mode,true));
    notice.textContent='Session Microsoft active · Données enregistrées dans SharePoint · Application Python locale';
    await open(roles.analyst?'analyst':'manager');
  })().catch(e=>{notice.textContent=e.message;});
})();

import { MAP_DATA } from './map-data.mjs';
import { findRoute } from './route-engine.mjs';

const WF_ICONS = {
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  route:'<circle cx="5" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 5h8a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h8"/>',
  'arrow-right':'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  'arrow-left':'<path d="M20 12H4m6-6-6 6 6 6"/>',
  layers:'<path d="m12 3 10 5-10 5L2 8l10-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  building:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h1m4 0h1M9 11h1m4 0h1M9 15h1m4 0h1m-4 6v-3h2v3"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',minus:'<path d="M5 12h14"/>',
  expand:'<path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>',
  locate:'<circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
  swap:'<path d="M8 3v17m-4-4 4 4 4-4m4 5V4m-4 4 4-4 4 4"/>',
  room:'<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 21V7h6v14m-3-7h.1"/>',
  study:'<path d="M3 4h7a3 3 0 0 1 2 2 3 3 0 0 1 2-2h7v15h-7a3 3 0 0 0-2 2 3 3 0 0 0-2-2H3V4Zm9 2v15"/>',
  restroom:'<circle cx="8" cy="5" r="2"/><circle cx="17" cy="5" r="2"/><path d="M5 11h6m-5-2v7h4V9M8 16v5m6-10h6m-3-2-3 8h6l-3-8m0 8v4"/>',
  exit:'<path d="M10 4H4v16h6m4-12 4 4-4 4m-6-4h13"/>',
  food:'<path d="M4 3v6a3 3 0 0 0 6 0V3M7 3v18M19 3c-4 2-4 9 0 10v8m0-18v10"/>',
  vending:'<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 5h8v8H8V5Zm5 12h3m-8 2h8m-8-2h.1"/>',
  escalator:'<path d="M3 17h5l8-10h5v5h-3l-8 10H3v-5Z"/><circle cx="8" cy="5" r="2"/><path d="M8 9v4"/>',
  entrance:'<path d="M3 21h18M5 21V4h14v17m-10 0V9h6v12m-6-6h.1"/>',
  camera:'<path d="M4 7h4l2-3h4l2 3h4a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z"/><circle cx="12" cy="14" r="4"/>',
  hand:'<path d="M8 13V6a2 2 0 0 1 4 0v6m0-4a2 2 0 0 1 4 0v5m0-3a2 2 0 0 1 4 0v7a5 5 0 0 1-5 5h-3a5 5 0 0 1-4-2l-5-6a2 2 0 0 1 3-2l2 2"/>',
  check:'<path d="m4 12 5 5L20 6"/>',
  flag:'<path d="M5 22V3m0 1c4-4 9 4 14 0v10c-5 4-10-4-14 0"/>',
  'turn-left':'<path d="M18 21v-9a5 5 0 0 0-5-5H4m5-5L4 7l5 5"/>',
  'turn-right':'<path d="M6 21v-9a5 5 0 0 1 5-5h9m-5-5 5 5-5 5"/>',
};
const wfIcon=(name,extra='')=>`<svg ${extra} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${WF_ICONS[name]||WF_ICONS.room}</svg>`;
const wfEscape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const wf$=selector=>document.querySelector(selector);
const wfNormalize=value=>String(value).toLocaleLowerCase().replace(/[\s·’']/g,'');
const wfDefaultView=()=>window.innerWidth<=700?[100,80,700,490]:[0,0,1000,700];
const wfPlaces=new Map(MAP_DATA.places.map(p=>[p.id,p]));
const wfNodes=new Map(MAP_DATA.nodes.map(n=>[n.id,n]));
const wfMedia=new Map();
const wfState={floor:'5',selected:'f5-y5302',category:'all',search:'',panel:'explore',origin:null,destination:null,route:null,position:null,activeStep:-1,view:wfDefaultView()};
let wfToastTimer, wfDb=null, wfPhotoTarget=null, wfImageFloor=null, wfDrag=null, wfDragged=false;

function wfHydrateIcons(root=document){root.querySelectorAll('[data-icon]').forEach(el=>{el.innerHTML=wfIcon(el.dataset.icon);});}
function wfPlaceLabel(p){return `${p.name} · ${p.floorId}F`;}
function wfCategoryName(p){return ({room:'Room',study:'Study room',restroom:'Restroom',exit:'Exit',food:'Food & drink',vending:'Vending',escalator:'Escalator',entrance:'Entrance'})[p.category]||'Place';}
function wfToast(message){const el=wf$('#toast');el.textContent=message;el.hidden=false;clearTimeout(wfToastTimer);wfToastTimer=setTimeout(()=>{el.hidden=true;},4000);}
function wfOpenDialog(id){const d=document.getElementById(id);if(typeof d.showModal==='function')d.showModal();else d.setAttribute('open','');}
function wfCloseDialog(id){const d=document.getElementById(id);if(typeof d.close==='function')d.close();else d.removeAttribute('open');}
function wfSetPanel(panel){wfState.panel=panel;for(const name of ['explore','directions']){const active=name===panel;wf$(`#${name}-panel`).hidden=!active;wf$(`#${name}-tab`).classList.toggle('active',active);wf$(`#${name}-tab`).setAttribute('aria-selected',String(active));}}
function wfSetFloor(floor,{fit=true}={}){if(!MAP_DATA.floors.some(f=>f.id===String(floor)))return;wfState.floor=String(floor);if(fit)wfState.view=wfDefaultView();if(wfPlaces.get(wfState.selected)?.floorId!==wfState.floor)wfState.selected=null;wfRenderSelected();wfRenderFloorControls();wfRenderPlaces();wfRenderMap();if(wf$('#setup-dialog').open)wfRenderSetup();}
function wfRenderFloorControls(){wf$('#header-floor').textContent=`Floor ${wfState.floor}`;wf$('#map-floor-title').textContent=`Floor ${wfState.floor}`;document.querySelectorAll('[data-floor]').forEach(b=>{const active=b.dataset.floor===wfState.floor;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});}
function wfSelectPlace(id,{moveFloor=true}={}){if(!wfPlaces.has(id))return;wfState.selected=id;if(moveFloor&&wfPlaces.get(id).floorId!==wfState.floor)wfSetFloor(wfPlaces.get(id).floorId);if(window.innerWidth<=700){const p=wfPlaces.get(id);wfState.view=[p.x-230,p.y-161,460,322];}wfRenderPlaces();wfRenderMap();wfRenderSelected();}
function wfRenderPlaces(){
  const query=wfNormalize(wfState.search.trim());
  const items=MAP_DATA.places.filter(p=>query?wfNormalize(p.name+' '+p.floorId+'f '+wfCategoryName(p)).includes(query):p.floorId===wfState.floor).filter(p=>wfState.category==='all'||(wfState.category==='rooms'?['room','study'].includes(p.category):!['room','study'].includes(p.category)));
  wf$('#place-list-title').textContent=query?'Search results':'On this floor';wf$('#place-count').textContent=`${items.length} places`;
  wf$('#place-list').innerHTML=items.length?items.map(p=>`<button class="place-row ${wfState.selected===p.id?'active':''}" data-select-place="${p.id}" type="button"><span class="place-type-icon ${p.category}">${wfIcon(p.category)}</span><span class="place-row-text"><strong>${wfEscape(p.name)}</strong><small>${wfCategoryName(p)} · Floor ${p.floorId}</small></span><span class="floor-pill">${p.floorId}F</span></button>`).join(''):'<div class="empty-list"><strong>No places found</strong>Try a room number or another category.</div>';
}
function wfRoomLines(p){
  if(p.category==='vending')return ['Vending',p.name.match(/\d+/)?.[0]||''];
  if(p.category==='escalator')return [p.name.startsWith('Down')?'Down':'Up','escalator'];
  if(p.name.includes('toilet'))return [p.name.split(' ')[0],'toilet'];
  if(p.name.startsWith('Study room'))return ['Study room',p.name.match(/\d+/)?.[0]||''];
  return p.name.length>16?p.name.split(/\s+(?=\S+$)/):[p.name];
}
function wfRenderMap(){
  const floor=MAP_DATA.floors.find(f=>f.id===wfState.floor),svg=wf$('#map-svg');
  const background=wfMedia.get(`floor:${wfState.floor}`);
  let markup=`<title id="map-title">Floor ${wfState.floor} indoor map</title><desc id="map-description">Illustrative indoor layout with clickable rooms and landmarks. ${background?'An imported background is shown; pin positions await calibration.':''}</desc><defs><filter id="floor-shadow" x="-15%" y="-15%" width="130%" height="140%"><feDropShadow dx="0" dy="5" stdDeviation="12" flood-color="#536c47" flood-opacity=".08"/></filter></defs>`;
  markup+='<rect x="52" y="85" width="910" height="540" rx="19" fill="#fff" stroke="#e1e7d9" stroke-width="1.5" filter="url(#floor-shadow)"/>';
  if(background){markup+=`<image href="${background}" x="65" y="95" width="885" height="520" preserveAspectRatio="xMidYMid meet"/>`;}
  else{
    for(const polygon of floor.corridors||[])markup+=`<polygon points="${polygon.map(x=>x.join(',')).join(' ')}" fill="#f7f8f2" stroke="#e6ebdf" stroke-width="1"/>`;
    markup+='<text class="map-hall-label" x="300" y="299" text-anchor="middle">NORTH CORRIDOR</text><text class="map-hall-label" x="330" y="429" text-anchor="middle">SOUTH CORRIDOR</text>';
    for(const a of floor.annotations||[])markup+=`<text x="${a.x}" y="${a.y}" text-anchor="middle" class="map-hall-label" style="font-size:12px;letter-spacing:4px;fill:#bbc4b4">${wfEscape(a.text)}</text>`;
  }
  for(const room of floor.rooms){
    const p=wfPlaces.get(room.placeId),selected=wfState.selected===p.id;
    markup+=`<g class="map-room ${selected?'selected':''}" data-place="${p.id}" tabindex="0" role="button" aria-label="${wfEscape(wfPlaceLabel(p))}"><polygon points="${room.polygon.map(x=>x.join(',')).join(' ')}" fill="${background?'#ffffff45':room.color}"/>`;
    const lines=wfRoomLines(p),small=p.category==='vending';
    markup+=`<text x="${room.labelX}" y="${room.labelY+(small?12:23)}" text-anchor="middle" style="font-size:${small?9:12}px">${lines.map((line,i)=>`<tspan x="${room.labelX}" dy="${i?15:0}">${wfEscape(line)}</tspan>`).join('')}</text></g>`;
  }
  const segments=(wfState.route?.floorSegments||[]).filter(s=>s.floorId===wfState.floor);
  for(const segment of segments){const points=segment.points.map(x=>x.join(',')).join(' ');markup+=`<polyline class="route-halo" points="${points}"/><polyline class="route-line" points="${points}"/>`;}
  for(const p of MAP_DATA.places.filter(p=>p.floorId===wfState.floor)){
    const selected=wfState.selected===p.id,size=p.category==='vending'?10:13;
    markup+=`<g class="map-poi ${selected?'selected':''}" transform="translate(${p.x},${p.y-10})" data-place="${p.id}" tabindex="0" role="button" aria-label="${wfEscape(wfPlaceLabel(p))}">${selected?'<circle class="poi-ring" r="19"/>':''}<circle class="poi-base" r="${size}"/><g class="poi-icon">${wfIcon(p.category,`x="${-size+4}" y="${-size+4}" width="${size*2-8}" height="${size*2-8}"`)}</g></g>`;
  }
  if(wfState.route){
    const start=wfPlaces.get(wfState.route.startPlaceId),end=wfPlaces.get(wfState.route.endPlaceId);
    if(start?.floorId===wfState.floor)markup+=`<circle cx="${start.x}" cy="${start.y}" r="7" class="map-origin"/>`;
    if(end?.floorId===wfState.floor)markup+=`<circle cx="${end.x}" cy="${end.y}" r="7" class="map-destination"/>`;
    const change=wfState.route.edges.find(e=>e.type==='escalator'&&wfNodes.get(e.from).floorId===wfState.floor);
    if(change){const n=wfNodes.get(change.from),to=wfNodes.get(change.to);markup+=`<text class="map-transition-label" x="${n.x-13}" y="${n.y+57}" text-anchor="end">Continue on ${to.floorId}F →</text>`;}
  }
  if(wfState.position){const p=wfPlaces.get(wfState.position.placeId);if(p.floorId===wfState.floor)markup+=`<circle cx="${p.x}" cy="${p.y}" r="25" fill="#4e7ca31c"/><circle cx="${p.x}" cy="${p.y}" r="6" fill="#527caa" stroke="#fff" stroke-width="3"/><text x="${p.x}" y="${p.y-30}" text-anchor="middle" class="map-current-label">${wfState.position.source==='demo'?'Demo position':'Estimated position'}</text>`;}
  svg.innerHTML=markup;svg.setAttribute('viewBox',wfState.view.join(' '));
}
function wfRenderSelected(){
  const card=wf$('#selected-card'),p=wfPlaces.get(wfState.selected);if(!p){card.hidden=true;return;}
  const photo=wfMedia.get(`photo:${p.id}`);card.hidden=false;
  card.innerHTML=`<div class="selected-photo">${photo?`<img src="${photo}" alt="Locally added photo of ${wfEscape(p.name)}">`:'<div class="photo-empty-art"></div><span class="photo-empty-content">'+wfIcon('camera')+'Your landmark photo here</span>'}<button class="icon-button selected-card-close" id="close-selected" type="button" aria-label="Close place details">${wfIcon('close')}</button>${photo?`<button class="photo-edit-button" id="remove-photo" type="button">${wfIcon('close')}Remove photo</button>`:''}</div><div class="selected-content"><div class="selected-category">${wfCategoryName(p)}</div><div class="selected-title-row"><h2>${wfEscape(p.name)}</h2><span class="selected-floor">${p.floorId}F</span></div><p>${wfEscape(p.description||`Find ${p.name} on Floor ${p.floorId}.`)}</p><div class="selected-actions"><button class="primary-button" id="selected-directions" type="button">${wfIcon('route')}Directions${wfIcon('arrow-right')}</button><button class="secondary-button" id="add-photo" type="button" aria-label="${photo?'Change':'Add'} photo for ${wfEscape(p.name)}" title="${photo?'Change':'Add'} photo">${wfIcon('camera')}</button></div></div>`;
  // Keep close reachable when the mobile layout hides the empty photo area.
  if(!photo&&matchMedia('(max-width:700px)').matches){const close=card.querySelector('#close-selected');card.append(close);}
}
function wfResolvePlace(value){
  const normalized=wfNormalize(value.trim());
  if(!normalized)return null;
  const exact=MAP_DATA.places.find(p=>wfNormalize(p.id)===normalized||wfNormalize(wfPlaceLabel(p))===normalized);if(exact)return exact;
  const byName=MAP_DATA.places.filter(p=>wfNormalize(p.name)===normalized);return byName.length===1?byName[0]:null;
}
function wfRouteError(text){wf$('#route-error').textContent=text;wf$('#route-error').hidden=!text;}
function wfRunRoute(){
  const origin=wfResolvePlace(wf$('#origin-input').value),destination=wfResolvePlace(wf$('#destination-input').value);
  if(!origin||!destination){wfRouteError('Choose a starting point and destination from the suggestions. Include the floor for places with the same name.');return false;}
  const route=findRoute(MAP_DATA,origin.id,destination.id);
  if(!['ok','same'].includes(route.status)){wfRouteError(route.status==='unreachable'?'These places are not connected by the current map.':'We couldn’t calculate this route. Please check both places.');return false;}
  wfRouteError('');wfState.origin=origin.id;wfState.destination=destination.id;wfState.route=route;wfState.activeStep=-1;
  wf$('#origin-input').value=wfPlaceLabel(origin);wf$('#destination-input').value=wfPlaceLabel(destination);wfSetFloor(origin.floorId);wfState.selected=null;wfRenderSelected();wfRenderRoute();wfRenderMap();return true;
}
function wfRenderRoute(){
  const route=wfState.route;wf$('#route-empty').hidden=Boolean(route);wf$('#route-result').hidden=!route;if(!route)return;
  const end=wfPlaces.get(route.endPlaceId),same=route.status==='same';
  wf$('#route-result').innerHTML=`<div class="route-summary"><div class="eyebrow">${same?'YOU’RE ALREADY THERE':'YOUR ROUTE PREVIEW'}</div><h2>${same?wfEscape(end.name):`To ${wfEscape(end.name)}`}</h2><p>${same?'Your starting point and destination are the same.':'Follow the highlighted corridor. Tap a step to view its floor.'}</p><div class="route-summary-badges"><span class="floor-change-badge">${route.floorChanges?`${route.floorChanges} floor change${route.floorChanges===1?'':'s'}`:'Same floor'}</span><span>${route.distanceMeters===null?'Distance awaiting map scale':`${Math.round(route.distanceMeters)} m`}</span></div></div><ol class="route-steps">${route.steps.map((step,i)=>{const symbol=step.type==='floor-change'?'escalator':step.type==='arrive'?'flag':step.type==='start'?'locate':step.text.toLowerCase().includes('left')?'turn-left':step.text.toLowerCase().includes('right')?'turn-right':'arrow-right';return `<li class="route-step ${wfState.activeStep===i?'active':''}" data-route-step="${i}" tabindex="0" role="button" aria-label="Step ${i+1}: ${wfEscape(step.text)}"><span class="route-step-icon">${wfIcon(symbol)}</span><span class="route-step-text"><strong>${wfEscape(step.text)}</strong><small>Floor ${step.floorId}</small></span></li>`;}).join('')}</ol><div class="route-preview-controls">${same?'':`<button class="secondary-button" id="preview-route" type="button">${wfIcon('route')}${wfState.activeStep<0?'Preview steps':'Next step'}</button>`}<button class="secondary-button" id="clear-route" type="button">Clear route</button></div>${same?'':'<p class="preview-status">Step preview · not live navigation</p>'}`;
}
function wfShowStep(index){if(!wfState.route)return;const step=wfState.route.steps[index];if(!step)return;wfState.activeStep=index;wfSetFloor(step.floorId);wfRenderRoute();if(index===wfState.route.steps.length-1)wfToast(`Preview complete: ${wfPlaces.get(wfState.route.endPlaceId).name}`);}
function wfClearRoute(){wfState.route=null;wfState.activeStep=-1;wfRenderRoute();wfRenderMap();wfRouteError('');}
function wfStartDirections(id){const p=wfPlaces.get(id);wfState.destination=id;wf$('#destination-input').value=wfPlaceLabel(p);wfSetPanel('directions');wfState.selected=null;wfRenderSelected();if(wfResolvePlace(wf$('#origin-input').value))wfRunRoute();else wf$('#origin-input').focus();}
function wfSetPosition({placeId,source='sensor-model',confidence}={}){
  if(!wfPlaces.has(placeId))throw new TypeError('Position must reference a known map placeId.');
  if(source==='demo')confidence=undefined;
  wfState.position={placeId,source,...(Number.isFinite(confidence)?{confidence}:{} )};wfState.origin=placeId;
  wf$('#origin-input').value=wfPlaceLabel(wfPlaces.get(placeId));
  const note=wf$('#position-note');note.hidden=false;note.textContent=source==='demo'?'Demo starting point · not your detected location':'Starting point supplied by the indoor positioning adapter';
  wfSetPanel('directions');wfSetFloor(wfPlaces.get(placeId).floorId);wfRenderMap();if(wfResolvePlace(wf$('#destination-input').value))wfRunRoute();
}
function wfZoom(factor){const v=wfState.view,w=Math.min(1700,Math.max(360,v[2]*factor)),h=w*.7;wfState.view=[v[0]+(v[2]-w)/2,v[1]+(v[3]-h)/2,w,h];wfRenderMap();}
function wfRenderSetup(){const has=wfMedia.has(`floor:${wfState.floor}`);wf$('#setup-floor-name').textContent=`Floor ${wfState.floor}`;wf$('#floor-image-status').textContent=has?'Your background image · positions uncalibrated':'Illustrative floor plan';wf$('#choose-floor-image').textContent=has?'Replace image':'Add image';wf$('#remove-floor-image').hidden=!has;}
async function wfOpenStorage(){
  if(!('indexedDB' in window)){wf$('#storage-note').textContent='Browser storage is unavailable. Images last for this session only.';return;}
  try{wfDb=await new Promise((resolve,reject)=>{const req=indexedDB.open('wayfind-local-media',1);req.onupgradeneeded=()=>{req.result.createObjectStore('media');};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});
    await new Promise((resolve,reject)=>{const tx=wfDb.transaction('media','readonly'),s=tx.objectStore('media'),req=s.openCursor();req.onsuccess=()=>{const cursor=req.result;if(cursor){if(typeof cursor.value==='string'&&cursor.value.startsWith('data:image/'))wfMedia.set(cursor.key,cursor.value);cursor.continue();}};tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});
  }catch{wfDb=null;wf$('#storage-note').textContent='Browser storage is unavailable. Images last for this session only.';}
}
async function wfSaveMedia(key,data){wfMedia.set(key,data);if(!wfDb){wfToast('Image added for this session. Browser storage is unavailable.');return;}
  try{await new Promise((resolve,reject)=>{const tx=wfDb.transaction('media','readwrite');tx.objectStore('media').put(data,key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});wfToast('Image saved in this browser.');}catch{wfToast('Image added for this session. Browser storage is full or unavailable.');}}
async function wfRemoveMedia(key){wfMedia.delete(key);if(wfDb)try{await new Promise((resolve,reject)=>{const tx=wfDb.transaction('media','readwrite');tx.objectStore('media').delete(key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});}catch{wfToast('Image removed for this session; the saved copy could not be cleared.');}}
async function wfImageData(file){
  if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('Choose a PNG, JPEG or WebP image.');
  if(file.size>25*1024*1024)throw new Error('Choose an image smaller than 25 MB.');
  const url=URL.createObjectURL(file);
  try{const image=await new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(new Error('This image could not be opened.'));im.src=url;});const scale=Math.min(1,1600/Math.max(image.width,image.height)),canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));const ctx=canvas.getContext('2d');if(!ctx)throw new Error('Image conversion is unavailable in this browser.');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);return canvas.toDataURL('image/jpeg',.86);}finally{URL.revokeObjectURL(url);}
}
function wfBindEvents(){
  document.addEventListener('click',event=>{
    const t=event.target.closest('button,[data-route-step]');if(!t)return;
    if(t.dataset.selectPlace){wfSelectPlace(t.dataset.selectPlace);return;}
    if(t.dataset.category){wfState.category=t.dataset.category;document.querySelectorAll('[data-category]').forEach(b=>{b.classList.toggle('active',b===t);b.setAttribute('aria-pressed',String(b===t));});wfRenderPlaces();return;}
    if(t.dataset.floor){wfSetFloor(t.dataset.floor);return;}
    if(t.dataset.closeDialog){wfCloseDialog(t.dataset.closeDialog);return;}
    if(t.dataset.routeStep!==undefined){wfShowStep(Number(t.dataset.routeStep));return;}
    switch(t.id){
      case'explore-tab':wfSetPanel('explore');break;case'directions-tab':wfSetPanel('directions');break;
      case'close-selected':wfState.selected=null;wfRenderSelected();wfRenderMap();wfRenderPlaces();break;
      case'selected-directions':wfStartDirections(wfState.selected);break;
      case'add-photo':wfPhotoTarget=wfState.selected;wf$('#photo-input').click();break;
      case'remove-photo':wfRemoveMedia(`photo:${wfState.selected}`).then(wfRenderSelected);break;
      case'zoom-in':wfZoom(.8);break;case'zoom-out':wfZoom(1.25);break;
      case'fit-map':wfState.view=[0,0,1000,700];wfRenderMap();break;
      case'locate-button':wfOpenDialog('location-dialog');break;
      case'try-demo-location':wfCloseDialog('location-dialog');wfSetPosition({placeId:'f5-exit-5',source:'demo'});wfToast('Demo location set to Exit 5 on Floor 5.');break;
      case'setup-button':wfRenderSetup();wfOpenDialog('setup-dialog');break;
      case'help-button':wfOpenDialog('help-dialog');break;
      case'choose-floor-image':wfImageFloor=wfState.floor;wf$('#floor-image-input').click();break;
      case'remove-floor-image':wfRemoveMedia(`floor:${wfState.floor}`).then(()=>{wfRenderMap();wfRenderSetup();});break;
      case'example-route':wf$('#origin-input').value=wfPlaceLabel(wfPlaces.get('f5-exit-5'));wf$('#destination-input').value=wfPlaceLabel(wfPlaces.get('f4-y4052'));wfRunRoute();break;
      case'swap-button':{const a=wf$('#origin-input').value;wf$('#origin-input').value=wf$('#destination-input').value;wf$('#destination-input').value=a;wfState.position=null;wf$('#position-note').hidden=true;if(wfState.route)wfRunRoute();break;}
      case'clear-route':wfClearRoute();break;
      case'preview-route':wfShowStep((wfState.activeStep+1)%wfState.route.steps.length);break;
    }
  });
  wf$('#explore-search').addEventListener('input',event=>{wfState.search=event.target.value;wfRenderPlaces();});
  wf$('#origin-input').addEventListener('input',()=>{wfState.position=null;wf$('#position-note').hidden=true;wfClearRoute();});
  wf$('#destination-input').addEventListener('input',()=>wfClearRoute());
  wf$('#route-form').addEventListener('submit',event=>{event.preventDefault();wfRunRoute();});
  wf$('#map-svg').addEventListener('click',event=>{if(wfDragged){wfDragged=false;return;}const p=event.target.closest('[data-place]');if(p)wfSelectPlace(p.dataset.place,{moveFloor:false});});
  wf$('#map-svg').addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){const p=event.target.closest('[data-place]');if(p){event.preventDefault();wfSelectPlace(p.dataset.place,{moveFloor:false});}}});
  document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)){event.preventDefault();wfSetPanel('explore');wf$('#explore-search').focus();}if(['Enter',' '].includes(event.key)&&event.target.dataset.routeStep!==undefined){event.preventDefault();wfShowStep(Number(event.target.dataset.routeStep));}});
  const canvas=wf$('#map-canvas');canvas.addEventListener('pointerdown',event=>{if(event.target.closest('[data-place]'))return;wfDrag={x:event.clientX,y:event.clientY,view:[...wfState.view]};wfDragged=false;canvas.setPointerCapture?.(event.pointerId);canvas.classList.add('dragging');});
  canvas.addEventListener('pointermove',event=>{if(!wfDrag)return;const rect=canvas.getBoundingClientRect(),dx=event.clientX-wfDrag.x,dy=event.clientY-wfDrag.y;if(Math.abs(dx)+Math.abs(dy)>5)wfDragged=true;wfState.view=[wfDrag.view[0]-dx/rect.width*wfDrag.view[2],wfDrag.view[1]-dy/rect.height*wfDrag.view[3],wfDrag.view[2],wfDrag.view[3]];wf$('#map-svg').setAttribute('viewBox',wfState.view.join(' '));});
  for(const name of ['pointerup','pointercancel'])canvas.addEventListener(name,()=>{wfDrag=null;canvas.classList.remove('dragging');});
  canvas.addEventListener('wheel',event=>{if(event.ctrlKey||event.metaKey){event.preventDefault();wfZoom(event.deltaY>0?1.12:.89);}},{passive:false});
  wf$('#photo-input').addEventListener('change',async event=>{const file=event.target.files?.[0],id=wfPhotoTarget;event.target.value='';if(!file||!id)return;try{await wfSaveMedia(`photo:${id}`,await wfImageData(file));if(wfState.selected===id)wfRenderSelected();}catch(error){wfToast(error.message);}});
  wf$('#floor-image-input').addEventListener('change',async event=>{const file=event.target.files?.[0],floor=wfImageFloor;event.target.value='';if(!file||!floor)return;try{await wfSaveMedia(`floor:${floor}`,await wfImageData(file));wfRenderMap();wfRenderSetup();}catch(error){wfToast(error.message);}});
  window.addEventListener('resize',()=>wfRenderSelected());
}
async function wfInit(){
  wfHydrateIcons();wf$('#place-options').innerHTML=MAP_DATA.places.map(p=>`<option value="${wfEscape(wfPlaceLabel(p))}"></option>`).join('');
  wfBindEvents();wfRenderFloorControls();wfRenderPlaces();wfRenderMap();wfRenderSelected();await wfOpenStorage();wfRenderMap();wfRenderSelected();
}
window.Wayfind=Object.freeze({
  setPosition:wfSetPosition,
  clearPosition(){wfState.position=null;wf$('#position-note').hidden=true;wfRenderMap();},
  setDestination(placeId){if(!wfPlaces.has(placeId))throw new TypeError('Unknown destination placeId.');wfStartDirections(placeId);},
  route(startPlaceId,endPlaceId){if(!wfPlaces.has(startPlaceId)||!wfPlaces.has(endPlaceId))throw new TypeError('Unknown route placeId.');wf$('#origin-input').value=wfPlaceLabel(wfPlaces.get(startPlaceId));wf$('#destination-input').value=wfPlaceLabel(wfPlaces.get(endPlaceId));wfSetPanel('directions');return wfRunRoute();},
  getState(){return {floor:wfState.floor,selected:wfState.selected,origin:wfState.origin,destination:wfState.destination,position:wfState.position?{...wfState.position}:null,route:wfState.route?{status:wfState.route.status,nodeIds:[...wfState.route.nodeIds],floorChanges:wfState.route.floorChanges}:null};},
});
wfInit();

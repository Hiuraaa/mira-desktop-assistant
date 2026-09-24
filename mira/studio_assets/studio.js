import * as THREE from '/assets/vendor/three.module.js';
import { GLTFLoader } from '/assets/vendor/loaders/GLTFLoader.js';

const $ = (id) => document.getElementById(id);
const token = new URLSearchParams(location.hash.slice(1)).get('session') || sessionStorage.getItem('miraSession');
if (token) { sessionStorage.setItem('miraSession', token); history.replaceState(null, '', location.pathname); }
let state = null, screenshot = '', chatting = false, running = false;
let screenshotUrl = '';
let scene, renderer, camera, actor, fallback, head, arms, eyes = [], mouth, humanoid = {}, expressions = {};
let mood = 'idle', rotation = 0, drag = 0, lastX = 0, lastY = 0, zoom = 3.7;
let toastTimer;

function notify(message) { const node = $('toast'); node.textContent = message; node.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => node.classList.remove('show'), 5200); }
function clearPreview(){screenshot='';$('attachment').hidden=true;$('screenPreview').removeAttribute('src');
  if(screenshotUrl){URL.revokeObjectURL(screenshotUrl);screenshotUrl='';}}
function setMood(next, message) { mood = next; $('mood').textContent = ({idle:'ĐANG LẮNG NGHE', thinking:'ĐANG SUY NGHĨ', speaking:'ĐANG TRẢ LỜI', doing:'ĐANG THAO TÁC'})[next] || next;
  $('stageMessage').textContent = message || ({idle:'Ở đây với bạn.',thinking:'Đang tìm lời phù hợp…',speaking:'Mình đang nói đây.',doing:'Đã xin quyền để thao tác.'})[next]; }
async function request(path, data = undefined) {
  const res = await fetch(path, {method:data === undefined ? 'GET':'POST', headers:{'X-Mira-Session':token,...(data === undefined ? {} : {'Content-Type':'application/json'})},
    ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  if (!res.ok) { let message = `Mira báo lỗi ${res.status}`; try { message = (await res.json()).error || message; } catch (_) {} throw new Error(message); }
  return res.json();
}
async function run(action) { try { await action(); } catch (error) { notify(error.message || String(error)); } }

function material(color, roughness=.86) { return new THREE.MeshStandardMaterial({color, roughness}); }
function part(parent, geo, mat, x,y,z, sx=1,sy=1,sz=1) { const mesh = new THREE.Mesh(geo,mat);
  mesh.position.set(x,y,z); mesh.scale.set(sx,sy,sz); mesh.castShadow=true; parent.add(mesh); return mesh; }
function defaultMira() {
  const group = new THREE.Group(), hair = material('#9984d6'), shadow=material('#705baf'), skin=material('#ffd7d2'), eye=material('#473760');
  const top=material('#eee7ff'), jacket=material('#5c528a'), violet=material('#ae92e5');
  const sphere=new THREE.SphereGeometry(1,20,16), cube=new THREE.BoxGeometry(1,1,1), cone=new THREE.ConeGeometry(1,1,20);
  part(group,new THREE.CylinderGeometry(.32,.42,.83,20),jacket,0,.98,0);
  part(group,cone,jacket,0,.57,0, .48,.45,.48).rotation.z=Math.PI;
  part(group,cube,top,0,1.16,.33,.42,.15,.05).rotation.z=Math.PI/4;
  const ribbon=part(group,sphere,violet,0,1.07,.42,.1,.11,.07); ribbon.castShadow=false;
  for (const side of [-1,1]) {
    part(group,new THREE.CylinderGeometry(.15,.12,.56,12),skin,side*.20,.37,0);
    part(group,sphere,shadow,side*.20,.12,.08,.15,.10,.18);
  }
  arms=[];
  for (const side of [-1,1]) {
    const pivot=new THREE.Group(); pivot.position.set(side*.37,1.34,-.02); group.add(pivot); arms.push(pivot);
    part(pivot,new THREE.CylinderGeometry(.115,.17,.57,12),jacket,side*.05,-.28,0).rotation.z=side*.12;
    part(pivot,sphere,skin,side*.10,-.60,.01,.13,.14,.12);
  }
  part(group,sphere,shadow,0,1.85,-.12,.61,.68,.48);
  head=new THREE.Group(); head.position.set(0,1.78,.04); group.add(head);
  part(head,sphere,skin,0,0,.12,.41,.51,.34);
  part(head,sphere,hair,0,.28,-.04,.46,.36,.40);
  for (const side of [-1,1]) {
    part(head,sphere,hair,side*.37,.03,-.01,.15,.47,.26);
    part(head,sphere,eye,side*.16,.08,.422,.053,.074,.023);
    eyes.push(part(head,sphere,material('#fff7ff'),side*.17,.11,.446,.016,.021,.008));
    part(head,sphere,skin,side*.39,-.08,.16,.08,.12,.08);
  }
  for (const side of [-1,1]) part(head,sphere,hair,side*.16,.35,.29,.20,.17,.21);
  part(head,sphere,violet,-.30,.47,.18,.12,.1,.12);
  mouth=part(head,sphere,eye,0,-.20,.45,.048,.024,.012);
  return group;
}
function startScene() {
  const canvas=$('stageCanvas');
  try { renderer = new THREE.WebGLRenderer({canvas,alpha:true,antialias:false,powerPreference:'low-power'}); }
  catch (error) { notify('Trình duyệt không bật được WebGL. Hãy dùng Edge/Chrome và bật tăng tốc đồ họa.'); return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1,1.4));
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  scene=new THREE.Scene(); camera=new THREE.PerspectiveCamera(36,1,.01,80); camera.position.set(0,1.33,zoom); camera.lookAt(0,1.17,0);
  scene.add(new THREE.HemisphereLight('#e6dbff','#7f6aa6',2.1)); const light=new THREE.DirectionalLight('#fff1ee',2.3);light.position.set(1.8,3,4);scene.add(light);
  const rim=new THREE.DirectionalLight('#b492ff',1.9);rim.position.set(-2,2,-3);scene.add(rim);
  const podium=part(scene,new THREE.CylinderGeometry(.95,1.05,.12,32),material('#39314f'),0,-.07,0);podium.castShadow=false;
  fallback=defaultMira(); scene.add(fallback);actor=fallback;
  canvas.addEventListener('pointerdown',e=>{drag=1;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(drag){rotation+=(e.clientX-lastX)*.009;lastX=e.clientX;lastY=e.clientY;}});
  canvas.addEventListener('pointerup',()=>drag=0);canvas.addEventListener('pointercancel',()=>drag=0);
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(2.15,Math.min(6.2,zoom+e.deltaY*.003));},{passive:false});
  let last=0;
  function frame(ms){requestAnimationFrame(frame);if(document.hidden || ms-last<32)return;last=ms;
    const {width,height}=canvas.getBoundingClientRect();if(width<1||height<1)return;
    const w=Math.floor(width),h=Math.floor(height);if(canvas.width !== Math.floor(w*renderer.getPixelRatio())||canvas.height !== Math.floor(h*renderer.getPixelRatio())) {
      renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();}
    camera.position.z=zoom;camera.lookAt(0,1.17,0);
    if(actor) {actor.rotation.y+=(((actor===fallback?0:Math.PI)+rotation)-actor.rotation.y)*.06;
      const now=ms*.001,blink=(now%4.25>4.09)? .06:1;
      if(actor===fallback){head.rotation.y=Math.sin(now*.8)*.065;head.rotation.x=mood==='thinking'?.10:Math.sin(now*.9)*.026;
        arms[0].rotation.z=Math.sin(now*.95)*.05;arms[1].rotation.z=-arms[0].rotation.z;
        eyes.forEach(eye=>eye.scale.y=blink*.021);mouth.scale.y=(mood==='speaking'?.05+Math.abs(Math.sin(now*10))*.055:.024);}
      else {const node=humanoid.head;if(node){node.rotation.y=Math.sin(now*.8)*.06;node.rotation.x=mood==='thinking'?.07:0;}
        const arm=humanoid.leftUpperArm;if(arm)arm.rotation.z=Math.sin(now*.65)*.025;
        for(const [name,amount] of Object.entries({blink:1-blink,aa:mood==='speaking'?.22+Math.abs(Math.sin(now*9))*.45:0}))
          (expressions[name]||[]).forEach(({mesh,index,weight})=>{mesh.morphTargetInfluences[index]=amount*weight;});}
    }
    renderer.render(scene,camera);
  } requestAnimationFrame(frame);
}
async function loadVRM() {
  const res=await fetch('/api/model',{headers:{'X-Mira-Session':token}});if(!res.ok){$('avatarLabel').textContent='Nhân vật 3D mặc định';return;}
  const content=await res.arrayBuffer();const loader=new GLTFLoader();
  const gltf=await new Promise((resolve,reject)=>loader.parse(content,'',resolve,reject));
  const root=gltf.scene; if(!root)throw new Error('VRM không chứa cảnh ba chiều.');
  const bounds=new THREE.Box3().setFromObject(root); const dim=new THREE.Vector3();bounds.getSize(dim);
  if(!Number.isFinite(dim.y)||dim.y<=.001||dim.y>10000)throw new Error('Kích thước model không hợp lệ.');
  const scale=2.28/dim.y;root.scale.setScalar(scale);
  root.position.set(-bounds.min.x*scale-dim.x*scale/2,-bounds.min.y*scale,-bounds.min.z*scale-dim.z*scale/2);
  const pivot=new THREE.Group();pivot.add(root);scene.remove(actor); actor=pivot;scene.add(actor);
  const ext=gltf.parser.json.extensions || {};const v1=ext.VRMC_vrm, v0=ext.VRM;
  humanoid={};expressions={};
  const bones=v1?.humanoid?.humanBones || v0?.humanoid?.humanBones || {};
  const names=['head','leftUpperArm','rightUpperArm'];
  for(const name of names){const index=Array.isArray(bones)?bones.find(b=>b.bone===name)?.node:bones[name]?.node;
    if(Number.isInteger(index))humanoid[name]=await gltf.parser.getDependency('node',index);}
  const presets=v1?.expressions?.preset||{};
  for(const name of ['blink','aa']) { const binds=presets[name]?.morphTargetBinds||[];expressions[name]=[];
    for(const bind of binds){const node=await gltf.parser.getDependency('node',bind.node);node?.traverse(mesh=>{
      if(mesh.morphTargetInfluences && bind.index<mesh.morphTargetInfluences.length)
        expressions[name].push({mesh,index:bind.index,weight:bind.weight ?? 1});});}}
  $('avatarLabel').textContent='Model VRM '+(v1?'1.0':'0.x')+' của bạn';notify('Đã tải nhân vật VRM lên sân khấu 3D.');
}

function bubble(role,text){const block=document.createElement('div');block.className='bubble'+(role==='user'?' me':'');const title=document.createElement('span');title.className='speaker';title.textContent=role==='user'?'BẠN':'✦ MIRA';const content=document.createElement('span');content.textContent=text;block.append(title,content);$('messages').append(block);$('messages').scrollTop=$('messages').scrollHeight;return content;}
function renderHistory(){const feed=$('messages');feed.replaceChildren();const items=state.messages||[];
  if(!items.length)bubble('assistant','Chào bạn, mình là Mira. Bạn có thể chọn VRM để gặp mình trên sân khấu, hoặc dạy mình một thao tác game ở bên dưới.');
  for(const item of items)bubble(item.role,item.content);}
function renderLists(){const list=$('lessonList');list.replaceChildren();
  for(const lesson of state.lessons||[]){const row=document.createElement('div');row.className='lesson-item';const info=document.createElement('div');
    const name=document.createElement('strong');name.textContent=lesson.name;const size=document.createElement('small');size.textContent=lesson.steps.length+' bước · /play '+lesson.name;
    info.append(name,size);const buttons=document.createElement('div');buttons.className='small-actions';const play=document.createElement('button');play.textContent='▶ Thử';play.addEventListener('click',()=>run(()=>playLesson(lesson.id)));
    const remove=document.createElement('button');remove.className='delete';remove.textContent='Xóa';remove.addEventListener('click',()=>run(async()=>{await request('/api/delete-lesson',{id:lesson.id});await refresh();}));buttons.append(play,remove);row.append(info,buttons);list.append(row);}
  if(!state.lessons?.length){const empty=document.createElement('span');empty.className='muted';empty.textContent='Chưa có bài học nào.';list.append(empty);}
  const memo=$('memoryList');memo.replaceChildren();for(const item of [...(state.memories||[])].reverse()){const row=document.createElement('div');row.className='memory-item';const text=document.createElement('span');text.textContent=item.text;const remove=document.createElement('button');remove.textContent='Quên';remove.addEventListener('click',()=>run(async()=>{await request('/api/forget',{id:item.id});await refresh();}));row.append(text,remove);memo.append(row);}
  const chats=$('chatList');chats.replaceChildren();for(const item of state.chats||[]){const btn=document.createElement('button');btn.className='chat-entry'+(item.id===state.chat_id?' current':'');btn.textContent=item.title;btn.addEventListener('click',()=>run(async()=>{await request('/api/select-chat',{id:item.id});await refresh();}));chats.append(btn);}
}
async function refresh(){state=await request('/api/state');$('stageName').textContent=state.name||'Mira';$('modelBadge').textContent=state.model||'Chưa chọn AI';$('chatSubtitle').textContent=state.model||'Chưa chọn AI';
  $('toggleControl').textContent=state.desktop_enabled?'Tắt quyền thao tác':'Bật quyền thao tác';$('targetStatus').textContent=state.target||'Chưa chọn game';renderHistory();renderLists();
  if(state.model_loaded&&actor===fallback)loadVRM().catch(error=>notify('VRM không mở được: '+error.message));}
async function playLesson(id){if(running)return;running=true;setMood('doing');try{const result=await request('/api/run',{id});notify(result.result);}
  finally{running=false;setMood('idle');}}
function addStep(){if($('steps').children.length>=10){notify('Tối đa 10 bước.');return;}const row=document.createElement('div');row.className='step-row';
  const kind=document.createElement('select');kind.setAttribute('aria-label','Loại thao tác');for(const [v,label] of [['press','Bấm'],['hold','Giữ']])kind.add(new Option(label,v));
  const key=document.createElement('select');key.setAttribute('aria-label','Phím');for(const option of 'w a s d q e r f c v 1 2 3 4 5 6 7 8 9 0 space enter esc shift ctrl tab up down left right'.split(' '))key.add(new Option(option.toUpperCase(),option));
  const duration=document.createElement('input');duration.className='duration';duration.type='number';duration.min='.05';duration.max='2';duration.step='.05';duration.value='.3';duration.title='Thời gian giữ phím (giây)';duration.hidden=true;
  kind.addEventListener('change',()=>{duration.hidden=kind.value!=='hold';});const del=document.createElement('button');del.className='remove-step';del.textContent='×';del.setAttribute('aria-label','Xóa bước');del.addEventListener('click',()=>row.remove());row.append(kind,key,duration,del);$('steps').append(row);}
async function send(){if(chatting)return;const prompt=$('prompt').value.trim();if(!prompt)return;
  if(prompt.toLowerCase().startsWith('/play ')){const name=prompt.slice(6).trim().toLowerCase();const lesson=(state.lessons||[]).find(item=>item.name.toLowerCase()===name);
    if(!lesson){notify('Không tìm thấy bài học. Hãy gõ đúng /play <tên bài học>.');return;}$('prompt').value='';await run(()=>playLesson(lesson.id));return;}
  chatting=true;$('send').disabled=true;$('prompt').value='';bubble('user',prompt+(screenshot?'\n[Đính kèm màn hình]':''));const content=bubble('assistant','');
  setMood('thinking');const ticket=screenshot;clearPreview();
  try{const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Mira-Session':token},body:JSON.stringify({text:prompt,screen_ticket:ticket})});
    if(!response.ok){const json=await response.json();throw new Error(json.error||`Lỗi ${response.status}`);}
    const reader=response.body.getReader(),decode=new TextDecoder();let buffer='',answer='';
    while(true){const {value,done}=await reader.read();if(done)break;buffer+=decode.decode(value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop();
      for(const line of lines)if(line.trim()){const item=JSON.parse(line);if(item.type==='token'){content.textContent+=item.text;setMood('speaking');$('messages').scrollTop=$('messages').scrollHeight;}
        if(item.type==='done'){answer=item.answer;content.textContent=answer;}
        if(item.type==='error')throw new Error(item.error);}}
    if(!answer&&buffer.trim()){const item=JSON.parse(buffer);if(item.type==='done'){answer=item.answer;content.textContent=answer;}}
    if(answer&&$('readAloud').checked&&'speechSynthesis'in window){speechSynthesis.cancel();const speech=new SpeechSynthesisUtterance(answer);speech.lang='vi-VN';speechSynthesis.speak(speech);}
    const old=state.chat_id;state=await request('/api/state');if(state.chat_id===old)renderLists();
  }catch(error){content.textContent='Mira không trả lời được: '+error.message;notify(error.message);}finally{chatting=false;$('send').disabled=false;setMood('idle');$('prompt').focus();}}

function bind(){for(const btn of document.querySelectorAll('[data-scroll]'))btn.addEventListener('click',()=>$(btn.dataset.scroll).scrollIntoView({behavior:'smooth'}));
  $('refreshState').addEventListener('click',()=>run(refresh));$('desktopWindow').addEventListener('click',()=>run(async()=>{await request('/api/desktop-window',{});notify('Đã mở cửa sổ Mira trên PC.');}));
  $('newChat').addEventListener('click',()=>run(async()=>{await request('/api/new-chat',{});await refresh();}));
  $('turnModel').addEventListener('click',()=>{rotation+=Math.PI;});
  $('vrmInput').addEventListener('change',()=>run(async()=>{const file=$('vrmInput').files[0];if(!file)return;
    if(!file.name.toLowerCase().endsWith('.vrm')||file.size>20*1024*1024)throw new Error('Chỉ chọn file .vrm dưới 20 MiB.');
    $('avatarLabel').textContent='Đang tải '+file.name+'…';const res=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'model/gltf-binary','X-Mira-Session':token},body:file});
    if(!res.ok)throw new Error((await res.json()).error);await loadVRM();$('vrmInput').value='';}));
  $('toggleControl').addEventListener('click',()=>run(async()=>{await request('/api/desktop',{});await refresh();}));
  $('selectGame').addEventListener('click',()=>run(async()=>{notify('Trong 3 giây tới, chuyển sang cửa sổ game bạn muốn Mira điều khiển.');const result=await request('/api/target',{});notify('Đã chọn: '+result.title);await refresh();}));
  $('stopLesson').addEventListener('click',()=>run(async()=>{await request('/api/stop',{});notify('Đã gửi tín hiệu dừng và thả phím đang giữ.');setMood('idle');}));
  $('addStep').addEventListener('click',addStep);addStep();
  $('saveLesson').addEventListener('click',()=>run(async()=>{const name=$('lessonName').value.trim();const steps=[...$('steps').children].map(row=>({kind:row.children[0].value,key:row.children[1].value,duration:row.children[0].value==='hold'?Number(row.children[2].value):0}));
    await request('/api/teach',{name,steps});$('lessonName').value='';$('steps').replaceChildren();addStep();await refresh();notify('Đã lưu bài học. Có thể gõ /play '+name+' trong chat.');}));
  $('saveMemory').addEventListener('click',()=>run(async()=>{await request('/api/memory',{text:$('memoryInput').value.trim()});$('memoryInput').value='';await refresh();notify('Mira đã ghi nhớ.');}));
  $('captureScreen').addEventListener('click',()=>run(async()=>{notify('Mira sẽ xin phép trên PC, sau đó bạn có 2 giây chuyển sang game để chụp.');const result=await request('/api/screenshot',{});
    clearPreview();screenshot=result.ticket;const preview=await fetch('/api/screen?ticket='+encodeURIComponent(screenshot),{headers:{'X-Mira-Session':token}});
    if(!preview.ok)throw new Error('Ảnh xem trước không còn sẵn sàng.');screenshotUrl=URL.createObjectURL(await preview.blob());
    $('screenPreview').src=screenshotUrl;$('attachment').hidden=false;$('attachmentLabel').textContent='Ảnh sắp gửi cho Mira';notify('Xem trước ảnh rồi bấm Gửi nếu đúng màn hình bạn muốn chia sẻ.');}));
  $('clearScreen').addEventListener('click',clearPreview);
  $('send').addEventListener('click',()=>run(send));$('prompt').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();run(send);}});
}

bind();if(!token)notify('Hãy mở Studio từ ứng dụng Mira để kết nối.');
else{startScene();run(refresh);}

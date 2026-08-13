(() => {
  const mode = document.body.classList.contains("afk") ? "afk" : "compact";
  const lake = document.getElementById("lake");
  const boats = document.getElementById("boats");
  const weather = document.getElementById("weather");
  const label = document.getElementById("weatherLabel");
  const banner = document.getElementById("banner");
  const powerStatus = document.getElementById("fishingPower");
  const pointsLeaderboard = document.getElementById("pointsLeaderboard");
  const nodes = new Map();
  const seen = new Set();
  let retry = 1000;

  function hash(s){let h=2166136261;for(const c of String(s)){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return h>>>0}
  function position(a){const h=hash(a.user_id);return mode==="compact"?{x:6+(h%86),y:1026+((h>>>8)%3)}:{x:6+(h%82),y:390+((h>>>8)%490)}}
  const centralIsland={left:650,right:1090,top:560,bottom:780};
  function safeBoatPoint(point){if(mode!=="afk")return point;const px=point.x*19.2;if(px>centralIsland.left&&px<centralIsland.right&&point.y>centralIsland.top&&point.y<centralIsland.bottom)return{x:point.x,y:point.y<(centralIsland.top+centralIsland.bottom)/2?520:820};return point}
  function pathHitsIsland(from,to){if(mode!=="afk")return false;for(let i=0;i<=40;i++){const t=i/40,x=(from.x+(to.x-from.x)*t)*19.2,y=from.y+(to.y-from.y)*t;if(x>centralIsland.left&&x<centralIsland.right&&y>centralIsland.top&&y<centralIsland.bottom)return true}return false}
  function faceBoat(el,next){const current=Number(el.dataset.x||next.x);el.classList.toggle("facing-left",next.x<current)}
  function placeBoatAt(el,next){faceBoat(el,next);el.dataset.x=String(next.x);el.dataset.y=String(next.y);el.style.left=`calc(${next.x}% - ${mode==="compact"?52:75}px)`;if(mode==="afk"){el.style.top=`${next.y}px`;el.style.zIndex=String(100+Math.round(next.y))}}
  function moveBoatTo(el,requested){const destination=safeBoatPoint(requested),current={x:Number(el.dataset.x||destination.x),y:Number(el.dataset.y||destination.y)};el.classList.add("moving");animateFishingLine(el);if(mode==="afk"&&pathHitsIsland(current,destination)){const aboveCost=Math.abs(current.y-520)+Math.abs(destination.y-520),belowCost=Math.abs(current.y-820)+Math.abs(destination.y-820),routeY=aboveCost<=belowCost?520:820,legs=[{x:current.x,y:routeY},{x:destination.x,y:routeY},destination];el.classList.add("routing");legs.forEach((leg,index)=>setTimeout(()=>placeBoatAt(el,leg),index*2050));setTimeout(()=>el.classList.remove("moving","routing"),6300)}else{placeBoatAt(el,destination);setTimeout(()=>el.classList.remove("moving"),mode==="afk"?5600:3300)}}
  function sendBoatAway(el,id){const left=(hash(id+"departure")&1)===0;el.classList.add("moving");placeBoatAt(el,{x:left?-8:108,y:Number(el.dataset.y||1026)});setTimeout(()=>{el.remove();nodes.delete(id)},mode==="afk"?5700:3400)}
  function welcomeBoat(a){if(!a||!a.active)return;const destination=safeBoatPoint(position(a)),startLeft=(hash(a.user_id+"return")&1)===0;a={...a};boat(a);const el=nodes.get(a.user_id);placeBoatAt(el,{x:startLeft?-8:108,y:destination.y});requestAnimationFrame(()=>requestAnimationFrame(()=>moveBoatTo(el,destination)))}
  function compactNumber(value){const n=Number(value)||0;if(n<1000)return String(n);return `${Math.floor(n/100)/10}K`}
  function showGps(p){const el=nodes.get(p.user_id);if(!el)return;const pin=document.createElement("div");pin.className="gps-pin";pin.innerHTML=`<span class="gps-name"></span><span class="medal-badge ${p.medal_tier||"bronze"}"><i></i>${compactNumber(p.medal_count)}</span>`;pin.querySelector(".gps-name").textContent=p.display_name;pin.style.left=`${Number(el.dataset.x)}%`;pin.style.top=`${Number(el.dataset.y)-(mode==="afk"?18:12)}px`;lake.appendChild(pin);setTimeout(()=>pin.remove(),6500)}
  function renderPointsLeaderboard(rows=[]){if(!pointsLeaderboard)return;pointsLeaderboard.innerHTML='<strong>FISHING POINTS</strong>'+rows.map((row,index)=>`<div><b>${index+1}</b><span></span><em>${compactNumber(row.fishing_points)}</em></div>`).join("");rows.forEach((row,index)=>{const name=pointsLeaderboard.children[index+1]?.querySelector("span");if(name)name.textContent=row.display_name})}
  function boat(a){
    let el=nodes.get(a.user_id),isNew=!el;
    if(!a.active){if(el)el.remove();nodes.delete(a.user_id);return}
    if(!el){el=document.createElement("div");el.innerHTML='<div class="person"></div><div class="boat-art"></div><div class="rod"></div><div class="fishing-line"></div>';el.className=`boat${(hash(a.user_id+"facing")&1)===1?" facing-left":""}`;boats.appendChild(el);nodes.set(a.user_id,el)}
    const p=safeBoatPoint(position(a));el.classList.remove("tier-1","tier-2","tier-3","tier-4");el.classList.add(`tier-${a.boat_tier}`);el.dataset.userId=a.user_id;if(!el.dataset.x)el.dataset.x=String(p.x);if(!el.dataset.y)el.dataset.y=String(p.y);el.style.setProperty("--boat-color",a.boat_color);el.style.setProperty("--shirt-color",a.shirt_color);if(isNew){el.style.left=`calc(${p.x}% - ${mode==="compact"?52:75}px)`;el.style.top=`${p.y}px`;el.style.zIndex=String(100+Math.round(p.y))}
  }
  function snapshot(msg){
    document.body.classList.toggle("powered-off",msg.enabled===false);
    if(powerStatus){powerStatus.classList.toggle("off",msg.enabled===false);powerStatus.innerHTML=msg.enabled===false?'<strong>FISHING OFF</strong><span>The lake is empty. Join again when it reopens.</span>':'<strong>FISHING ON</strong><span>Type !fish join to launch your boat.</span><span>Treasure Gold upgrades boats automatically.</span><span>Customize: !fish boatcolor #RRGGBB</span>'}
    const current=new Set(msg.anglers.map(a=>a.user_id));for(const [id,el] of nodes){if(!current.has(id)){el.remove();nodes.delete(id)}}
    msg.anglers.forEach(boat);renderPointsLeaderboard(msg.points_leaderboard||[]);setWeather(msg.weather,msg.weather_boosted_species||[]);if(mode==="afk")label.style.display=msg.enabled===false?"none":"";else if(msg.enabled===false)label.textContent="⏻";
  }
  function setWeather(value,boosted=[]){const icons={sunny:"☀️",cloudy:"☁️",windy:"💨",rainy:"🌧️",night:"🌙"};if(mode==="compact")label.textContent=icons[value]||"🎣";else label.innerHTML=`<strong>${value.toUpperCase()}</strong><span>Improved catch rates: ${boosted.length?boosted.join(", "):"None"}</span>`;label.title=value;lake.classList.remove("night","weather-sunny","weather-cloudy","weather-windy","weather-rainy");lake.classList.add(value==="night"?"night":`weather-${value}`);weather.innerHTML="";if(value==="rainy")spawnRain();if(mode==="afk")renderAfkWeather(value)}
  function spawnRain(){const count=mode==="compact"?35:190;for(let i=0;i<count;i++){const d=document.createElement("i");d.className="rain";d.style.left=`${ambientInt(0,10000)/100}%`;d.style.height=`${ambientInt(13,30)}px`;d.style.opacity=String(ambientInt(38,88)/100);d.style.setProperty("--rain-x",`${-ambientInt(12,58)}px`);d.style.animationDuration=`${ambientInt(52,112)/100}s`;d.style.animationDelay=`-${ambientInt(0,240)/100}s`;weather.appendChild(d)}}
  function renderAfkWeather(value){
    const cloudCount={sunny:2,cloudy:7,windy:5,rainy:8,night:2}[value]||0;
    for(let i=0;i<cloudCount;i++){const c=document.createElement("div");c.className="weather-cloud";c.textContent="☁";c.style.top=`${45+(i%3)*62}px`;c.style.left=`${(i*271)%1500}px`;c.style.animationDuration=`${28+(i%4)*7}s`;c.style.animationDelay=`-${i*8}s`;weather.appendChild(c)}
    if(value==="windy")for(let i=0;i<18;i++){const w=document.createElement("i");w.className="wind-streak";w.style.top=`${80+(i*47)%850}px`;w.style.left=`${(i*113)%1200}px`;w.style.animationDelay=`-${(i%8)/3}s`;weather.appendChild(w)}
    if(value==="sunny"||value==="night"){const celestial=document.createElement("div");celestial.className="celestial";celestial.textContent=value==="night"?"🌙":"☀️";weather.appendChild(celestial)}
    if(value==="night")for(let i=0;i<55;i++){const s=document.createElement("i");s.className="star";s.style.left=`${25+(i*137)%1820}px`;s.style.top=`${18+(i*71)%225}px`;s.style.animationDelay=`-${(i%10)/5}s`;weather.appendChild(s)}
  }
  function ambientInt(min,max){const value=new Uint32Array(1);crypto.getRandomValues(value);return min+(value[0]%(max-min+1))}
  function ambientCoin(){return ambientInt(0,1)===1}
  function setSwimDirection(el,isDuck){const right=ambientCoin();el.classList.toggle("faces-left",!isDuck&&!right);el.classList.toggle("faces-right",isDuck&&right);el.style.setProperty("--swim-y",`${isDuck?ambientInt(455,760):ambientInt(400,950)}px`);el.style.setProperty("--swim-drift",`${isDuck?ambientInt(35,75):ambientInt(18,48)}px`);el.style.animationName=right?"swimRight":"swimLeft"}
  function spawnAfkAmbient(){if(mode!=="afk")return;const scenery=document.getElementById("scenery"),ambient=document.getElementById("ambient");scenery.innerHTML='<div class="shore-tree left">🌲</div><div class="shore-tree mid-left">🌲</div><div class="shore-tree center-left">🌲</div><div class="shore-tree mid-right">🌲</div><div class="shore-tree far-right">🌲</div><div class="shore-tree right">🌲</div><div class="dock"></div><div class="island one"></div><div class="island two"></div><div class="reeds one">|||||||</div><div class="reeds two">|||||||</div><div class="boathouse"></div>';for(let i=0;i<24;i++){const f=document.createElement("i");f.className="fish-silhouette";f.style.top=`${390+(i*83)%580}px`;f.style.width=`${38+(i%5)*7}px`;f.style.animationDuration=`${24+(i%7)*6}s`;f.style.animationDelay=`-${i*4}s`;setSwimDirection(f,false);f.addEventListener("animationiteration",()=>setSwimDirection(f,false));ambient.appendChild(f)}for(let i=0;i<2;i++){const d=document.createElement("div");d.className=`duck-ambient${i?" second":""}`;d.textContent="🦆";d.style.animationDuration=`${48+i*15}s`;setSwimDirection(d,true);d.addEventListener("animationiteration",()=>setSwimDirection(d,true));ambient.appendChild(d)}}
  function event(msg){
    if(seen.has(msg.event_id))return;seen.add(msg.event_id);if(seen.size>300)seen.delete(seen.values().next().value);
    const p=msg.payload, el=nodes.get(p.user_id);
    if((msg.kind==="angler_moved"||(msg.kind==="angler_activity"&&p.activity==="cruising"))&&el)moveBoatTo(el,position({user_id:p.user_id+msg.event_id}));
    if(msg.kind==="angler_inactive"&&el)sendBoatAway(el,p.user_id);
    if(msg.kind==="angler_returned")welcomeBoat(p.angler);
    if(msg.kind==="angler_gps")showGps(p);
    if(msg.kind==="angler_activity"&&p.activity==="casting"&&el){el.classList.add("fishing");setTimeout(()=>el.classList.remove("fishing"),2200)}
    if((msg.kind==="steve_attack"||msg.kind==="boat_sunk")&&el){el.classList.add("sunk");setTimeout(()=>{el.remove();nodes.delete(p.user_id)},900)}
    if(["catch","treasure","gun_cache","junk","boat_unlocked","bait_unlocked"].includes(msg.kind)&&el){animateFishingLine(el);const fx=document.createElement("div");fx.className="celebrate";fx.textContent=msg.kind==="catch"?"🐟":msg.kind==="treasure"?"💰":msg.kind==="gun_cache"?"📦":msg.kind==="junk"?"🥾":msg.kind==="boat_unlocked"?"🚤":"🪱";fx.style.left=el.style.left;fx.style.top=el.style.top;lake.appendChild(fx);setTimeout(()=>fx.remove(),2200)}
    if(mode==="afk")showBanner(msg);
    if(msg.kind==="catch"&&(p.tier==="diamond"||p.lake_record))fireworks(p.user_id,p.lake_record?7:2);
  }
  function showBanner(msg){const p=msg.payload;let text="";if(msg.kind==="catch")text=`${p.lake_record?"🏆 NEW LAKE RECORD — ":""}${p.display_name} • ${p.tier.toUpperCase()} ${p.species_name}<br>${p.weight.toFixed(1)} lb • +${p.points} Fishing Points${p.personal_best?" • NEW PB":""}`;if(msg.kind==="treasure")text=`💰 ${p.display_name} FOUND A ${p.chest_tier.toUpperCase()} TREASURE CHEST<br>+${p.gold} gold`;if(msg.kind==="gun_cache")text=`📦 ${p.display_name} FOUND A MYSTERIOUS CACHE`;if(msg.kind==="junk")text=`🥾 ${p.display_name} CAUGHT A ${p.item.toUpperCase()}`;if(msg.kind==="bait_unlocked")text=`🎣 ${p.display_name} UNLOCKED ${p.bait_label.toUpperCase()}<br>${p.species_name} can now be targeted`;if(msg.kind==="boat_unlocked")text=`${p.boat_tier===4?"🛳️":"🚤"} ${p.display_name.toUpperCase()} UNLOCKED ${p.boat_name.toUpperCase()}`;if(msg.kind==="steve_attack")text=`🦈 STEVE ATTACK!<br>${p.display_name}'s boat was destroyed`;if(msg.kind==="boat_sunk")text=`💥 ${p.attacker} SANK ${p.display_name}`;if(msg.kind==="angler_inactive")text=`🚤 ${p.display_name} LEFT THE LAKE<br>${p.reason}`;if(msg.kind==="angler_returned")text=`🎣 WELCOME BACK TO THE LAKE, ${p.display_name}!`;if(!text)return;banner.innerHTML=text;banner.classList.add("show");setTimeout(()=>banner.classList.remove("show"),4500)}
  function fireworks(id,count){const p=position({user_id:id});for(let i=0;i<count;i++)setTimeout(()=>{const f=document.createElement("div");f.className="firework";f.textContent="✦";f.style.left=`${Math.max(3,Math.min(96,p.x-12+i*4))}%`;f.style.top=`${Math.max(10,p.y-80-(i%3)*35)}px`;lake.appendChild(f);setTimeout(()=>f.remove(),1200)},i*130)}
  function animateFishingLine(el){el.classList.remove("line-active");void el.offsetWidth;el.classList.add("line-active");setTimeout(()=>el.classList.remove("line-active"),1500)}
  function fit(){if(mode!=="afk")return;lake.style.transform=`scale(${Math.min(innerWidth/1920,innerHeight/1080)})`}
  function compactWander(){if(mode==="compact"&&nodes.size){const entries=[...nodes.entries()],picked=entries[ambientInt(0,entries.length-1)],el=picked[1],x=Math.max(3,Math.min(97,Number(el.dataset.x)+ambientInt(-12,12)));moveBoatTo(el,{x,y:Number(el.dataset.y||1026)})}setTimeout(compactWander,ambientInt(35000,70000))}
  function connect(){const ws=new WebSocket(`${location.protocol==="https:"?"wss":"ws"}://${location.host}/ws`);ws.onopen=()=>{retry=1000;ws.send(JSON.stringify({type:"request_fishing_state"}))};ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==="fishing_state")snapshot(m);else if(m.type==="fishing_event")event(m)};ws.onclose=()=>setTimeout(connect,retry=Math.min(10000,retry*1.6))}
  addEventListener("resize",fit);spawnAfkAmbient();fit();connect();setTimeout(compactWander,ambientInt(25000,50000));
})();

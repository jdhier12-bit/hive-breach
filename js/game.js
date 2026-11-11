import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const BEST_KEY = "hiveBreach.bestScore";
const START_CREDITS = 240;
const BASE_MAX_HP = 20;
const MECH_ENERGY = 12;
const MECH_DRAIN = 1.15;
const MECH_COOLDOWN = 8;

const TOWER_DEF = {
  laser: {
    name: "Laser Turret", cost: 80, range: 5.8, rate: 0.2, damage: 7,
    upgrades: [60, 100], color: 0x3cefff,
  },
  tesla: {
    name: "Tesla Coil", cost: 140, range: 4.6, rate: 0.8, damage: 16,
    chain: 3, chainRange: 2.5, upgrades: [100, 160], color: 0xb44dff,
  },
  rocket: {
    name: "Missile Pod", cost: 180, range: 7.4, rate: 1.3, damage: 32,
    splash: 2.3, upgrades: [120, 180], color: 0xff6a1a,
  },
};

const ENEMY_DEF = {
  grunt: { hp: 32, speed: 2.15, reward: 6, score: 10, radius: 0.42, dmg: 1 },
  tank:  { hp: 150, speed: 1.35, reward: 16, score: 28, radius: 0.7, dmg: 3 },
  boss:  { hp: 980, speed: 0.92, reward: 90, score: 220, radius: 1.35, dmg: 8 },
};

const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const rand = (a, b) => a + Math.random() * (b - a);

// ---------------------------------------------------------------------------
// Audio
// ---------------------------------------------------------------------------
const AudioFX = {
  ctx: null,
  master: null,
  music: null,
  musicEl: null,
  muted: false,
  unlocked: false,

  init() {
    if (this.ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    this.ctx = new AC();
    this.master = this.ctx.createGain();
    this.master.gain.value = 0.9;
    this.master.connect(this.ctx.destination);
    this.musicEl = new Audio("assets/music/theme.mp3");
    this.musicEl.loop = true;
    this.musicEl.volume = 0.42;
    this.musicEl.preload = "auto";
  },

  async unlock() {
    this.init();
    if (this.ctx.state === "suspended") {
      try { await this.ctx.resume(); } catch (e) {}
    }
    this.unlocked = true;
    if (!this.muted) {
      this.musicEl.play().catch(() => {});
    }
  },

  setMuted(m) {
    this.muted = m;
    if (this.master) this.master.gain.value = m ? 0 : 0.9;
    if (this.musicEl) {
      this.musicEl.volume = m ? 0 : 0.42;
      if (!m && this.unlocked) this.musicEl.play().catch(() => {});
      if (m) this.musicEl.pause();
    }
  },

  beep(freq, dur, type, vol, slide) {
    if (!this.ctx || this.muted) return;
    const t = this.ctx.currentTime;
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.type = type || "square";
    o.frequency.setValueAtTime(freq, t);
    if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(40, slide), t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol || 0.2, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(this.master);
    o.start(t); o.stop(t + dur + 0.02);
  },

  noise(dur, vol, hp) {
    if (!this.ctx || this.muted) return;
    const t = this.ctx.currentTime;
    const n = this.ctx.createBuffer(1, Math.floor(this.ctx.sampleRate * dur), this.ctx.sampleRate);
    const d = n.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const src = this.ctx.createBufferSource();
    src.buffer = n;
    const f = this.ctx.createBiquadFilter();
    f.type = "highpass"; f.frequency.value = hp || 400;
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(vol || 0.2, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f); f.connect(g); g.connect(this.master);
    src.start(t);
  },

  laser() { this.beep(1400, 0.09, "square", 0.12, 420); this.noise(0.05, 0.06, 2000); },
  tesla() { this.beep(220, 0.18, "sawtooth", 0.16, 90); this.beep(900, 0.12, "square", 0.08, 200); this.noise(0.1, 0.1, 800); },
  rocket() { this.beep(180, 0.22, "sawtooth", 0.16, 70); this.noise(0.16, 0.12, 300); },
  boom() { this.beep(90, 0.35, "sine", 0.28, 40); this.noise(0.3, 0.22, 120); },
  stomp() { this.beep(70, 0.28, "sine", 0.32, 32); this.noise(0.2, 0.16, 80); },
  death() { this.beep(500, 0.16, "triangle", 0.1, 80); },
  ui() { this.beep(880, 0.06, "sine", 0.08); },
  build() { this.beep(520, 0.1, "triangle", 0.1); this.beep(780, 0.12, "sine", 0.08); },
  hitBase() { this.beep(120, 0.3, "sawtooth", 0.2, 50); this.noise(0.25, 0.15, 200); },
  wave() { this.beep(440, 0.15, "square", 0.1); this.beep(660, 0.2, "square", 0.1); },
  spawn() { this.beep(180, 0.12, "sine", 0.07, 90); },
};

// ---------------------------------------------------------------------------
// Game state
// ---------------------------------------------------------------------------
const game = {
  phase: "boot", // boot, home, playing, gameover
  credits: START_CREDITS,
  score: 0,
  best: Number(localStorage.getItem(BEST_KEY) || 0),
  wave: 0,
  baseHp: BASE_MAX_HP,
  timeScale: 1,
  selectedType: "laser",
  selectedPad: null,
  selectedTower: null,
  pads: [],
  towers: [],
  enemies: [],
  projectiles: [],
  fx: [],
  waypoints: [],
  pathLen: 0,
  pathSegs: [],
  mech: null,
  mechCooldown: 0,
  waveQueue: [],
  waveTimer: 0,
  spawning: false,
  prep: 0,
  shake: 0,
  elapsed: 0,
};

const assets = {};
const dummy = new THREE.Object3D();
const _v = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _v3 = new THREE.Vector3();

let renderer, scene, camera, composer, bloomPass, clock, raycaster, pointer;
let arenaRoot, hiveLight, baseLight;
let gruntPack, tankPack, bossProto, turretProto = {}, mechProto;
let canvas, joyState = { active: false, x: 0, y: 0, pid: null };

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function boot() {
  canvas = $("c");
  setupRenderer();
  setupScene();
  setupInput();
  bindUI();
  await loadAssets((p, label) => {
    $("loader-fill").style.width = `${Math.round(p * 100)}%`;
    $("loader-text").textContent = label;
  });
  buildWorld();
  updateHomeBest();
  $("loader").classList.add("hidden");
  $("home").classList.remove("hidden");
  game.phase = "home";
  clock = new THREE.Clock();
  renderer.setAnimationLoop(tick);
  exposeDebug();
}

function setupRenderer() {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.18;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070910);
  scene.fog = new THREE.FogExp2(0x0a0d16, 0.011);

  camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 0.1, 400);
  fitCamera();

  const renderPass = new RenderPass(scene, camera);
  bloomPass = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 0.48, 0.32, 1.05);
  const outputPass = new OutputPass();
  composer = new EffectComposer(renderer);
  composer.addPass(renderPass);
  composer.addPass(bloomPass);
  composer.addPass(outputPass);

  raycaster = new THREE.Raycaster();
  pointer = new THREE.Vector2();

  window.addEventListener("resize", onResize);
}

function fitCamera() {
  const w = window.innerWidth, h = window.innerHeight;
  camera.aspect = w / h;
  const portrait = h > w;
  camera.fov = portrait ? 46 : 34;
  camera.updateProjectionMatrix();
  // A slightly lower 3/4 view so the hive, base, and units read clearly on a phone.
  if (portrait) camera.position.set(0, 26, 27);
  else camera.position.set(0, 22, 21);
  camera.lookAt(0, 0.5, 0);
}

function onResize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  composer.setSize(w, h);
  bloomPass.setSize(w, h);
  fitCamera();
}

function setupScene() {
  scene.add(new THREE.HemisphereLight(0x8aa0c8, 0x2a241c, 0.9));
  scene.add(new THREE.AmbientLight(0x3a4458, 0.25));
  const sun = new THREE.DirectionalLight(0xffe6c8, 1.55);
  sun.position.set(-18, 28, 16);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 2;
  sun.shadow.camera.far = 80;
  sun.shadow.camera.left = -28;
  sun.shadow.camera.right = 28;
  sun.shadow.camera.top = 32;
  sun.shadow.camera.bottom = -32;
  sun.shadow.bias = -0.0004;
  scene.add(sun);
  scene.add(sun.target);

  hiveLight = new THREE.PointLight(0xff2d6a, 32, 26, 1.4);
  hiveLight.position.set(0, 3.2, -18);
  scene.add(hiveLight);
  baseLight = new THREE.PointLight(0xffc14a, 8, 14, 1.6);
  baseLight.position.set(0, 3.2, 17);
  scene.add(baseLight);

  // Distant planet + ring
  const planet = new THREE.Mesh(
    new THREE.SphereGeometry(36, 48, 32),
    new THREE.MeshStandardMaterial({
      color: 0xb85a32, roughness: 0.82, metalness: 0.05,
      emissive: 0x3a180c, emissiveIntensity: 0.35,
    })
  );
  planet.position.set(-70, 28, -90);
  scene.add(planet);
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(44, 58, 64),
    new THREE.MeshStandardMaterial({
      color: 0xd9a878, roughness: 0.6, side: THREE.DoubleSide,
      emissive: 0x6a4020, emissiveIntensity: 0.2,
    })
  );
  ring.position.copy(planet.position);
  ring.rotation.x = Math.PI / 2.6;
  ring.rotation.y = 0.35;
  scene.add(ring);

  // Stars
  const starGeo = new THREE.BufferGeometry();
  const n = 600;
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const r = 80 + Math.random() * 160;
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(rand(-0.2, 1));
    pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pos[i * 3 + 1] = r * Math.cos(ph) + 20;
    pos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th) - 20;
  }
  starGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xcde6ff, size: 0.45, sizeAttenuation: true })));
}

async function loadAssets(onProg) {
  const loader = new GLTFLoader();
  const files = {
    arena: "assets/models/arena.glb",
    grunt: "assets/models/alien_grunt.glb",
    tank: "assets/models/alien_tank.glb",
    boss: "assets/models/alien_boss.glb",
    laser: "assets/models/turret_laser.glb",
    tesla: "assets/models/turret_tesla.glb",
    rocket: "assets/models/turret_rocket.glb",
    mech: "assets/models/mech.glb",
  };
  const keys = Object.keys(files);
  let done = 0;
  const loadOne = (key) => new Promise((resolve, reject) => {
    loader.load(files[key], (gltf) => {
      assets[key] = gltf;
      done++;
      onProg(done / keys.length, `Loading ${key}…`);
      resolve(gltf);
    }, undefined, reject);
  });
  onProg(0, "Loading models…");
  await Promise.all(keys.map(loadOne));
  // Textures for VFX
  const texLoader = new THREE.TextureLoader();
  assets.glow = texLoader.load("assets/textures/glow.png");
  assets.burst = texLoader.load("assets/textures/burst.png");
  onProg(1, "Ready");
}

function prepareModel(root) {
  root.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      if (o.material) {
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach((m) => {
          if (m.map) m.map.colorSpace = THREE.SRGBColorSpace;
          m.side = THREE.FrontSide;
        });
      }
    }
  });
  return root;
}

function makeInstancedPack(gltf, maxCount) {
  const pack = [];
  const src = gltf.scene.clone(true);
  src.updateMatrixWorld(true);
  src.traverse((o) => {
    if (!o.isMesh) return;
    const geo = o.geometry.clone();
    geo.applyMatrix4(o.matrixWorld);
    const mat = o.material.clone();
    const inst = new THREE.InstancedMesh(geo, mat, maxCount);
    inst.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    inst.castShadow = true;
    inst.receiveShadow = true;
    inst.count = 0;
    inst.frustumCulled = false;
    pack.push(inst);
    scene.add(inst);
  });
  return pack;
}

function buildWorld() {
  arenaRoot = prepareModel(assets.arena.scene);
  // Hide extra pad decals — the platform mesh + a soft highlight is cleaner on a phone.
  arenaRoot.traverse((o) => {
    if (o.name.startsWith("PadRing") || o.name.startsWith("PadMark")) o.visible = false;
    if (o.isMesh && o.material) {
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m) => {
        const c = m.emissive;
        if (c && (c.r > 0.4 && c.b > 0.2 && c.g < 0.4)) m.emissiveIntensity = Math.max(m.emissiveIntensity || 1, 2.4);
      });
    }
  });
  const hiveObj = arenaRoot.getObjectByName("HiveShip");
  if (hiveObj) {
    hiveObj.scale.setScalar(1.65);
    hiveObj.position.y += 0.9;
    const hp = new THREE.Vector3();
    hiveObj.updateWorldMatrix(true, true);
    hiveObj.getWorldPosition(hp);
    hiveLight.position.set(hp.x, hp.y + 2.4, hp.z + 2.0);
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: assets.glow, color: 0xff2d6a, blending: THREE.AdditiveBlending,
      transparent: true, depthWrite: false, opacity: 0.9,
    }));
    glow.position.set(hp.x, hp.y + 1.1, hp.z + 2.2);
    glow.scale.set(6.5, 6.5, 1);
    scene.add(glow);
  }
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(90, 48),
    new THREE.MeshStandardMaterial({ color: 0x090b10, roughness: 1, metalness: 0 })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.08;
  ground.receiveShadow = true;
  scene.add(ground);
  scene.add(arenaRoot);

  // Waypoints & pads from the arena (already in three.js space)
  const wps = [];
  const pads = [];
  arenaRoot.updateMatrixWorld(true);
  arenaRoot.traverse((o) => {
    if (o.name.startsWith("Waypoint_")) {
      const p = new THREE.Vector3();
      o.getWorldPosition(p);
      const i = Number(o.name.split("_")[1]);
      wps[i] = p;
    } else if (/^Pad_\d+/.test(o.name)) {
      const p = new THREE.Vector3();
      o.getWorldPosition(p);
      const i = Number(o.name.split("_")[1]);
      pads[i] = { index: i, pos: p, mesh: o, tower: null, highlight: null };
    }
  });
  game.waypoints = wps.filter(Boolean);
  game.pads = pads.filter(Boolean);
  // Path segments
  game.pathSegs = [];
  game.pathLen = 0;
  for (let i = 0; i < game.waypoints.length - 1; i++) {
    const a = game.waypoints[i], b = game.waypoints[i + 1];
    const len = a.distanceTo(b);
    game.pathSegs.push({ a, b, len, start: game.pathLen });
    game.pathLen += len;
  }

  // Pad highlights
  const ringGeo = new THREE.RingGeometry(0.95, 1.12, 32);
  ringGeo.rotateX(-Math.PI / 2);
  game.pads.forEach((pad) => {
    const hl = new THREE.Mesh(
      ringGeo,
      new THREE.MeshBasicMaterial({ color: 0x3cefff, transparent: true, opacity: 0, depthWrite: false })
    );
    hl.position.copy(pad.pos);
    hl.position.y += 0.12;
    scene.add(hl);
    pad.highlight = hl;
  });

  gruntPack = makeInstancedPack(assets.grunt, 80);
  tankPack = makeInstancedPack(assets.tank, 24);
  bossProto = prepareModel(assets.boss.scene);
  turretProto.laser = prepareModel(assets.laser.scene);
  turretProto.tesla = prepareModel(assets.tesla.scene);
  turretProto.rocket = prepareModel(assets.rocket.scene);
  mechProto = prepareModel(assets.mech.scene);
  // Nudge visor forward if it's buried in the helmet
  const vis = mechProto.getObjectByName("Mech_Visor");
  if (vis) vis.position.z += 0.08; // glTF: Blender -Y becomes +Z? Wait, Blender -Y is +Z in glTF. Front is +Z? 
  // Blender front is -Y, glTF conversion: Z_gl = -Y_bl, so front is +Z in three.js.
}

function pathPoint(dist, offset, out, outDir) {
  const d = clamp(dist, 0, game.pathLen);
  const segs = game.pathSegs;
  let s = segs[segs.length - 1];
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i].start + segs[i].len) { s = segs[i]; break; }
  }
  const t = s.len > 0 ? (d - s.start) / s.len : 1;
  out.lerpVectors(s.a, s.b, t);
  _v2.subVectors(s.b, s.a).setY(0);
  if (_v2.lengthSq() > 1e-6) _v2.normalize();
  if (outDir) outDir.copy(_v2);
  // lateral offset
  _v3.set(-_v2.z, 0, _v2.x).multiplyScalar(offset || 0);
  out.add(_v3);
  return out;
}


// ---------------------------------------------------------------------------
// Waves
// ---------------------------------------------------------------------------
function wavePlan(n) {
  const plan = [];
  const push = (type, c) => { for (let i = 0; i < c; i++) plan.push(type); };
  const g = 6 + n * 3;
  const t = n >= 3 ? Math.floor((n - 2) * 1.4) : 0;
  push("grunt", g);
  push("tank", t);
  if (n % 5 === 0) push("boss", 1 + Math.floor((n - 5) / 10));
  // interleave a bit so tanks aren't all at the end
  if (t > 0) {
    const mixed = [];
    let gi = 0, ti = 0, grunts = plan.filter((x) => x === "grunt");
    const tanks = plan.filter((x) => x === "tank");
    const bosses = plan.filter((x) => x === "boss");
    const total = grunts.length + tanks.length;
    for (let i = 0; i < total; i++) {
      if (ti < tanks.length && (i % 4 === 3 || gi >= grunts.length)) mixed.push(tanks[ti++]);
      else mixed.push(grunts[gi++]);
    }
    return mixed.concat(bosses);
  }
  return plan;
}

function beginRun() {
  game.credits = START_CREDITS;
  game.score = 0;
  game.wave = 0;
  game.baseHp = BASE_MAX_HP;
  game.towers.forEach((t) => { scene.remove(t.root); });
  game.towers = [];
  game.pads.forEach((p) => { p.tower = null; });
  clearEnemies();
  game.projectiles.forEach((p) => { if (p.mesh) scene.remove(p.mesh); });
  game.projectiles = [];
  retractMech(true);
  game.mechCooldown = 0;
  game.waveQueue = [];
  game.spawning = false;
  game.selectedPad = null;
  game.selectedTower = null;
  game.selectedType = "laser";
  game.shake = 0;
  game.elapsed = 0;
  $("tower-sheet").classList.add("hidden");
  $("energy-wrap").classList.add("hidden");
  $("joystick").classList.add("hidden");
  enterPrep(12);
  syncHUD();
  highlightAfford();
}

function enterPrep(seconds) {
  game.prep = seconds;
  game.spawning = false;
  $("wave-banner").classList.remove("hidden");
  $("wave-banner-text").textContent = game.wave === 0 ? "Place your defenses" : `Wave ${game.wave} cleared`;
  $("btn-start-wave").classList.remove("hidden");
  $("btn-start-wave").textContent = game.wave === 0 ? "Launch Wave 1" : `Launch Wave ${game.wave + 1}`;
}

function launchWave() {
  game.wave += 1;
  game.waveQueue = wavePlan(game.wave);
  game.spawning = true;
  game.waveTimer = 0.4;
  game.prep = 0;
  $("btn-start-wave").classList.add("hidden");
  $("wave-banner-text").textContent = `WAVE ${game.wave}`;
  AudioFX.wave();
  setTimeout(() => { if (game.spawning) $("wave-banner").classList.add("hidden"); }, 1600);
  syncHUD();
}

function maybeFinishWave() {
  if (game.spawning && game.waveQueue.length === 0 && game.enemies.every((e) => !e.alive)) {
    game.spawning = false;
    if (game.phase === "playing") enterPrep(7);
  }
}

// ---------------------------------------------------------------------------
// Enemies
// ---------------------------------------------------------------------------
function spawnEnemy(type) {
  const def = ENEMY_DEF[type];
  const scaleHp = 1 + 0.16 * (game.wave - 1);
  const scaleSp = 1 + 0.045 * (game.wave - 1);
  const e = {
    type, def,
    hp: def.hp * scaleHp,
    maxHp: def.hp * scaleHp,
    speed: def.speed * scaleSp,
    dist: 0,
    offset: rand(-0.7, 0.7),
    x: 0, y: 0, z: 0,
    rot: 0,
    alive: true,
    seed: Math.random() * 100,
    radius: def.radius,
    object: null, // boss only
  };
  if (type === "boss") {
    const obj = bossProto.clone(true);
    prepareModel(obj);
    scene.add(obj);
    e.object = obj;
  }
  pathPoint(0, e.offset, _v);
  e.x = _v.x; e.y = _v.y; e.z = _v.z;
  game.enemies.push(e);
  AudioFX.spawn();
  return e;
}

function clearEnemies() {
  game.enemies.forEach((e) => { if (e.object) scene.remove(e.object); });
  game.enemies = [];
  syncPacks();
}

function damageEnemy(e, amt, flash) {
  if (!e.alive) return;
  e.hp -= amt;
  if (flash) pulseFx(e.x, 0.8, e.z, flash, 0.35, 0.4);
  if (e.hp <= 0) killEnemy(e);
}

function killEnemy(e) {
  if (!e.alive) return;
  e.alive = false;
  game.credits += e.def.reward;
  game.score += e.def.score * Math.max(1, game.wave);
  burstFx(e.x, 0.6, e.z, e.type === "boss" ? 0xff3d8a : 0x9dff3c, e.type === "boss" ? 1.6 : 0.7);
  AudioFX.death();
  if (e.type === "boss") AudioFX.boom();
  if (e.object) {
    scene.remove(e.object);
    e.object = null;
  }
  syncHUD();
  maybeFinishWave();
}

function updateEnemies(dt) {
  for (const e of game.enemies) {
    if (!e.alive) continue;
    e.dist += e.speed * dt;
    if (e.dist >= game.pathLen) {
      leakEnemy(e);
      continue;
    }
    pathPoint(e.dist, e.offset, _v, _v2);
    e.x = _v.x; e.y = _v.y; e.z = _v.z;
    if (_v2.lengthSq() > 0) e.rot = Math.atan2(_v2.x, _v2.z);
  }
  // compact occasionally
  if (game.enemies.length > 8 && game.enemies.every((e) => !e.alive)) {
    game.enemies = [];
  } else if (game.enemies.length > 40) {
    game.enemies = game.enemies.filter((e) => e.alive || e.object);
  }
  syncPacks();
}

function leakEnemy(e) {
  e.alive = false;
  game.baseHp -= e.def.dmg;
  game.shake = Math.max(game.shake, 0.35);
  AudioFX.hitBase();
  burstFx(e.x, 0.8, e.z, 0xff5a6a, 0.8);
  if (e.object) { scene.remove(e.object); e.object = null; }
  syncHUD();
  if (game.baseHp <= 0) endGame();
  else maybeFinishWave();
}

function syncPacks() {
  const kinds = [
    { type: "grunt", pack: gruntPack },
    { type: "tank", pack: tankPack },
  ];
  for (const { type, pack } of kinds) {
    const list = game.enemies.filter((e) => e.type === type && e.alive);
    list.forEach((e, i) => {
      const bob = 1 + 0.05 * Math.sin(game.elapsed * 14 + e.seed);
      dummy.position.set(e.x, 0, e.z);
      dummy.rotation.set(0, e.rot, Math.sin(game.elapsed * 10 + e.seed) * 0.08);
      dummy.scale.setScalar(bob);
      dummy.updateMatrix();
      pack.forEach((inst) => inst.setMatrixAt(i, dummy.matrix));
    });
    pack.forEach((inst) => {
      inst.count = list.length;
      inst.instanceMatrix.needsUpdate = true;
    });
  }
  for (const e of game.enemies) {
    if (e.object && e.alive) {
      e.object.position.set(e.x, 0, e.z);
      e.object.rotation.y = e.rot;
      const bob = 1 + 0.03 * Math.sin(game.elapsed * 8 + e.seed);
      e.object.scale.setScalar(bob);
    }
  }
}

function enemiesInRange(x, z, range, except) {
  const r2 = range * range;
  const out = [];
  for (const e of game.enemies) {
    if (!e.alive || e === except) continue;
    const dx = e.x - x, dz = e.z - z;
    const d2 = dx * dx + dz * dz;
    if (d2 <= r2) out.push({ e, d2 });
  }
  out.sort((a, b) => a.d2 - b.d2);
  return out;
}

// ---------------------------------------------------------------------------
// Towers
// ---------------------------------------------------------------------------
function towerStats(type, level) {
  const d = TOWER_DEF[type];
  const mul = level === 1 ? 1 : level === 2 ? 1.4 : 1.85;
  return {
    range: d.range * (level === 3 ? 1.2 : level === 2 ? 1.1 : 1),
    rate: d.rate * (level === 3 ? 0.78 : level === 2 ? 0.88 : 1),
    damage: d.damage * mul,
    splash: d.splash ? d.splash * (level === 3 ? 1.2 : 1) : 0,
    chain: d.chain || 0,
    chainRange: d.chainRange || 0,
  };
}

function spentOn(type, level) {
  const d = TOWER_DEF[type];
  let s = d.cost;
  for (let i = 0; i < level - 1; i++) s += d.upgrades[i];
  return s;
}

function placeTower(pad, type) {
  if (!pad || pad.tower) return false;
  const def = TOWER_DEF[type];
  if (game.credits < def.cost) {
    toast("Not enough credits");
    return false;
  }
  game.credits -= def.cost;
  const root = turretProto[type].clone(true);
  prepareModel(root);
  root.position.copy(pad.pos);
  root.position.y = pad.pos.y;
  root.scale.setScalar(1.2);
  scene.add(root);
  const yaw = root.getObjectByName("Turret_Yaw") || root;
  const pitch = root.getObjectByName("Turret_Pitch") || yaw;
  const tower = {
    type, level: 1, pad, root, yaw, pitch,
    cooldown: 0.2, stats: towerStats(type, 1),
  };
  pad.tower = tower;
  game.towers.push(tower);
  AudioFX.build();
  syncHUD();
  highlightAfford();
  return tower;
}

function upgradeTower(tower) {
  if (!tower || tower.level >= 3) return false;
  const cost = TOWER_DEF[tower.type].upgrades[tower.level - 1];
  if (game.credits < cost) { toast("Not enough credits"); return false; }
  game.credits -= cost;
  tower.level += 1;
  tower.stats = towerStats(tower.type, tower.level);
  tower.root.scale.setScalar(1.2 * (1 + (tower.level - 1) * 0.1));
  AudioFX.build();
  syncHUD();
  openSheet(tower);
  return true;
}

function sellTower(tower) {
  if (!tower) return;
  const value = Math.floor(spentOn(tower.type, tower.level) * 0.6);
  game.credits += value;
  scene.remove(tower.root);
  tower.pad.tower = null;
  game.towers = game.towers.filter((t) => t !== tower);
  game.selectedTower = null;
  $("tower-sheet").classList.add("hidden");
  AudioFX.ui();
  syncHUD();
  highlightAfford();
}

function updateTowers(dt) {
  for (const t of game.towers) {
    t.cooldown -= dt;
    const hits = enemiesInRange(t.root.position.x, t.root.position.z, t.stats.range);
    if (!hits.length) continue;
    const target = hits[0].e;
    aimTurret(t, target);
    if (t.cooldown <= 0) {
      fireTower(t, target, hits);
      t.cooldown = t.stats.rate;
    }
  }
}

function aimTurret(t, target) {
  if (!t.yaw) return;
  const pos = t.root.position;
  const dx = target.x - pos.x;
  const dz = target.z - pos.z;
  // yaw around Y so the turret's forward (+Z local after glTF? original Blender gun pointed +Y = -Z in three?)
  // Blender gun barrels were placed in +Y, which becomes -Z in glTF. So rest pose faces -Z.
  // We want the barrel to point at the target. angle from -Z: atan2(dx, -dz)? 
  // Object facing -Z: rotation.y = 0. To face a direction (dx, dz), rotation.y = Math.atan2(dx, dz) would face +Z.
  // To face -Z at rest, rotation.y = Math.atan2(dx, dz) + Math.PI.
  const yaw = Math.atan2(dx, dz) + Math.PI;
  t.yaw.rotation.y = yaw;
}

function fireTower(t, target, hits) {
  const p = t.root.position;
  if (t.type === "laser") {
    beamFx(p.x, 1.1, p.z, target.x, 0.6, target.z, 0x3cefff, 0.08);
    muzzleFx(p.x, 1.15, p.z, 0x3cefff);
    damageEnemy(target, t.stats.damage, 0x3cefff);
    AudioFX.laser();
  } else if (t.type === "tesla") {
    let prev = { x: p.x, y: 1.5, z: p.z };
    const chained = [target];
    let current = target;
    damageEnemy(current, t.stats.damage, 0xb44dff);
    zapFx(prev.x, prev.y, prev.z, current.x, 0.8, current.z, 0xc07cff);
    for (let i = 1; i < t.stats.chain; i++) {
      const next = enemiesInRange(current.x, current.z, t.stats.chainRange, current)
        .find((h) => !chained.includes(h.e));
      if (!next) break;
      current = next.e;
      chained.push(current);
      zapFx(chained[i - 1].x, 0.8, chained[i - 1].z, current.x, 0.8, current.z, 0xc07cff);
      damageEnemy(current, t.stats.damage * (1 - i * 0.25), 0xb44dff);
    }
    AudioFX.tesla();
  } else {
    // rocket projectile
    const proj = {
      kind: "rocket",
      x: p.x, y: 1.15, z: p.z,
      tx: target.x, ty: 0.6, tz: target.z,
      speed: 14,
      damage: t.stats.damage,
      splash: t.stats.splash,
      target,
      mesh: makeBolt(0xff6a1a, 0.12, 0.4),
    };
    proj.mesh.position.set(proj.x, proj.y, proj.z);
    scene.add(proj.mesh);
    game.projectiles.push(proj);
    AudioFX.rocket();
  }
}

function updateProjectiles(dt) {
  for (let i = game.projectiles.length - 1; i >= 0; i--) {
    const p = game.projectiles[i];
    if (p.target && p.target.alive) {
      p.tx = p.target.x; p.ty = 0.55; p.tz = p.target.z;
    }
    const dx = p.tx - p.x, dy = p.ty - p.y, dz = p.tz - p.z;
    const dist = Math.hypot(dx, dy, dz) || 1;
    const step = p.speed * dt;
    if (step >= dist) {
      // impact
      if (p.mesh) scene.remove(p.mesh);
      burstFx(p.tx, p.ty, p.tz, 0xff6a1a, p.splash || 0.8);
      AudioFX.boom();
      game.shake = Math.max(game.shake, 0.18);
      const hits = enemiesInRange(p.tx, p.tz, p.splash || 0.5);
      for (const h of hits) {
        const fall = 1 - Math.sqrt(h.d2) / (p.splash + 0.01);
        damageEnemy(h.e, p.damage * Math.max(0.4, fall), 0xff6a1a);
      }
      game.projectiles.splice(i, 1);
    } else {
      p.x += (dx / dist) * step;
      p.y += (dy / dist) * step + Math.sin((dist / 8) * Math.PI) * 0.02;
      p.z += (dz / dist) * step;
      if (p.mesh) {
        p.mesh.position.set(p.x, p.y, p.z);
        p.mesh.lookAt(p.tx, p.ty, p.tz);
      }
    }
  }
}

function makeBolt(color, r, len) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.CapsuleGeometry(r, len, 6, 8),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95 })
  );
  body.rotation.x = Math.PI / 2;
  g.add(body);
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({
    map: assets.glow, color, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false,
  }));
  glow.scale.set(0.6, 0.6, 1);
  g.add(glow);
  return g;
}


// ---------------------------------------------------------------------------
// Mech
// ---------------------------------------------------------------------------
function canDeployMech() {
  return !game.mech && game.mechCooldown <= 0 && game.phase === "playing";
}

function deployMech(x, z) {
  if (!canDeployMech()) {
    if (game.mechCooldown > 0) toast("Aegis recharging");
    return false;
  }
  if (x == null) {
    // drop near the base (last waypoint)
    const wp = game.waypoints[game.waypoints.length - 1];
    x = wp.x; z = wp.z + 3;
  }
  const root = mechProto.clone(true);
  prepareModel(root);
  // Fix visor if present: push toward local +Z (front)
  root.traverse((o) => {
    if (o.name === "Mech_Visor") o.position.z += 0.1;
  });
  root.position.set(x, 0, z);
  root.scale.setScalar(1.25);
  scene.add(root);
  const parts = {
    root,
    pelvis: root.getObjectByName("Mech_Pelvis") || root,
    torso: root.getObjectByName("Mech_Torso"),
    head: root.getObjectByName("Mech_Head"),
    lThigh: root.getObjectByName("Mech_LThigh"),
    rThigh: root.getObjectByName("Mech_RThigh"),
    lShin: root.getObjectByName("Mech_LShin"),
    rShin: root.getObjectByName("Mech_RShin"),
    lArm: root.getObjectByName("Mech_LArm"),
    rArm: root.getObjectByName("Mech_RArm"),
    lFore: root.getObjectByName("Mech_LFore"),
    rFore: root.getObjectByName("Mech_RFore"),
  };
  game.mech = {
    parts, x, z, rot: 0, vx: 0, vz: 0,
    energy: MECH_ENERGY, maxEnergy: MECH_ENERGY,
    dest: null, shootCd: 0, stompCd: 0, walk: 0, moving: false,
  };
  $("joystick").classList.remove("hidden");
  $("energy-wrap").classList.remove("hidden");
  AudioFX.build();
  syncHUD();
  return true;
}

function retractMech(silent) {
  if (!game.mech) return;
  scene.remove(game.mech.parts.root);
  game.mech = null;
  game.mechCooldown = MECH_COOLDOWN;
  $("joystick").classList.add("hidden");
  $("energy-wrap").classList.add("hidden");
  joyState.active = false; joyState.x = 0; joyState.y = 0;
  if (!silent) AudioFX.ui();
  syncHUD();
}

function updateMech(dt) {
  if (!game.mech) {
    if (game.mechCooldown > 0) {
      game.mechCooldown = Math.max(0, game.mechCooldown - dt);
      syncMechStatus();
    }
    return;
  }
  const m = game.mech;
  // input
  let ix = 0, iz = 0;
  if (joyState.active && (Math.abs(joyState.x) > 0.12 || Math.abs(joyState.y) > 0.12)) {
    ix = joyState.x; iz = joyState.y;
    m.dest = null;
  } else if (m.dest) {
    const dx = m.dest.x - m.x, dz = m.dest.z - m.z;
    const d = Math.hypot(dx, dz);
    if (d < 0.4) m.dest = null;
    else { ix = dx / d; iz = dz / d; }
  }
  const spd = 5.4;
  m.vx = ix * spd; m.vz = iz * spd;
  m.x = clamp(m.x + m.vx * dt, -14, 14);
  m.z = clamp(m.z + m.vz * dt, -22, 22);
  m.moving = Math.hypot(m.vx, m.vz) > 0.2;
  if (m.moving) m.rot = Math.atan2(m.vx, m.vz); // face +Z dir of motion? atan2(x,z) faces +Z when moving +Z
  m.parts.root.position.set(m.x, 0, m.z);
  m.parts.root.rotation.y = m.rot;

  // Walk cycle
  m.walk += dt * (m.moving ? 8 : 2);
  const swing = m.moving ? 0.55 : 0.08;
  const a = Math.sin(m.walk) * swing;
  const b = Math.sin(m.walk + Math.PI) * swing;
  const setRot = (obj, x) => { if (obj) obj.rotation.x = x; };
  setRot(m.parts.lThigh, a);
  setRot(m.parts.rThigh, b);
  setRot(m.parts.lShin, Math.max(0, -a) * 0.6);
  setRot(m.parts.rShin, Math.max(0, -b) * 0.6);
  setRot(m.parts.lArm, b * 0.4);
  setRot(m.parts.rArm, a * 0.4);
  if (m.parts.torso) m.parts.torso.rotation.y = Math.sin(m.walk * 0.5) * 0.05;

  // Combat
  m.shootCd -= dt; m.stompCd -= dt;
  const near = enemiesInRange(m.x, m.z, 6);
  if (near.length) {
    const t = near[0].e;
    if (m.shootCd <= 0) {
      beamFx(m.x, 1.3, m.z, t.x, 0.6, t.z, 0x3cefff, 0.07);
      damageEnemy(t, 14, 0x3cefff);
      AudioFX.laser();
      m.shootCd = 0.28;
    }
    if (m.stompCd <= 0 && near[0].d2 < 2.6 * 2.6) {
      stomp(m);
    }
  }

  m.energy -= MECH_DRAIN * dt;
  if (m.energy <= 0) retractMech();
  else {
    $("ui-energy").style.width = `${(m.energy / m.maxEnergy) * 100}%`;
  }
}

function stomp(m) {
  m.stompCd = 1.05;
  game.shake = Math.max(game.shake, 0.55);
  burstFx(m.x, 0.2, m.z, 0xffe6a0, 1.4);
  AudioFX.stomp();
  const hits = enemiesInRange(m.x, m.z, 2.5);
  for (const h of hits) damageEnemy(h.e, 40, 0xffe6a0);
  if (m.parts.lThigh) m.parts.lThigh.rotation.x = -0.5;
}

// ---------------------------------------------------------------------------
// VFX
// ---------------------------------------------------------------------------
function pulseFx(x, y, z, color, scale, life) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: assets.glow, color, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false,
  }));
  s.position.set(x, y, z);
  s.scale.setScalar(scale);
  scene.add(s);
  game.fx.push({ mesh: s, life, max: life, grow: 1.6 });
}

function burstFx(x, y, z, color, scale) {
  pulseFx(x, y, z, color, scale, 0.35);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: assets.burst, color: 0xffffff, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false,
  }));
  s.position.set(x, y, z);
  s.scale.setScalar(scale * 0.8);
  scene.add(s);
  game.fx.push({ mesh: s, life: 0.28, max: 0.28, grow: 2.2 });
}

function muzzleFx(x, y, z, color) { pulseFx(x, y, z, color, 0.5, 0.08); }

function beamFx(x1, y1, z1, x2, y2, z2, color, life) {
  const p1 = new THREE.Vector3(x1, y1, z1), p2 = new THREE.Vector3(x2, y2, z2);
  const geo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
  const line = new THREE.Line(geo, new THREE.LineBasicMaterial({
    color, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false,
  }));
  scene.add(line);
  game.fx.push({ mesh: line, life: life || 0.08, max: life || 0.08, isLine: true });
  pulseFx(x2, y2, z2, color, 0.45, 0.12);
}

function zapFx(x1, y1, z1, x2, y2, z2, color) {
  const pts = [];
  const segs = 6;
  for (let i = 0; i <= segs; i++) {
    const t = i / segs;
    pts.push(new THREE.Vector3(
      lerp(x1, x2, t) + (i === 0 || i === segs ? 0 : rand(-0.25, 0.25)),
      lerp(y1, y2, t) + (i === 0 || i === segs ? 0 : rand(-0.15, 0.15)),
      lerp(z1, z2, t) + (i === 0 || i === segs ? 0 : rand(-0.25, 0.25)),
    ));
  }
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  const line = new THREE.Line(geo, new THREE.LineBasicMaterial({
    color, transparent: true, opacity: 1, blending: THREE.AdditiveBlending, depthWrite: false,
  }));
  scene.add(line);
  game.fx.push({ mesh: line, life: 0.12, max: 0.12, isLine: true });
}

function updateFx(dt) {
  for (let i = game.fx.length - 1; i >= 0; i--) {
    const f = game.fx[i];
    f.life -= dt;
    const k = Math.max(0, f.life / f.max);
    if (f.mesh.material) f.mesh.material.opacity = k;
    if (f.grow && f.mesh.scale) {
      const s = f.mesh.scale.x + dt * f.grow;
      f.mesh.scale.setScalar(s);
    }
    if (f.life <= 0) {
      scene.remove(f.mesh);
      if (f.mesh.geometry && f.isLine) f.mesh.geometry.dispose();
      game.fx.splice(i, 1);
    }
  }
}

// ---------------------------------------------------------------------------
// UI / Input
// ---------------------------------------------------------------------------
function bindUI() {
  $("btn-start").addEventListener("click", async () => {
    await AudioFX.unlock();
    AudioFX.ui();
    startPlaying();
  });
  $("btn-again").addEventListener("click", async () => {
    await AudioFX.unlock();
    $("gameover").classList.add("hidden");
    startPlaying();
  });
  $("btn-home").addEventListener("click", () => {
    $("gameover").classList.add("hidden");
    $("hud").classList.add("hidden");
    $("home").classList.remove("hidden");
    game.phase = "home";
    updateHomeBest();
  });
  $("btn-start-wave").addEventListener("click", () => launchWave());
  $("btn-mute").addEventListener("click", () => {
    AudioFX.setMuted(!AudioFX.muted);
    $("btn-mute").textContent = AudioFX.muted ? "Muted" : "♪";
  });
  document.querySelectorAll(".build-btn[data-type]").forEach((btn) => {
    btn.addEventListener("click", () => {
      game.selectedType = btn.dataset.type;
      document.querySelectorAll(".build-btn[data-type]").forEach((b) => b.classList.toggle("selected", b === btn));
      AudioFX.ui();
      if (game.selectedPad && !game.selectedPad.tower) {
        placeTower(game.selectedPad, game.selectedType);
        game.selectedPad = null;
        clearPadHighlight();
      }
    });
  });
  $("btn-mech").addEventListener("click", () => {
    if (game.mech) retractMech();
    else deployMech();
  });
  $("btn-upgrade").addEventListener("click", () => upgradeTower(game.selectedTower));
  $("btn-sell").addEventListener("click", () => sellTower(game.selectedTower));
  $("btn-sheet-close").addEventListener("click", () => {
    game.selectedTower = null;
    $("tower-sheet").classList.add("hidden");
  });
  // First tap anywhere unlocks audio
  const unlockOnce = () => { AudioFX.unlock(); };
  window.addEventListener("pointerdown", unlockOnce, { once: true });
}

function startPlaying() {
  $("home").classList.add("hidden");
  $("gameover").classList.add("hidden");
  $("hud").classList.remove("hidden");
  game.phase = "playing";
  beginRun();
  document.querySelector('.build-btn[data-type="laser"]').classList.add("selected");
}

function updateHomeBest() {
  const el = $("home-best");
  if (game.best > 0) {
    el.classList.remove("hidden");
    el.querySelector("strong").textContent = String(game.best);
  }
}

function syncHUD() {
  $("ui-wave").textContent = String(Math.max(1, game.wave) );
  $("ui-credits").textContent = String(Math.floor(game.credits));
  $("ui-score").textContent = String(Math.floor(game.score));
  $("ui-hp").style.width = `${clamp(game.baseHp / BASE_MAX_HP, 0, 1) * 100}%`;
  $("ui-hp").style.background = game.baseHp < BASE_MAX_HP * 0.3
    ? "linear-gradient(90deg,#ff5a6a,#ff9a3c)"
    : "linear-gradient(90deg,#35e07a,#8cff6a)";
  document.querySelectorAll(".b-cost[data-cost]").forEach((el) => {
    el.textContent = String(TOWER_DEF[el.dataset.cost].cost);
  });
  highlightAfford();
  syncMechStatus();
}

function syncMechStatus() {
  const el = $("mech-status");
  if (game.mech) el.textContent = "Recall";
  else if (game.mechCooldown > 0) el.textContent = `${game.mechCooldown.toFixed(0)}s`;
  else el.textContent = "Ready";
  $("btn-mech").classList.toggle("cant", !game.mech && game.mechCooldown > 0);
}

function highlightAfford() {
  document.querySelectorAll(".build-btn[data-type]").forEach((btn) => {
    const cost = TOWER_DEF[btn.dataset.type].cost;
    btn.classList.toggle("cant", game.credits < cost);
  });
}

function openSheet(tower) {
  game.selectedTower = tower;
  const def = TOWER_DEF[tower.type];
  $("sheet-name").textContent = def.name;
  $("sheet-level").textContent = tower.level >= 3 ? "Max level" : `Level ${tower.level}`;
  const up = $("btn-upgrade");
  if (tower.level >= 3) {
    up.disabled = true;
    $("upgrade-cost").textContent = "";
    up.childNodes[0].textContent = "Maxed ";
  } else {
    up.disabled = false;
    const cost = def.upgrades[tower.level - 1];
    $("upgrade-cost").textContent = cost;
    up.childNodes[0].textContent = "Upgrade ";
  }
  $("sell-value").textContent = Math.floor(spentOn(tower.type, tower.level) * 0.6);
  $("tower-sheet").classList.remove("hidden");
}

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 1200);
}

function clearPadHighlight() {
  game.pads.forEach((p) => { p.highlight.material.opacity = 0; });
}

function pulsePads(dt) {
  const t = game.elapsed;
  game.pads.forEach((p) => {
    if (p.tower) { p.highlight.material.opacity = 0; return; }
    const sel = game.selectedPad === p;
    const idle = game.spawning ? 0.08 : 0.16 + 0.08 * Math.sin(t * 2.5);
    p.highlight.material.opacity = sel ? 0.9 : idle;
    p.highlight.material.color.set(sel ? 0xffc14a : 0x3cefff);
  });
}

function setupInput() {
  const el = canvas;
  el.addEventListener("pointerdown", onPointerDown);
  el.addEventListener("pointermove", onPointerMove);
  el.addEventListener("pointerup", onPointerUp);
  el.addEventListener("pointercancel", onPointerUp);
  // Joystick
  const joy = $("joystick");
  joy.addEventListener("pointerdown", (ev) => {
    ev.stopPropagation();
    joyState.active = true;
    joyState.pid = ev.pointerId;
    joy.setPointerCapture(ev.pointerId);
    moveJoy(ev);
  });
  joy.addEventListener("pointermove", (ev) => { if (joyState.active && ev.pointerId === joyState.pid) moveJoy(ev); });
  const endJoy = (ev) => {
    if (ev && ev.pointerId !== joyState.pid) return;
    joyState.active = false; joyState.x = 0; joyState.y = 0; joyState.pid = null;
    $("joy-knob").style.transform = "translate(-50%,-50%)";
  };
  joy.addEventListener("pointerup", endJoy);
  joy.addEventListener("pointercancel", endJoy);
}

function moveJoy(ev) {
  const base = ev.currentTarget.querySelector(".joy-base") || ev.currentTarget;
  const r = base.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  let dx = ev.clientX - cx, dy = ev.clientY - cy;
  const max = r.width * 0.42;
  const len = Math.hypot(dx, dy) || 1;
  if (len > max) { dx = (dx / len) * max; dy = (dy / len) * max; }
  $("joy-knob").style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
  // Screen Y down should move toward camera / +Z in world (south is +Z? Wait)
  // Waypoints: hive is north. In Blender Y+ was north (hive). After glTF, Blender +Y becomes -Z.
  // So hive is at negative Z, base at positive Z. Camera is at +Z looking toward -Z (hive).
  // Joystick up (negative screen Y) should move toward hive ( -Z ).
  joyState.x = dx / max;
  joyState.y = -dy / max; // up = -Z? if y is used as iz... updateMech uses iz as z velocity.
  // I set joyState.y from -dy, so joystick up => joyState.y > 0 => m.z increases => toward camera / base.
  // That's backward if up should be "forward from camera into the map".
  // Camera looks toward -Z, so "forward" (into the map, toward hive) is -Z.
  // Joystick up should be iz < 0. So joyState.y should be +dy or we invert when applying.
  // In updateMech: iz = joyState.y. I'll store joystick-up as negative Z:
  joyState.y = dy / max; // up (dy<0) => negative z => toward hive. Good.
}

function onPointerDown(ev) {
  if (game.phase !== "playing") return;
  // Don't steal joystick
  if (ev.target.closest && ev.target.closest("#joystick, .build-bar, .sheet, .hud-top, .wave-banner")) return;
  const hit = pick(ev);
  if (!hit) {
    if (game.mech) {
      const ground = pickGround(ev);
      if (ground) game.mech.dest = { x: ground.x, z: ground.z };
    }
    game.selectedPad = null;
    game.selectedTower = null;
    $("tower-sheet").classList.add("hidden");
    return;
  }
  if (hit.pad) {
    if (hit.pad.tower) openSheet(hit.pad.tower);
    else {
      game.selectedPad = hit.pad;
      game.selectedTower = null;
      $("tower-sheet").classList.add("hidden");
      // If a type is already selected, build immediately on second-style: tap pad builds selected
      placeTower(hit.pad, game.selectedType);
      game.selectedPad = null;
    }
    AudioFX.ui();
  }
}

function onPointerMove() {}
function onPointerUp() {}

function ndcFromEvent(ev) {
  const r = canvas.getBoundingClientRect();
  pointer.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
  pointer.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
}

function pick(ev) {
  ndcFromEvent(ev);
  raycaster.setFromCamera(pointer, camera);
  const meshes = game.pads.map((p) => p.mesh).filter(Boolean);
  const hits = raycaster.intersectObjects(meshes, true);
  if (!hits.length) return null;
  let obj = hits[0].object;
  while (obj && !/^Pad_\d+/.test(obj.name)) obj = obj.parent;
  const pad = game.pads.find((p) => p.mesh === obj || (obj && p.mesh && p.mesh.getObjectById && p.mesh.name === obj.name));
  // walk up to find pad by name
  const name = obj && obj.name;
  const found = game.pads.find((p) => p.mesh.name === name);
  if (found) return { pad: found };
  return null;
}

function pickGround(ev) {
  ndcFromEvent(ev);
  raycaster.setFromCamera(pointer, camera);
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const pt = new THREE.Vector3();
  if (raycaster.ray.intersectPlane(plane, pt)) return pt;
  return null;
}

function endGame() {
  if (game.phase !== "playing") return;
  game.phase = "gameover";
  game.spawning = false;
  if (game.score > game.best) {
    game.best = game.score;
    localStorage.setItem(BEST_KEY, String(game.best));
  }
  retractMech(true);
  $("go-wave").textContent = String(game.wave);
  $("go-score").textContent = String(Math.floor(game.score));
  $("go-best").textContent = String(Math.floor(game.best));
  $("go-credits").textContent = String(Math.floor(game.credits));
  $("gameover").classList.remove("hidden");
  AudioFX.boom();
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------
function tick() {
  const raw = Math.min(clock.getDelta(), 0.05);
  const dt = raw * game.timeScale;
  game.elapsed += dt;

  if (game.phase === "playing") {
    if (game.prep > 0 && !game.spawning) {
      game.prep -= dt;
      const n = game.wave + 1;
      $("wave-banner-text").textContent = `Wave ${n} in ${Math.max(0, game.prep).toFixed(0)}s`;
      if (game.prep <= 0) launchWave();
    }
    if (game.spawning) {
      game.waveTimer -= dt;
      const interval = Math.max(0.18, 0.55 - game.wave * 0.03);
      if (game.waveQueue.length && game.waveTimer <= 0) {
        spawnEnemy(game.waveQueue.shift());
        game.waveTimer = interval;
      }
    }
    updateEnemies(dt);
    updateTowers(dt);
    updateProjectiles(dt);
    updateMech(dt);
    maybeFinishWave();
  } else {
    // idle: slowly pulse hive light
    syncPacks();
  }

  updateFx(dt);
  if (game.phase === "playing" || game.phase === "home") pulsePads(dt);

  hiveLight.intensity = 14 + Math.sin(game.elapsed * 2.2) * 4;
  // camera shake
  if (game.shake > 0) {
    const s = game.shake;
    camera.position.x += (Math.random() - 0.5) * s * 0.6;
    camera.position.y += (Math.random() - 0.5) * s * 0.4;
    game.shake = Math.max(0, game.shake - dt * 2.2);
    if (game.shake === 0) fitCamera();
  }

  composer.render();
}

function exposeDebug() {
  window.__HIVE = {
    start: () => { if (game.phase !== "playing") startPlaying(); },
    place: (i, type) => placeTower(game.pads[i], type),
    deployMech: (x, z) => deployMech(x, z),
    setSpeed: (s) => { game.timeScale = s; },
    getState: () => ({
      phase: game.phase, credits: game.credits, score: game.score, best: game.best,
      wave: game.wave, baseHp: game.baseHp, towers: game.towers.length,
      enemies: game.enemies.filter((e) => e.alive).length,
      mech: !!game.mech, pads: game.pads.length, waypoints: game.waypoints.length,
    }),
    killBase: () => { game.baseHp = 0; endGame(); },
    skipWave: () => { if (game.prep > 0) launchWave(); },
    setCredits: (n) => { game.credits = n; syncHUD(); },
    spawn: (type, n = 1) => { for (let i = 0; i < n; i++) spawnEnemy(type); },
    game,
  };
}

boot().catch((err) => {
  console.error(err);
  $("loader-text").textContent = "Failed to load. Refresh to try again.";
});

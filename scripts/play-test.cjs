const { chromium } = require("/usr/local/lib/pnpm/5/.pnpm/playwright-core@1.59.1/node_modules/playwright-core");
const path = require("path");
const fs = require("fs");
const { execSync } = require("child_process");

const OUT = path.resolve("/workspace/hive-breach/shots");
fs.mkdirSync(OUT, { recursive: true });
const URL = process.env.HIVE_URL || "http://127.0.0.1:8765/";

(async () => {
  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    headless: true,
    args: [
      "--no-sandbox", "--disable-dev-shm-usage",
      "--use-gl=angle", "--use-angle=swiftshader",
      "--enable-webgl", "--ignore-gpu-blocklist",
      "--autoplay-policy=no-user-gesture-required",
    ],
  });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    recordVideo: { dir: path.join(OUT, "_video"), size: { width: 390, height: 844 } },
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => console.log("PAGEERROR", e.message));
  page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE", m.text()); });

  await page.goto(URL, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForFunction(() => window.__HIVE && window.__HIVE.getState().phase === "home", { timeout: 30000 });
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, "1-home.png") });
  console.log("1-home");

  // Hidden-UI map framing check
  await page.evaluate(() => {
    document.getElementById("home").classList.add("hidden");
    document.getElementById("hud").classList.add("hidden");
  });
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(OUT, "_map.png") });
  console.log("map");
  await page.evaluate(() => document.getElementById("home").classList.remove("hidden"));

  await page.tap("#btn-start");
  await page.waitForFunction(() => window.__HIVE.getState().phase === "playing", { timeout: 10000 });
  await page.waitForTimeout(300);

  await page.evaluate(() => {
    const H = window.__HIVE;
    H.setCredits(2000);
    // A few towers near the first bend, so the swarm is visible on the path
    H.place(0, "laser");
    H.place(1, "laser");
    H.place(2, "tesla");
    H.place(5, "rocket");
    H.skipWave();
    H.setSpeed(0.55);
    // Seed a visible crowd along the first half of the path
    const g = H.game;
    for (let i = 0; i < 14; i++) {
      const e = (() => { H.spawn(i === 10 ? "tank" : "grunt"); return g.enemies[g.enemies.length - 1]; })();
      e.dist = 4 + i * 1.7;
    }
  });
  await page.waitForFunction(() => window.__HIVE.getState().enemies >= 8, { timeout: 10000 });
  await page.waitForTimeout(900);
  await page.screenshot({ path: path.join(OUT, "2-wave.png") });
  console.log("2-wave", await page.evaluate(() => window.__HIVE.getState()));

  const mech = await page.evaluate(() => {
    const H = window.__HIVE;
    const wps = H.game.waypoints;
    const mid = wps[4];
    return { ok: H.deployMech(mid.x + 2.2, mid.z), mid };
  });
  console.log("mech", mech);
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "3-mech.png") });
  console.log("3-mech", await page.evaluate(() => window.__HIVE.getState()));

  await page.waitForTimeout(2800);
  await page.evaluate(() => window.__HIVE.killBase());
  await page.waitForFunction(() => window.__HIVE.getState().phase === "gameover", { timeout: 8000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, "4-gameover.png") });
  console.log("4-gameover", await page.evaluate(() => window.__HIVE.getState()));

  const video = await page.video().path();
  await context.close();
  await browser.close();
  const outMp4 = path.join(OUT, "gameplay.mp4");
  execSync(`ffmpeg -y -i ${JSON.stringify(video)} -t 14 -an -c:v libx264 -pix_fmt yuv420p -crf 22 -movflags +faststart ${JSON.stringify(outMp4)}`, { stdio: "inherit" });
  console.log("video", outMp4, fs.statSync(outMp4).size);
  console.log("DONE");
})().catch((e) => { console.error(e); process.exit(1); });

// 截图脚本：预览页整页 + 各 wrapper 2x PNG
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const EXE = "C:\\Users\\LeeNiuBi\\AppData\\Local\\ms-playwright\\chromium-1223\\chrome-win64\\chrome.exe";
const LOGO_DIR = "C:\\Users\\LeeNiuBi\\Desktop\\shangmentiyu\\generated-logos";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE });
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 2 });

  // 1) 整页预览
  await page.goto("file:///" + path.join(LOGO_DIR, "preview.html").replace(/\\/g, "/"));
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(LOGO_DIR, "_review_full.png"), fullPage: true });
  console.log("review screenshot done");

  // 2) 各 wrapper PNG
  const tsv = fs.readFileSync(path.join(LOGO_DIR, "_wrappers.tsv"), "utf-8").trim().split("\n");
  for (const line of tsv) {
    const [name, w, h] = line.split("\t");
    await page.setViewportSize({ width: Number(w), height: Number(h) });
    await page.goto("file:///" + path.join(LOGO_DIR, "png_wrappers", name + ".html").replace(/\\/g, "/"));
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(LOGO_DIR, name + ".png"), clip: { x: 0, y: 0, width: Number(w), height: Number(h) } });
    console.log("png:", name);
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });

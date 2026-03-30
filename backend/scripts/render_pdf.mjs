import fs from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

const inputPath = process.argv[2];

if (!inputPath) {
  console.error("Usage: node render_pdf.mjs <input-json>");
  process.exit(1);
}

const raw = await fs.readFile(inputPath, "utf8");
const payload = JSON.parse(raw);

const executablePath =
  payload.chromePath ||
  process.env.PBA_CHROME_PATH ||
  process.env.CHROME_PATH ||
  "/usr/bin/google-chrome";

const browser = await puppeteer.launch({
  executablePath,
  headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox", "--font-render-hinting=medium"],
});

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1240, height: 1754, deviceScaleFactor: 2 });
  await page.emulateMediaType("print");
  await page.setContent(payload.html, { waitUntil: "networkidle0" });

  await fs.mkdir(path.dirname(payload.outputPath), { recursive: true });

  await page.pdf({
    path: payload.outputPath,
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: Boolean(payload.headerTemplate || payload.footerTemplate),
    headerTemplate: payload.headerTemplate || "<div></div>",
    footerTemplate: payload.footerTemplate || "<div></div>",
    margin: payload.margin || {
      top: "90px",
      right: "48px",
      bottom: "78px",
      left: "48px",
    },
  });
} finally {
  await browser.close();
}

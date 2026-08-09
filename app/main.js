const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");

const API_PORT = 47831;
const LOCAL_API_TOKEN = crypto.randomBytes(32).toString("hex");
let apiBase = `http://127.0.0.1:${API_PORT}`;
let apiToken = LOCAL_API_TOKEN;
let usesExternalBackend = false;
let apiProcess = null;

function loadBackendConfiguration() {
  const configPath = path.join(app.getPath("userData"), "backend.json");
  let fileConfig = {};
  try {
    fileConfig = JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch (_error) {
    fileConfig = {};
  }
  const configuredBase = process.env.GLYPH_API_BASE || fileConfig.api_base;
  const configuredToken = process.env.GLYPH_API_TOKEN || fileConfig.api_token;
  if (configuredBase) {
    const parsed = new URL(configuredBase);
    if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error("Glyph backend must use HTTP or HTTPS");
    if (!configuredToken) throw new Error("Glyph backend token is missing");
    apiBase = configuredBase.replace(/\/$/, "");
    apiToken = configuredToken;
    usesExternalBackend = true;
  }
  process.env.GLYPH_API_BASE = apiBase;
  process.env.GLYPH_API_TOKEN = apiToken;
}

async function requestBackend(pathname, options = {}) {
  if (!String(pathname).startsWith("/api/")) throw new Error("Glyph API paths must begin with /api/");
  const response = await fetch(`${apiBase}${pathname}`, {
    method: options.method || "GET",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${apiToken}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body || undefined,
  });
  const text = await response.text();
  let value;
  try {
    value = text ? JSON.parse(text) : {};
  } catch (_error) {
    throw new Error(`Glyph backend returned invalid JSON (${response.status})`);
  }
  if (!response.ok) throw new Error(value.error || `Glyph backend request failed (${response.status})`);
  return value;
}

async function uploadSourceFile(filePath, prompt = "", origin = "upload") {
  const extension = path.extname(filePath).toLowerCase();
  if (![".png", ".jpg", ".jpeg", ".webp"].includes(extension)) {
    throw new Error("Choose a PNG, JPEG, or WebP image");
  }
  const data = fs.readFileSync(filePath);
  if (data.length > 50 * 1024 * 1024) throw new Error("Source images must be smaller than 50 MB");
  const project = await requestBackend("/api/source/upload", {
    method: "POST",
    body: JSON.stringify({
      filename: path.basename(filePath),
      base64: data.toString("base64"),
      prompt,
      origin,
    }),
  });
  const source = project.source?.versions?.find((item) => item.id === project.source.active_id);
  return { project, source_id: source?.id || null, preview_url: `data:image/${extension === ".jpg" || extension === ".jpeg" ? "jpeg" : extension.slice(1)};base64,${data.toString("base64")}` };
}

function projectRoot() {
  return app.getAppPath();
}

function pythonExecutable() {
  const candidates = [
    process.env.GLYPH_PYTHON,
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python3",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || "python3";
}

function harnessEnvironment() {
  const home = app.getPath("home");
  const nvmRoot = path.join(home, ".nvm", "versions", "node");
  let nvmBins = [];
  try {
    nvmBins = fs.readdirSync(nvmRoot, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => path.join(nvmRoot, entry.name, "bin"))
      .sort()
      .reverse();
  } catch (_error) {
    nvmBins = [];
  }
  const searchPath = [
    ...nvmBins,
    "/opt/homebrew/bin",
    "/usr/local/bin",
    process.env.PATH || "/usr/bin:/bin:/usr/sbin:/sbin",
  ].join(":");
  return { ...process.env, GLYPH_API_TOKEN: apiToken, PATH: searchPath, PYTHONUNBUFFERED: "1" };
}

function startHarness() {
  const root = projectRoot();
  const workspace = path.join(app.getPath("userData"), "workspace");
  apiProcess = spawn(
    pythonExecutable(),
    ["-m", "glyph_harness.server", "--port", String(API_PORT), "--project-root", root, "--workspace", workspace],
    { cwd: root, env: harnessEnvironment() }
  );
  apiProcess.stdout.on("data", (chunk) => process.stdout.write(`[harness] ${chunk}`));
  apiProcess.stderr.on("data", (chunk) => process.stderr.write(`[harness] ${chunk}`));
  apiProcess.on("error", (error) => {
    console.error(`Glyph harness failed to spawn: ${error.message}`);
  });
  apiProcess.on("exit", (code) => {
    if (!app.isQuitting && code) console.error(`Glyph harness exited with ${code}`);
  });
}

function waitForBackend(attempts = 80) {
  return new Promise((resolve, reject) => {
    const check = () => requestBackend("/api/health").then(resolve).catch(retry);
    const retry = () => {
      if (--attempts <= 0) reject(new Error(`Glyph backend did not respond at ${apiBase}`));
      else setTimeout(check, 150);
    };
    check();
  });
}

async function createWindow() {
  const window = new BrowserWindow({
    width: 1536,
    height: 1024,
    minWidth: 1120,
    minHeight: 720,
    titleBarStyle: "hiddenInset",
    backgroundColor: "#111315",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  window.webContents.on("console-message", (_event, details) => {
    console.log(`[renderer:${details.level}] ${details.message} (${details.sourceId}:${details.lineNumber})`);
  });
  window.webContents.on("did-fail-load", (_event, code, description) => {
    console.error(`[renderer] load failed ${code}: ${description}`);
  });
  await waitForBackend();
  await window.loadFile(path.join(__dirname, "renderer", "index.html"));
}

ipcMain.handle("glyph-api", (_event, pathname, options) => requestBackend(pathname, options));
ipcMain.handle("glyph-import-source", (_event, source) => uploadSourceFile(source.path, source.prompt, source.origin));
ipcMain.handle("glyph-import-preset", (_event, preset) => {
  const presetPath = path.join(projectRoot(), "app", "assets", "source-presets", preset.filename);
  return uploadSourceFile(presetPath, `Built-in source: ${preset.label}`, `preset:${preset.id}`);
});

ipcMain.handle("choose-blend", async () => {
  const result = await dialog.showOpenDialog({
    title: "Open a Blender project in Glyph",
    properties: ["openFile"],
    filters: [{ name: "Blender Projects", extensions: ["blend"] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("choose-reference", async () => {
  const result = await dialog.showOpenDialog({
    title: "Attach a reference image",
    properties: ["openFile"],
    filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "webp"] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("choose-source", async () => {
  const result = await dialog.showOpenDialog({
    title: "Choose a source image for Glyph",
    properties: ["openFile"],
    filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "webp"] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("choose-mesh", async () => {
  const result = await dialog.showOpenDialog({
    title: "Approve a TRELLIS mesh in Glyph",
    properties: ["openFile"],
    filters: [{ name: "3D Meshes", extensions: ["glb", "gltf"] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

app.whenReady().then(async () => {
  try {
    loadBackendConfiguration();
    if (!usesExternalBackend) startHarness();
    await createWindow();
  } catch (error) {
    dialog.showErrorBox("Glyph could not start", error.message);
    app.quit();
  }
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (apiProcess && !apiProcess.killed) apiProcess.kill("SIGTERM");
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

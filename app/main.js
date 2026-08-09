const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const fs = require("fs");
const crypto = require("crypto");

const API_PORT = 47831;
const API_TOKEN = crypto.randomBytes(32).toString("hex");
process.env.GLYPH_API_TOKEN = API_TOKEN;
let apiProcess = null;

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
  return { ...process.env, GLYPH_API_TOKEN: API_TOKEN, PATH: searchPath, PYTHONUNBUFFERED: "1" };
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

function waitForHarness(attempts = 80) {
  return new Promise((resolve, reject) => {
    const check = () => {
      const request = http.get({
        hostname: "127.0.0.1",
        port: API_PORT,
        path: "/api/health",
        headers: { Authorization: `Bearer ${API_TOKEN}` },
      }, (response) => {
        response.resume();
        if (response.statusCode === 200) resolve();
        else retry();
      });
      request.on("error", retry);
      request.setTimeout(500, () => request.destroy());
    };
    const retry = () => {
      if (--attempts <= 0) reject(new Error("Glyph harness did not start"));
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
  await waitForHarness();
  await window.loadFile(path.join(__dirname, "renderer", "index.html"));
}

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
  startHarness();
  try {
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

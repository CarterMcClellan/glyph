const { contextBridge, ipcRenderer } = require("electron");

function localFileUrl(filePath) {
  const encodedPath = String(filePath)
    .replace(/\\/g, "/")
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `file://${encodedPath}`;
}

contextBridge.exposeInMainWorld("glyphDesktop", {
  api: (path, options) => ipcRenderer.invoke("glyph-api", path, options),
  importSource: (source) => ipcRenderer.invoke("glyph-import-source", source),
  importPreset: (preset) => ipcRenderer.invoke("glyph-import-preset", preset),
  apiBase: process.env.GLYPH_API_BASE,
  chooseBlend: () => ipcRenderer.invoke("choose-blend"),
  chooseSource: () => ipcRenderer.invoke("choose-source"),
  chooseReference: () => ipcRenderer.invoke("choose-reference"),
  chooseMesh: () => ipcRenderer.invoke("choose-mesh"),
  toFileUrl: localFileUrl,
});

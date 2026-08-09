const { contextBridge, ipcRenderer } = require("electron");
const { pathToFileURL } = require("url");

contextBridge.exposeInMainWorld("glyphDesktop", {
  apiBase: "http://127.0.0.1:47831",
  apiToken: process.env.GLYPH_API_TOKEN,
  chooseBlend: () => ipcRenderer.invoke("choose-blend"),
  chooseSource: () => ipcRenderer.invoke("choose-source"),
  chooseReference: () => ipcRenderer.invoke("choose-reference"),
  chooseMesh: () => ipcRenderer.invoke("choose-mesh"),
  toFileUrl: (path) => pathToFileURL(path).href,
});

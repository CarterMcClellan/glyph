import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const BUNDLED_SOURCE_PRESETS = [
  { id: "voxel-apprentice", label: "Voxel Apprentice", description: "Chunky 3D style", filename: "voxel-apprentice.png", asset: "../assets/source-presets/voxel-apprentice.png" },
  { id: "illustrated-apprentice", label: "Storybook Apprentice", description: "Clean illustrated style", filename: "illustrated-apprentice.png", asset: "../assets/source-presets/illustrated-apprentice.png" },
  { id: "voxel-elder", label: "Voxel Elder", description: "Tall block-built style", filename: "voxel-elder.png", asset: "../assets/source-presets/voxel-elder.png" },
  { id: "arcane-mage", label: "Arcane Mage", description: "Detailed fantasy style", filename: "arcane-mage.png", asset: "../assets/source-presets/arcane-mage.png" },
];

const state = {
  project: null,
  scene: null,
  activeObject: null,
  selectedFaces: new Set(),
  reference: null,
  previewActive: false,
  context: null,
  settings: {},
  auth: { available: false, signed_in: false },
  sourcePresets: [],
  sourcePreview: null,
  trellisContract: null,
  viewMode: "lit",
  sceneCollapsed: false,
};

const elements = Object.fromEntries(
  [
    "workspace", "viewport", "viewport-stats", "viewport-empty", "scene-tree", "scene-search", "scene-collapse", "open-project",
    "instruction", "attach-reference", "reference-chip", "generate-preview",
    "accept-preview", "reject-preview", "clear-selection", "object-chip", "face-chip",
    "vertex-chip", "selection-preview", "harness-steps", "harness-status", "settings-button",
    "settings-dialog", "model-setting", "trellis-endpoint", "save-settings", "send-trellis",
    "trellis-status", "toast", "select-tool", "move-tool", "view-mesh", "view-render", "view-lit",
    "imagine-workspace", "mesh-workspace", "workflow-status", "status-imagine", "status-mesh", "status-edit",
    "editor-toolbar", "viewport-modes", "fork-project", "source-preview", "source-image", "source-heading", "source-subheading",
    "source-placeholder", "source-presets", "import-source", "replace-source", "lock-source", "source-ready-title", "source-ready-copy",
    "lock-dialog", "lock-confirmation", "chatgpt-auth", "chatgpt-auth-label", "settings-auth-card",
    "settings-auth-title", "settings-auth-detail", "settings-sign-in",
    "confirm-lock", "locked-source-image", "locked-source-version", "locked-source-hash", "locked-source-prompt",
    "mesh-source-ghost", "mesh-job-pill", "mesh-progress-title", "mesh-progress-percent", "mesh-progress-bar",
    "mesh-progress-copy", "mesh-state-icon", "meshify-animation", "meshify-canvas", "conversion-upload", "conversion-validate", "start-meshify",
    "refresh-meshify", "approve-mesh",
  ].map((id) => [id.replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase()), document.getElementById(id)])
);

let renderer;
let camera;
let controls;
let threeScene;
let meshRoot;
let raycaster;
let pointer;
let pointerDown;
let meshifyLottie;
const meshifyVisual = {
  context: null,
  image: null,
  source: "",
  meshLayer: null,
  effectLayer: null,
  rect: null,
  width: 0,
  height: 0,
  progress: 0,
  status: "ready",
};
const meshViews = new Map();

async function api(path, options = {}) {
  return window.glyphDesktop.api(path, { method: options.method || "GET", body: options.body });
}

function initViewport() {
  threeScene = new THREE.Scene();
  threeScene.background = new THREE.Color(0xf3f0fb);
  camera = new THREE.PerspectiveCamera(38, 1, 0.01, 5000);
  camera.position.set(3.8, 2.8, 4.8);
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  elements.viewport.prepend(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.target.set(0, 0, 0);
  raycaster = new THREE.Raycaster();
  pointer = new THREE.Vector2();
  meshRoot = new THREE.Group();
  meshRoot.rotation.x = -Math.PI / 2;
  threeScene.add(meshRoot);

  const hemisphere = new THREE.HemisphereLight(0xffffff, 0xd9d0ec, 2.25);
  threeScene.add(hemisphere);
  const key = new THREE.DirectionalLight(0xffffff, 2.5);
  key.position.set(4, 7, 5);
  threeScene.add(key);
  const rim = new THREE.DirectionalLight(0x8b7be8, 1.15);
  rim.position.set(-5, 2, -4);
  threeScene.add(rim);
  const grid = new THREE.GridHelper(30, 30, 0x9a8ed8, 0xd8d0e8);
  grid.material.opacity = 0.42;
  grid.material.transparent = true;
  grid.position.y = -1.6;
  threeScene.add(grid);

  renderer.domElement.addEventListener("pointerdown", (event) => {
    pointerDown = { x: event.clientX, y: event.clientY };
  });
  renderer.domElement.addEventListener("pointerup", (event) => {
    if (!pointerDown || Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 4) return;
    selectAt(event);
  });
  window.addEventListener("resize", resizeViewport);
  resizeViewport();
  animate();
}

function initMeshifyAnimation() {
  if (meshifyLottie || !elements.meshifyAnimation || !window.lottie) return;
  try {
    meshifyLottie = window.lottie.loadAnimation({
      container: elements.meshifyAnimation,
      renderer: "svg",
      loop: true,
      autoplay: true,
      path: new URL("../assets/animations/meshify-magic.json", import.meta.url).href,
      rendererSettings: { preserveAspectRatio: "xMidYMid meet", progressiveLoad: true },
    });
    meshifyLottie.setSpeed(0.78);
    meshifyLottie.addEventListener("DOMLoaded", () => {
      elements.meshStateIcon.parentElement.classList.add("lottie-ready");
    });
    meshifyLottie.addEventListener("data_failed", () => {
      elements.meshStateIcon.parentElement.classList.remove("lottie-ready");
    });
  } catch (_error) {
    meshifyLottie = null;
  }
}

function meshNoise(column, row) {
  const value = Math.sin(column * 91.173 + row * 47.719) * 43758.5453;
  return value - Math.floor(value);
}

function drawMagicStar(context, x, y, radius, color, rotation = 0) {
  context.save();
  context.translate(x, y);
  context.rotate(rotation);
  context.beginPath();
  for (let index = 0; index < 8; index += 1) {
    const angle = -Math.PI / 2 + (index * Math.PI) / 4;
    const length = index % 2 === 0 ? radius : radius * 0.25;
    context.lineTo(Math.cos(angle) * length, Math.sin(angle) * length);
  }
  context.closePath();
  context.fillStyle = color;
  context.fill();
  context.restore();
}

function rebuildMeshifyLayers() {
  const canvas = elements.meshifyCanvas;
  const image = meshifyVisual.image;
  if (!canvas || !image?.naturalWidth) return;
  const parent = canvas.parentElement;
  const width = parent.clientWidth;
  const height = parent.clientHeight;
  if (!width || !height) return;
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * pixelRatio);
  canvas.height = Math.round(height * pixelRatio);
  meshifyVisual.context = canvas.getContext("2d");
  meshifyVisual.context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  meshifyVisual.width = width;
  meshifyVisual.height = height;

  const scale = Math.min((width * 0.82) / image.naturalWidth, (height * 0.98) / image.naturalHeight);
  const drawWidth = image.naturalWidth * scale;
  const drawHeight = image.naturalHeight * scale;
  const x = (width - drawWidth) / 2;
  const y = (height - drawHeight) / 2 + height * 0.015;
  meshifyVisual.rect = { x, y, width: drawWidth, height: drawHeight };

  const meshLayer = document.createElement("canvas");
  meshLayer.width = Math.ceil(width);
  meshLayer.height = Math.ceil(height);
  const meshContext = meshLayer.getContext("2d");
  meshContext.drawImage(image, x, y, drawWidth, drawHeight);
  meshContext.globalCompositeOperation = "source-in";
  meshContext.fillStyle = "rgba(246, 242, 255, 0.96)";
  meshContext.fillRect(x, y, drawWidth, drawHeight);
  meshContext.globalCompositeOperation = "source-over";

  const columns = 11;
  const rows = Math.max(12, Math.round(columns * drawHeight / Math.max(drawWidth, 1)));
  const stepX = drawWidth / columns;
  const stepY = drawHeight / rows;
  const points = [];
  for (let row = 0; row <= rows; row += 1) {
    const line = [];
    for (let column = 0; column <= columns; column += 1) {
      const edge = column === 0 || column === columns || row === 0 || row === rows;
      const jitterX = edge ? 0 : (meshNoise(column, row) - 0.5) * stepX * 0.48;
      const jitterY = edge ? 0 : (meshNoise(row + 17, column + 29) - 0.5) * stepY * 0.48;
      line.push({ x: x + column * stepX + jitterX, y: y + row * stepY + jitterY });
    }
    points.push(line);
  }
  meshContext.lineJoin = "round";
  meshContext.lineCap = "round";
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const a = points[row][column];
      const b = points[row][column + 1];
      const c = points[row + 1][column + 1];
      const d = points[row + 1][column];
      const diagonalForward = (row + column) % 2 === 0;
      const triangles = diagonalForward ? [[a, b, c], [a, c, d]] : [[a, b, d], [b, c, d]];
      for (const triangle of triangles) {
        meshContext.beginPath();
        meshContext.moveTo(triangle[0].x, triangle[0].y);
        meshContext.lineTo(triangle[1].x, triangle[1].y);
        meshContext.lineTo(triangle[2].x, triangle[2].y);
        meshContext.closePath();
        meshContext.fillStyle = (row + column) % 3 === 0 ? "rgba(126, 105, 218, 0.105)" : "rgba(126, 105, 218, 0.035)";
        meshContext.fill();
        meshContext.strokeStyle = "rgba(100, 78, 191, 0.82)";
        meshContext.lineWidth = 1.15;
        meshContext.stroke();
      }
    }
  }
  meshContext.globalCompositeOperation = "destination-in";
  meshContext.drawImage(image, x, y, drawWidth, drawHeight);
  meshContext.globalCompositeOperation = "source-over";
  meshifyVisual.meshLayer = meshLayer;

  const effectLayer = document.createElement("canvas");
  effectLayer.width = Math.ceil(width);
  effectLayer.height = Math.ceil(height);
  meshifyVisual.effectLayer = effectLayer;
  parent.classList.add("canvas-ready");
}

function setMeshifyCanvasSource(source) {
  if (!source || meshifyVisual.source === source) return;
  meshifyVisual.source = source;
  const image = new Image();
  image.addEventListener("load", () => {
    meshifyVisual.image = image;
    rebuildMeshifyLayers();
  }, { once: true });
  image.addEventListener("error", () => {
    elements.meshifyCanvas?.parentElement.classList.remove("canvas-ready");
  }, { once: true });
  image.src = source;
}

function renderMeshifyFrame(time) {
  const { context, image, meshLayer, effectLayer, rect, width, height } = meshifyVisual;
  if (!context || !image || !meshLayer || !effectLayer || !rect) return;
  context.clearRect(0, 0, width, height);
  const seconds = time / 1000;
  const running = meshifyVisual.status === "running";
  const complete = meshifyVisual.status === "complete";
  const failed = meshifyVisual.status === "failed";
  const progressRatio = Math.max(0, Math.min(1, meshifyVisual.progress / 100));
  const baseSplit = complete ? 0.2 : running ? 0.31 + progressRatio * 0.47 : 0.55;
  const shimmer = failed ? 0 : Math.sin(seconds * 1.55) * (running ? 0.022 : 0.012);
  const split = rect.x + rect.width * Math.max(0.16, Math.min(0.82, baseSplit + shimmer));

  context.save();
  context.translate(rect.x + rect.width / 2, rect.y + rect.height / 2);
  context.scale(1.18, 0.72);
  const halo = context.createRadialGradient(0, 0, 8, 0, 0, rect.height * 0.62);
  halo.addColorStop(0, "rgba(255, 255, 255, 0.82)");
  halo.addColorStop(0.48, "rgba(226, 217, 250, 0.38)");
  halo.addColorStop(1, "rgba(226, 217, 250, 0)");
  context.fillStyle = halo;
  context.beginPath();
  context.arc(0, 0, rect.height * 0.62, 0, Math.PI * 2);
  context.fill();
  context.restore();

  context.save();
  context.beginPath();
  context.rect(0, 0, split + 3, height);
  context.clip();
  context.globalAlpha = failed ? 0.48 : 1;
  context.drawImage(image, rect.x, rect.y, rect.width, rect.height);
  context.restore();

  context.save();
  context.beginPath();
  context.rect(split - 3, 0, width - split + 3, height);
  context.clip();
  context.globalAlpha = failed ? 0.35 : complete ? 0.9 : 1;
  context.drawImage(meshLayer, 0, 0);
  context.restore();

  const effectContext = effectLayer.getContext("2d");
  effectContext.clearRect(0, 0, width, height);
  const pulse = 0.72 + Math.sin(seconds * 3.2) * 0.22;
  effectContext.save();
  effectContext.shadowColor = "rgba(113, 86, 221, 0.72)";
  effectContext.shadowBlur = 13;
  effectContext.strokeStyle = `rgba(105, 79, 211, ${pulse})`;
  effectContext.lineWidth = running ? 4 : 2.5;
  effectContext.setLineDash([12, 7]);
  effectContext.lineDashOffset = -seconds * 28;
  effectContext.beginPath();
  effectContext.moveTo(split, rect.y + 2);
  effectContext.lineTo(split, rect.y + rect.height - 2);
  effectContext.stroke();
  effectContext.restore();
  effectContext.globalCompositeOperation = "destination-in";
  effectContext.drawImage(image, rect.x, rect.y, rect.width, rect.height);
  effectContext.globalCompositeOperation = "source-over";
  context.drawImage(effectLayer, 0, 0);

  if (!failed) {
    const starDrift = Math.sin(seconds * 2.1) * 8;
    const twinkle = 0.72 + Math.sin(seconds * 2.8) * 0.2;
    drawMagicStar(context, split + 17, rect.y + rect.height * 0.29 + starDrift, 13, "rgba(244, 157, 73, 0.95)", seconds * 0.5);
    drawMagicStar(context, split + 31, rect.y + rect.height * 0.7 - starDrift, 8, "rgba(82, 183, 177, 0.9)", -seconds * 0.7);
    drawMagicStar(context, rect.x - 17, rect.y + rect.height * 0.24 - starDrift * 0.35, 7, `rgba(235, 112, 143, ${twinkle})`, -seconds * 0.35);
    drawMagicStar(context, rect.x + rect.width + 22, rect.y + rect.height * 0.19 + starDrift * 0.3, 10, `rgba(235, 112, 143, ${0.82 - Math.sin(seconds * 2.3) * 0.14})`, seconds * 0.32);
    drawMagicStar(context, rect.x + rect.width + 12, rect.y + rect.height * 0.55 + starDrift * 0.5, 6, `rgba(126, 105, 218, ${twinkle})`, seconds * 0.8);
    drawMagicStar(context, rect.x - 8, rect.y + rect.height * 0.78 - starDrift * 0.25, 5, "rgba(244, 157, 73, 0.82)", -seconds * 0.6);
  }
}

function initMeshifyCanvas() {
  if (!elements.meshifyCanvas || meshifyVisual.context) return;
  const observer = new ResizeObserver(() => rebuildMeshifyLayers());
  observer.observe(elements.meshifyCanvas.parentElement);
  const frame = (time) => {
    if (!elements.meshWorkspace.classList.contains("hidden")) renderMeshifyFrame(time);
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function resizeViewport() {
  if (!renderer) return;
  const { clientWidth, clientHeight } = elements.viewport;
  renderer.setSize(clientWidth, clientHeight, false);
  camera.aspect = clientWidth / Math.max(clientHeight, 1);
  camera.updateProjectionMatrix();
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(threeScene, camera);
}

function disposeRoot() {
  for (const child of [...meshRoot.children]) {
    child.traverse((item) => {
      item.geometry?.dispose();
      item.material?.dispose();
    });
    meshRoot.remove(child);
  }
  meshViews.clear();
}

function renderMeshes(fit = false) {
  disposeRoot();
  const objects = state.scene?.objects || [];
  for (const record of objects) {
    if (!record.positions.length) continue;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(record.positions, 3));
    geometry.computeVertexNormals();
    const sourceColor = record.material_color || (record.preview ? [0.58, 0.65, 0.74] : [0.68, 0.71, 0.73]);
    const color = new THREE.Color(sourceColor[0], sourceColor[1], sourceColor[2]);
    let material;
    if (state.viewMode === "mesh") {
      material = new THREE.MeshBasicMaterial({ color: 0x7769c8, transparent: true, opacity: 0.1, depthWrite: false, side: THREE.DoubleSide });
    } else if (state.viewMode === "render") {
      material = new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide });
    } else {
      material = new THREE.MeshStandardMaterial({ color, roughness: 0.68, metalness: 0.04, side: THREE.DoubleSide, flatShading: false });
    }
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.record = record;
    meshRoot.add(mesh);
    const topologyPositions = [];
    for (const [a, b] of record.edges || []) {
      topologyPositions.push(...record.vertex_positions.slice(a * 3, a * 3 + 3));
      topologyPositions.push(...record.vertex_positions.slice(b * 3, b * 3 + 3));
    }
    const topologyGeometry = new THREE.BufferGeometry();
    topologyGeometry.setAttribute("position", new THREE.Float32BufferAttribute(topologyPositions, 3));
    const topology = new THREE.LineSegments(
      topologyGeometry,
      new THREE.LineBasicMaterial({ color: 0x6f62bf, transparent: true, opacity: 0.75 })
    );
    topology.visible = state.viewMode === "mesh";
    mesh.add(topology);
    const highlight = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshStandardMaterial({ color: 0xed7d69, emissive: 0x5c1b13, roughness: 0.58, side: THREE.DoubleSide })
    );
    highlight.renderOrder = 2;
    mesh.add(highlight);
    meshViews.set(record.id, { mesh, highlight, record });
  }
  updateHighlight();
  elements.viewportEmpty.classList.toggle("hidden", objects.length > 0);
  if (fit) fitCamera();
}

function fitCamera() {
  const bounds = new THREE.Box3().setFromObject(meshRoot);
  if (bounds.isEmpty()) return;
  const sphere = bounds.getBoundingSphere(new THREE.Sphere());
  const distance = Math.max(sphere.radius * 3.0, 2.5);
  controls.target.copy(sphere.center);
  camera.position.copy(sphere.center).add(new THREE.Vector3(distance * 0.75, distance * 0.45, distance));
  camera.near = Math.max(distance / 1000, 0.01);
  camera.far = distance * 100;
  camera.updateProjectionMatrix();
  controls.update();
}

function selectAt(event) {
  if (state.previewActive) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects([...meshViews.values()].map((item) => item.mesh), false);
  if (!hits.length) return;
  const hit = hits[0];
  const record = hit.object.userData.record;
  if (state.activeObject !== record.id) {
    state.activeObject = record.id;
    state.selectedFaces.clear();
    renderSceneTree();
  }
  const polygon = record.triangle_polygons[hit.faceIndex];
  if (state.selectedFaces.has(polygon)) state.selectedFaces.delete(polygon);
  else state.selectedFaces.add(polygon);
  updateHighlight();
  updateContext();
}

function updateHighlight() {
  for (const [id, view] of meshViews) {
    const positions = [];
    if (id === state.activeObject) {
      const source = view.record.positions;
      view.record.triangle_polygons.forEach((polygon, triangle) => {
        if (!state.selectedFaces.has(polygon)) return;
        const start = triangle * 9;
        positions.push(...source.slice(start, start + 9));
      });
    }
    const geometry = new THREE.BufferGeometry();
    if (positions.length) {
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      geometry.computeVertexNormals();
    }
    view.highlight.geometry.dispose();
    view.highlight.geometry = geometry;
    view.highlight.position.set(0, 0, 0);
    view.highlight.scale.setScalar(1.002);
  }
}

function activeRecord() {
  return state.scene?.objects.find((item) => item.id === state.activeObject) || null;
}

function selectedVertices(record) {
  if (!record) return new Set();
  const result = new Set();
  for (const polygon of record.polygons) {
    if (state.selectedFaces.has(polygon.index)) polygon.vertices.forEach((vertex) => result.add(vertex));
  }
  return result;
}

function updateContext() {
  const record = activeRecord();
  const faces = state.selectedFaces.size;
  const vertices = selectedVertices(record).size;
  elements.objectChip.textContent = record?.label || "No mesh";
  elements.faceChip.textContent = `${faces || record?.face_count || 0} faces${faces ? "" : " (whole object)"}`;
  elements.vertexChip.textContent = `${vertices || record?.vertex_count || 0} vertices`;
  elements.viewportStats.innerHTML = record
    ? `Vertices&nbsp;&nbsp; ${record.vertex_count.toLocaleString()}<br>Edges&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${record.edge_count.toLocaleString()}<br>Faces&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ${record.face_count.toLocaleString()}`
    : "";
  elements.selectionPreview.innerHTML = record
    ? `<div style="text-align:center"><strong style="display:block;color:#d9685a;font-size:26px">${faces || record.face_count}</strong><span>${faces ? "selected faces" : "whole object selected"}</span></div>`
    : "<span>Select a mesh and click faces</span>";
}

function renderSceneTree() {
  const query = elements.sceneSearch.value.trim().toLowerCase();
  const objectsById = new Map((state.scene?.objects || []).map((item) => [item.id, item]));
  elements.sceneTree.innerHTML = "";
  for (const collection of state.scene?.collections || []) {
    const records = collection.objects.map((id) => objectsById.get(id)).filter(Boolean)
      .filter((item) => !query || item.label.toLowerCase().includes(query) || collection.name.toLowerCase().includes(query));
    if (!records.length) continue;
    const collectionRow = document.createElement("div");
    collectionRow.className = "collection-row";
    collectionRow.innerHTML = `<span class="tree-arrow">⌄</span><span>▣</span><span>${escapeHtml(collection.name)}</span><span class="row-spacer"></span><span>•••</span>`;
    elements.sceneTree.append(collectionRow);
    for (const record of records) {
      const row = document.createElement("div");
      row.className = `object-row${record.id === state.activeObject ? " active" : ""}`;
      row.innerHTML = `<span class="tree-arrow">›</span><span class="mesh-icon">⬡</span><span>${escapeHtml(record.label)}</span><span class="row-spacer"></span>${record.preview ? '<span class="preview-badge">Preview</span>' : '<span class="visibility">◉</span>'}`;
      row.addEventListener("click", () => {
        if (state.previewActive) return;
        state.activeObject = record.id;
        state.selectedFaces.clear();
        renderSceneTree();
        updateHighlight();
        updateContext();
      });
      elements.sceneTree.append(row);
    }
  }
}

function setScene(scene, fit = false) {
  state.scene = scene;
  state.previewActive = Boolean(scene.preview_active);
  if (!scene.objects.some((item) => item.id === state.activeObject)) {
    state.activeObject = scene.objects[0]?.id || null;
    state.selectedFaces.clear();
  }
  renderSceneTree();
  renderMeshes(fit);
  updateContext();
  togglePreviewActions();
}

function togglePreviewActions() {
  elements.acceptPreview.classList.toggle("hidden", !state.previewActive);
  elements.rejectPreview.classList.toggle("hidden", !state.previewActive);
  elements.generatePreview.classList.toggle("hidden", state.previewActive);
}

function renderHarness(steps) {
  elements.harnessSteps.innerHTML = steps.map((step) =>
    `<div class="harness-step"><strong>${escapeHtml(step.name)}</strong><small>${escapeHtml(step.detail)}</small></div>`
  ).join("");
}

function setBusy(busy, label = "Working…") {
  elements.generatePreview.disabled = busy;
  elements.acceptPreview.disabled = busy;
  elements.rejectPreview.disabled = busy;
  elements.harnessStatus.className = `status-dot ${busy ? "running" : "complete"}`;
  if (busy) elements.harnessSteps.innerHTML = `<p>${escapeHtml(label)}</p>`;
  if (!busy) renderAuth();
}

function toast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.className = `toast${error ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => elements.toast.classList.add("hidden"), 4200);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}

function fileUrl(path) {
  return path ? window.glyphDesktop.toFileUrl(path) : "";
}

function sourceDisplayUrl(source) {
  if (state.sourcePreview?.sourceId === source?.id) return state.sourcePreview.url;
  const origin = String(source?.origin || "");
  const presetId = origin.startsWith("preset:") ? origin.slice("preset:".length) : "";
  const preset = state.sourcePresets.find((item) => item.id === presetId);
  return preset?.asset || fileUrl(source?.path);
}

function activeSource() {
  const source = state.project?.source;
  return source?.versions?.find((item) => item.id === source.active_id) || null;
}

function setWorkflowStep(element, status, number) {
  element.className = `workflow-step ${status}`.trim();
  element.querySelector("span").textContent = status === "complete" ? "✓" : String(number);
}

function renderWorkflow() {
  if (!state.project) return;
  const stage = state.project.stage;
  elements.imagineWorkspace.classList.toggle("hidden", stage !== "IMAGINE");
  elements.meshWorkspace.classList.toggle("hidden", stage !== "MESH");
  elements.workspace.classList.toggle("hidden", stage !== "EDIT");
  elements.editorToolbar.classList.toggle("hidden", stage !== "EDIT");
  elements.viewportModes.classList.toggle("hidden", stage !== "EDIT");
  elements.forkProject.classList.toggle("hidden", stage === "IMAGINE");
  elements.openProject.textContent = state.project.name;
  setWorkflowStep(elements.statusImagine, stage === "IMAGINE" ? "active" : "complete", 1);
  setWorkflowStep(elements.statusMesh, stage === "MESH" ? "active" : stage === "EDIT" ? "complete" : "", 2);
  setWorkflowStep(elements.statusEdit, stage === "EDIT" ? "active" : "", 3);
  if (stage === "IMAGINE") renderImagine();
  if (stage === "MESH") renderMesh();
  if (stage === "EDIT") setTimeout(resizeViewport, 20);
  renderAuth();
}

function renderImagine() {
  const source = activeSource();
  elements.sourceImage.classList.toggle("hidden", !source);
  elements.sourcePlaceholder.classList.toggle("hidden", Boolean(source));
  elements.sourcePreview.classList.toggle("empty", !source);
  if (source) elements.sourceImage.src = sourceDisplayUrl(source);
  elements.lockSource.disabled = !source;
  elements.replaceSource.classList.toggle("hidden", !source);
  elements.sourceReadyTitle.textContent = source ? "Source image ready" : "No source image loaded";
  elements.sourceReadyCopy.textContent = source ? "Continue when this is the exact image you want TRELLIS to reconstruct." : "Choose a PNG, JPEG, or WebP image to begin.";
  elements.sourceHeading.textContent = source ? "Your source is ready for 3D." : "Start with the object you want to make 3D.";
  elements.sourceSubheading.textContent = source ? "This image is ready to lock in and turn into a mesh." : "Load one clean image with the full object visible and a simple background.";
  renderSourcePresets();
}

function renderSourcePresets() {
  if (!elements.sourcePresets) return;
  const origin = activeSource()?.origin || "";
  elements.sourcePresets.innerHTML = "";
  for (const preset of state.sourcePresets) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `source-preset${origin === `preset:${preset.id}` ? " active" : ""}`;
    button.dataset.presetId = preset.id;
    button.innerHTML = `<span class="preset-image"><img src="${escapeHtml(preset.asset)}" alt=""></span><strong>${escapeHtml(preset.label)}</strong><small>${escapeHtml(preset.description)}</small>`;
    button.addEventListener("click", () => selectSourcePreset(preset.id));
    elements.sourcePresets.append(button);
  }
}

async function selectSourcePreset(presetId) {
  const buttons = [...elements.sourcePresets.querySelectorAll("button")];
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const preset = state.sourcePresets.find((item) => item.id === presetId);
    const result = await window.glyphDesktop.importPreset(preset);
    state.project = result.project;
    state.sourcePreview = { sourceId: result.source_id, url: result.preview_url };
    renderWorkflow();
    toast("Example selected. Continue when you are ready for TRELLIS.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

function renderAuth() {
  const signedIn = Boolean(state.auth?.signed_in);
  const available = Boolean(state.auth?.available);
  elements.chatgptAuth.classList.toggle("signed-in", signedIn);
  elements.chatgptAuthLabel.textContent = signedIn ? "ChatGPT connected" : available ? "Sign in with ChatGPT" : "ChatGPT unavailable";
  elements.settingsAuthCard.classList.toggle("signed-in", signedIn);
  elements.settingsAuthTitle.textContent = signedIn ? "Signed in with ChatGPT" : "ChatGPT sign-in required";
  elements.settingsAuthDetail.textContent = signedIn
    ? "Glyph Agent is ready for localized mesh edits."
    : state.auth?.detail || "Glyph Agent uses your ChatGPT account—no OpenAI API key.";
  elements.settingsSignIn.textContent = signedIn ? "Connected" : "Sign in";
  elements.settingsSignIn.disabled = signedIn || !available;
  if (state.project?.stage === "EDIT" && !state.previewActive) {
    elements.generatePreview.disabled = !signedIn;
    elements.generatePreview.title = signedIn ? "" : "Sign in with ChatGPT to use Glyph Agent";
  }
}

async function refreshAuth() {
  state.auth = await api("/api/auth/chatgpt");
  renderAuth();
  return state.auth;
}

async function signInWithChatGPT() {
  if (state.auth?.signed_in) return toast("Glyph Agent is connected to ChatGPT");
  const buttons = [elements.chatgptAuth, elements.settingsSignIn];
  buttons.forEach((button) => { button.disabled = true; });
  elements.chatgptAuthLabel.textContent = "Finish sign-in in your browser…";
  try {
    state.auth = await api("/api/auth/chatgpt/login", { method: "POST", body: "{}" });
    renderAuth();
    toast("Signed in with ChatGPT. Glyph Agent is ready.");
  } catch (error) {
    toast(error.message, true);
    await refreshAuth().catch(() => {});
  } finally {
    if (!state.auth?.signed_in) buttons.forEach((button) => { button.disabled = false; });
  }
}

function valueAtPath(payload, path) {
  let value = payload;
  for (const key of String(path).split(".")) {
    if (!value || typeof value !== "object" || !(key in value)) return undefined;
    value = value[key];
  }
  return value;
}

function trellisValue(job, field) {
  const fallbackPaths = {
    job_id: ["job_id", "id"],
    status: ["status", "state"],
    progress: ["progress", "percent"],
    message: ["message", "detail", "error.message"],
    mesh_output: ["mesh_output", "mesh_url", "output.mesh_url", "output.glb_url", "result.mesh_url", "result.glb_url"],
  };
  const paths = state.trellisContract?.response?.fields?.[field] || fallbackPaths[field] || [];
  for (const path of paths) {
    const value = valueAtPath(job, path);
    if (value !== undefined && value !== null) return value;
  }
  return undefined;
}

function trellisStatuses(group, fallback) {
  return state.trellisContract?.response?.statuses?.[group] || fallback;
}

function normalizedJobStatus(job) {
  return String(trellisValue(job, "status") ?? job?.status ?? "ready").toLowerCase();
}

function hasMeshOutput(job) {
  if (!job) return false;
  return typeof trellisValue(job, "mesh_output") === "string";
}

function renderMesh() {
  const locked = state.project.source.locked;
  if (!locked) return;
  const imageUrl = sourceDisplayUrl(locked);
  elements.lockedSourceImage.src = imageUrl;
  elements.meshSourceGhost.src = imageUrl;
  setMeshifyCanvasSource(imageUrl);
  elements.lockedSourceVersion.textContent = locked.id.replace("source-", "Source ");
  elements.lockedSourceHash.textContent = `sha256:${locked.sha256}`;
  elements.lockedSourcePrompt.textContent = locked.prompt || "Imported source";
  const job = state.project.mesh.job;
  const status = normalizedJobStatus(job);
  const runningStatuses = trellisStatuses("running", ["running", "processing", "reconstructing"]);
  const completeStatuses = trellisStatuses("complete", ["completed", "succeeded", "success"]);
  const failedStatuses = trellisStatuses("failed", ["failed", "error", "cancelled", "canceled"]);
  const queuedStatuses = trellisStatuses("queued", ["queued", "pending"]);
  const rawProgress = Number(trellisValue(job, "progress") ?? (completeStatuses.includes(status) ? 100 : runningStatuses.includes(status) ? 54 : job ? 12 : 0));
  const progress = Math.max(0, Math.min(100, rawProgress <= 1 && rawProgress > 0 ? rawProgress * 100 : rawProgress));
  const running = [...queuedStatuses, ...runningStatuses].includes(status);
  const complete = completeStatuses.includes(status);
  const failed = failedStatuses.includes(status);
  meshifyVisual.progress = progress;
  meshifyVisual.status = failed ? "failed" : complete ? "complete" : running ? "running" : "ready";
  elements.meshJobPill.textContent = job ? status.replace(/^./, (value) => value.toUpperCase()) : "Ready";
  elements.meshProgressTitle.textContent = complete ? "Mesh generation complete" : failed ? "Conversion failed" : running ? "TRELLIS is reconstructing" : "Ready to meshify";
  elements.meshProgressPercent.textContent = `${Math.round(progress)}%`;
  elements.meshProgressBar.style.width = `${progress}%`;
  elements.meshProgressCopy.textContent = complete ? "Choose the completed GLB to validate it in Blender and unlock Edit." : failed ? "Retrying will use the same locked source." : running ? "You can leave this screen; the job remains attached to this project." : "The source is locked. Start TRELLIS when your endpoint is configured.";
  elements.meshStateIcon.parentElement.classList.toggle("running", running);
  elements.meshStateIcon.parentElement.classList.toggle("complete", complete);
  elements.meshStateIcon.parentElement.classList.toggle("failed", failed);
  if (meshifyLottie) {
    if (failed) meshifyLottie.pause();
    else meshifyLottie.play();
    meshifyLottie.setSpeed(running ? 1 : complete ? 0.45 : 0.72);
  }
  elements.conversionUpload.classList.toggle("active", running);
  elements.conversionUpload.classList.toggle("complete", complete);
  elements.conversionValidate.classList.toggle("active", complete);
  elements.startMeshify.textContent = failed ? "Retry same locked source" : job ? "Start another conversion" : "Start TRELLIS conversion";
  elements.refreshMeshify.classList.toggle("hidden", !job?.job_id || complete || failed);
  elements.approveMesh.textContent = complete && hasMeshOutput(job) ? "Approve TRELLIS mesh →" : "Choose completed GLB to approve";
  if (running) scheduleMeshPoll(job.job_id);
}

function scheduleMeshPoll(jobId) {
  clearTimeout(scheduleMeshPoll.timer);
  scheduleMeshPoll.timer = setTimeout(() => refreshMeshJob(jobId, true), 3000);
}

async function refreshMeshJob(jobId, silent = false) {
  if (!jobId || state.project?.stage !== "MESH") return;
  try {
    const job = await api(`/api/trellis/jobs/${encodeURIComponent(jobId)}`);
    state.project.mesh.job = job;
    renderMesh();
  } catch (error) {
    if (!silent) toast(error.message, true);
  }
}

async function load() {
  initViewport();
  initMeshifyAnimation();
  initMeshifyCanvas();
  try {
    const [project, settings, auth, sourcePresets, trellisContract] = await Promise.all([
      api("/api/project/state"),
      api("/api/settings"),
      api("/api/auth/chatgpt"),
      api("/api/source/presets"),
      api("/api/trellis/contract"),
    ]);
    state.project = project;
    state.settings = settings;
    state.auth = auth;
    const guides = Array.isArray(sourcePresets) ? sourcePresets : sourcePresets?.presets || [];
    state.sourcePresets = BUNDLED_SOURCE_PRESETS.map((preset, index) => ({
      ...preset,
      guidance: guides[index] || null,
    }));
    state.trellisContract = trellisContract;
    elements.modelSetting.value = settings.model;
    elements.trellisEndpoint.value = settings.trellis_endpoint;
    elements.trellisStatus.textContent = settings.trellis_endpoint ? "Configured" : "Not configured";
    renderWorkflow();
    renderAuth();
    if (project.stage === "EDIT") setScene(await api("/api/scene"), true);
  } catch (error) {
    toast(error.message, true);
  }
}

elements.openProject.addEventListener("click", () => toast(`${state.project?.name || "Glyph project"} · ${state.project?.stage || "Loading"}`));

elements.importSource.addEventListener("click", async () => {
  const path = await window.glyphDesktop.chooseSource();
  if (!path) return;
  elements.importSource.disabled = true;
  try {
    const result = await window.glyphDesktop.importSource({ path, origin: "upload" });
    state.project = result.project;
    state.sourcePreview = { sourceId: result.source_id, url: result.preview_url };
    renderWorkflow();
    toast("Source image imported");
  } catch (error) { toast(error.message, true); }
  finally { elements.importSource.disabled = false; }
});

elements.sourcePreview.addEventListener("click", () => {
  if (state.project?.stage === "IMAGINE") elements.importSource.click();
});
elements.replaceSource.addEventListener("click", () => elements.importSource.click());

elements.lockSource.addEventListener("click", () => {
  elements.lockConfirmation.checked = false;
  elements.confirmLock.disabled = true;
  elements.lockDialog.showModal();
});

elements.lockConfirmation.addEventListener("change", () => {
  elements.confirmLock.disabled = !elements.lockConfirmation.checked;
});

elements.confirmLock.addEventListener("click", async (event) => {
  event.preventDefault();
  if (!elements.lockConfirmation.checked) return;
  elements.confirmLock.disabled = true;
  try {
    state.project = await api("/api/source/lock", { method: "POST", body: JSON.stringify({ confirmed: true }) });
    elements.lockDialog.close();
    renderWorkflow();
    toast("Source locked permanently. TRELLIS is now available.");
  } catch (error) { toast(error.message, true); elements.confirmLock.disabled = false; }
});

elements.forkProject.addEventListener("click", async () => {
  elements.forkProject.disabled = true;
  try {
    state.project = await api("/api/project/fork", { method: "POST", body: "{}" });
    state.scene = null;
    state.selectedFaces.clear();
    renderWorkflow();
    toast("New project fork created. Its source is editable again.");
  } catch (error) { toast(error.message, true); }
  finally { elements.forkProject.disabled = false; }
});

elements.startMeshify.addEventListener("click", async () => {
  elements.startMeshify.disabled = true;
  try {
    const job = await api("/api/trellis/meshify", { method: "POST", body: "{}" });
    state.project.mesh.job = job;
    renderMesh();
    toast(`TRELLIS job ${job.job_id} started`);
  } catch (error) { toast(error.message, true); }
  finally { elements.startMeshify.disabled = false; }
});

elements.refreshMeshify.addEventListener("click", () => refreshMeshJob(state.project?.mesh?.job?.job_id));

elements.approveMesh.addEventListener("click", async () => {
  const job = state.project?.mesh?.job;
  const automatic = trellisStatuses("complete", ["completed", "succeeded", "success"]).includes(normalizedJobStatus(job)) && hasMeshOutput(job);
  const path = automatic ? null : await window.glyphDesktop.chooseMesh();
  if (!automatic && !path) return;
  elements.approveMesh.disabled = true;
  elements.approveMesh.textContent = "Validating in Blender…";
  try {
    const result = await api(automatic ? "/api/mesh/approve-job" : "/api/mesh/approve", {
      method: "POST",
      body: automatic ? "{}" : JSON.stringify({ path }),
    });
    state.project = result.project;
    setScene(result.scene, true);
    renderWorkflow();
    toast("Mesh approved. Local editing is unlocked.");
  } catch (error) { toast(error.message, true); }
  finally { elements.approveMesh.disabled = false; if (state.project?.stage === "MESH") renderMesh(); }
});

elements.attachReference.addEventListener("click", async () => {
  const path = await window.glyphDesktop.chooseReference();
  if (!path) return;
  state.reference = path;
  elements.referenceChip.textContent = path.split("/").pop();
  elements.referenceChip.classList.remove("hidden");
});

elements.generatePreview.addEventListener("click", async () => {
  if (!state.auth?.signed_in) return signInWithChatGPT();
  const record = activeRecord();
  if (!record) return toast("Select a mesh first", true);
  setBusy(true, "Harness is planning a typed edit…");
  try {
    const result = await api("/api/preview", {
      method: "POST",
      body: JSON.stringify({
        instruction: elements.instruction.value,
        object_name: record.id,
        face_indices: [...state.selectedFaces],
        references: state.reference ? [state.reference] : [],
        backend: "CODEX",
        model: state.settings.model,
        scene: state.scene,
      }),
    });
    state.context = result.context;
    renderHarness(result.steps);
    setScene(result.scene);
    toast("Preview ready — inspect it, then Accept or Reject");
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
});

elements.acceptPreview.addEventListener("click", async () => {
  setBusy(true, "Accepting preview and preserving the source backup…");
  try {
    const result = await api("/api/accept", { method: "POST", body: "{}" });
    setScene(result.scene);
    renderHarness([{ name: "Edit accepted", detail: `Original preserved in ${result.backup}` }]);
    toast("Edit accepted; source mesh preserved as a hidden backup");
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
});

elements.rejectPreview.addEventListener("click", async () => {
  setBusy(true, "Restoring the untouched source…");
  try {
    const result = await api("/api/reject", { method: "POST", body: "{}" });
    setScene(result.scene);
    renderHarness([{ name: "Preview rejected", detail: "Untouched source restored" }]);
    toast("Preview rejected");
  } catch (error) { toast(error.message, true); }
  finally { setBusy(false); }
});

elements.clearSelection.addEventListener("click", () => {
  state.selectedFaces.clear(); updateHighlight(); updateContext();
});
elements.sceneSearch.addEventListener("input", renderSceneTree);
elements.sceneCollapse.addEventListener("click", () => {
  state.sceneCollapsed = !state.sceneCollapsed;
  elements.workspace.classList.toggle("scene-collapsed", state.sceneCollapsed);
  elements.sceneCollapse.textContent = state.sceneCollapsed ? "›" : "‹";
  elements.sceneCollapse.title = state.sceneCollapsed ? "Expand Scene panel" : "Collapse Scene panel";
  setTimeout(resizeViewport, 220);
});

function setViewMode(mode) {
  state.viewMode = mode;
  for (const name of ["mesh", "render", "lit"]) {
    elements[`view${name[0].toUpperCase()}${name.slice(1)}`].classList.toggle("active", name === mode);
  }
  renderMeshes(false);
}

elements.viewMesh.addEventListener("click", () => setViewMode("mesh"));
elements.viewRender.addEventListener("click", () => setViewMode("render"));
elements.viewLit.addEventListener("click", () => setViewMode("lit"));
elements.selectTool.addEventListener("click", () => {
  elements.selectTool.classList.add("active"); elements.moveTool.classList.remove("active");
});
elements.moveTool.addEventListener("click", () => {
  elements.moveTool.classList.add("active"); elements.selectTool.classList.remove("active");
  toast("Move is reserved for direct positioning; mesh context selection remains active");
});

elements.chatgptAuth.addEventListener("click", signInWithChatGPT);
elements.settingsSignIn.addEventListener("click", signInWithChatGPT);
elements.settingsButton.addEventListener("click", () => { renderAuth(); elements.settingsDialog.showModal(); });
elements.saveSettings.addEventListener("click", async (event) => {
  event.preventDefault();
  try {
    state.settings = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        model: elements.modelSetting.value,
        trellis_endpoint: elements.trellisEndpoint.value,
        planner: "CODEX",
      }),
    });
    state.trellisContract = await api("/api/trellis/contract");
    elements.trellisStatus.textContent = state.settings.trellis_endpoint ? "Configured" : "Not configured";
    elements.settingsDialog.close();
    renderWorkflow();
    toast("Settings saved");
  } catch (error) { toast(error.message, true); }
});

elements.sendTrellis.addEventListener("click", async () => {
  if (!state.context) return toast("Generate a selection preview before sending a TRELLIS job", true);
  elements.sendTrellis.disabled = true;
  try {
    const job = await api("/api/trellis/jobs", {
      method: "POST",
      body: JSON.stringify({ instruction: elements.instruction.value, context: state.context, references: state.reference ? [state.reference] : [] }),
    });
    elements.trellisStatus.textContent = job.status || "Queued";
    toast(`TRELLIS job ${job.job_id || "submitted"}`);
  } catch (error) { toast(error.message, true); }
  finally { elements.sendTrellis.disabled = false; }
});

load();

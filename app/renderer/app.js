import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const API = window.glyphDesktop.apiBase;
const API_TOKEN = window.glyphDesktop.apiToken;
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
    "editor-toolbar", "viewport-modes", "fork-project", "source-preview", "source-image",
    "source-placeholder", "import-source", "replace-source", "lock-source", "source-ready-title", "source-ready-copy",
    "lock-dialog", "lock-confirmation", "chatgpt-auth", "chatgpt-auth-label", "settings-auth-card",
    "settings-auth-title", "settings-auth-detail", "settings-sign-in",
    "confirm-lock", "locked-source-image", "locked-source-version", "locked-source-hash", "locked-source-prompt",
    "mesh-source-ghost", "mesh-job-pill", "mesh-progress-title", "mesh-progress-percent", "mesh-progress-bar",
    "mesh-progress-copy", "mesh-state-icon", "conversion-upload", "conversion-validate", "start-meshify",
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
const meshViews = new Map();

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${API_TOKEN}`, ...(options.headers || {}) },
    ...options,
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `Request failed (${response.status})`);
  return value;
}

function initViewport() {
  threeScene = new THREE.Scene();
  threeScene.background = new THREE.Color(0x24282b);
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

  const hemisphere = new THREE.HemisphereLight(0xffffff, 0x232a31, 2.1);
  threeScene.add(hemisphere);
  const key = new THREE.DirectionalLight(0xffffff, 2.5);
  key.position.set(4, 7, 5);
  threeScene.add(key);
  const rim = new THREE.DirectionalLight(0x6da7ff, 1.2);
  rim.position.set(-5, 2, -4);
  threeScene.add(rim);
  const grid = new THREE.GridHelper(30, 30, 0x56606a, 0x343a40);
  grid.material.opacity = 0.35;
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
      material = new THREE.MeshBasicMaterial({ color: 0x78838d, transparent: true, opacity: 0.07, depthWrite: false, side: THREE.DoubleSide });
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
      new THREE.LineBasicMaterial({ color: 0x9ba6b1, transparent: true, opacity: 0.72 })
    );
    topology.visible = state.viewMode === "mesh";
    mesh.add(topology);
    const highlight = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshStandardMaterial({ color: 0xf5a623, emissive: 0x6b3600, roughness: 0.55, side: THREE.DoubleSide })
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
    ? `<div style="text-align:center"><strong style="display:block;color:#f5a623;font-size:26px">${faces || record.face_count}</strong><span>${faces ? "selected faces" : "whole object selected"}</span></div>`
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
  if (source) elements.sourceImage.src = fileUrl(source.path);
  elements.lockSource.disabled = !source;
  elements.replaceSource.classList.toggle("hidden", !source);
  elements.sourceReadyTitle.textContent = source ? "Source image ready" : "No source image loaded";
  elements.sourceReadyCopy.textContent = source ? "Continue when this is the exact image you want TRELLIS to reconstruct." : "Choose a PNG, JPEG, or WebP image to begin.";
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

function normalizedJobStatus(job) {
  return String(job?.status || "ready").toLowerCase();
}

function hasMeshOutput(job) {
  if (!job) return false;
  const keys = new Set(["glb_url", "mesh_url", "output_url", "glb_path", "mesh_path", "glb", "mesh", "replacement_glb", "path", "url"]);
  const scan = (value, depth = 0) => {
    if (!value || depth > 2) return false;
    if (Array.isArray(value)) return value.some((item) => scan(item, depth + 1));
    if (typeof value !== "object") return false;
    return Object.entries(value).some(([key, item]) => (keys.has(key) && typeof item === "string") || scan(item, depth + 1));
  };
  return scan(job);
}

function renderMesh() {
  const locked = state.project.source.locked;
  if (!locked) return;
  const imageUrl = fileUrl(locked.path);
  elements.lockedSourceImage.src = imageUrl;
  elements.meshSourceGhost.src = imageUrl;
  elements.lockedSourceVersion.textContent = locked.id.replace("source-", "Source ");
  elements.lockedSourceHash.textContent = `sha256:${locked.sha256}`;
  elements.lockedSourcePrompt.textContent = locked.prompt || "Imported source";
  const job = state.project.mesh.job;
  const status = normalizedJobStatus(job);
  const rawProgress = Number(job?.progress ?? job?.percent ?? (status === "completed" || status === "succeeded" ? 100 : ["running", "processing", "reconstructing"].includes(status) ? 54 : job ? 12 : 0));
  const progress = Math.max(0, Math.min(100, rawProgress <= 1 && rawProgress > 0 ? rawProgress * 100 : rawProgress));
  const running = ["queued", "running", "processing", "reconstructing", "pending"].includes(status);
  const complete = ["completed", "succeeded", "success"].includes(status);
  const failed = ["failed", "error", "cancelled"].includes(status);
  elements.meshJobPill.textContent = job ? status.replace(/^./, (value) => value.toUpperCase()) : "Ready";
  elements.meshProgressTitle.textContent = complete ? "Mesh generation complete" : failed ? "Conversion failed" : running ? "TRELLIS is reconstructing" : "Ready to meshify";
  elements.meshProgressPercent.textContent = `${Math.round(progress)}%`;
  elements.meshProgressBar.style.width = `${progress}%`;
  elements.meshProgressCopy.textContent = complete ? "Choose the completed GLB to validate it in Blender and unlock Edit." : failed ? "Retrying will use the same locked source." : running ? "You can leave this screen; the job remains attached to this project." : "The source is locked. Start TRELLIS when your endpoint is configured.";
  elements.meshStateIcon.parentElement.classList.toggle("running", running);
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
  try {
    const [project, settings, auth] = await Promise.all([api("/api/project/state"), api("/api/settings"), api("/api/auth/chatgpt")]);
    state.project = project;
    state.settings = settings;
    state.auth = auth;
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
    state.project = await api("/api/source/import", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
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
  const automatic = ["completed", "succeeded", "success"].includes(normalizedJobStatus(job)) && hasMeshOutput(job);
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

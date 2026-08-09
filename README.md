# Glyph

**Select. Describe. Transform.**

Glyph is a standalone desktop application for selection-aware, recoverable 3D edits. It owns the
workflow and interface while Blender 5 runs headlessly as its geometry engine.

Projects move forward through three states:

1. **Source** — load an existing PNG, JPEG, or WebP image.
2. **Meshify** — permanently lock that source and reconstruct it through TRELLIS.
3. **Edit** — approve a Blender-validated GLB, then make local, selection-aware edits.

The source-lock boundary is enforced by the local service and persisted in `project.json`. A locked
source cannot be changed or reselected. Exploring a different direction creates a new project fork
with an explicit parent lineage.

## What the standalone app includes

- a native desktop window with an interactive Three.js mesh viewport;
- a focused source-image import workspace with no image-generation API dependency;
- four bundled transparent source presets plus local image upload;
- an explicit, irreversible source confirmation;
- an asynchronous TRELLIS reconstruction workspace;
- Blender-validated GLB/glTF approval before Edit unlocks;
- a searchable scene and object hierarchy;
- face selection with an explicit **Model Context** inspector;
- an agent-style harness that creates a typed plan, invokes narrow Blender tools, and records each
  step of the run;
- isolated previews with **Accept** and **Reject**; accepted edits retain a hidden source backup;
- ChatGPT sign-in for the Codex-powered Glyph Agent, with no OpenAI API key;
- optional reference images; and
- a configurable remote TRELLIS job endpoint.

The model never receives arbitrary Python or direct Blender access. It returns an `EditPlan` from a
small operation vocabulary. Glyph applies that plan to duplicated geometry and validates the result
before it can replace the working mesh.

## Requirements

- macOS on Apple Silicon;
- Blender 5.0 or newer (`/Applications/Blender.app` by default);
- Node.js and npm; and
- Python 3.11 or newer.

## Run from source

```bash
./scripts/launch_glyph.sh
```

The launcher installs the JavaScript dependencies on the first run and then opens Glyph. Configure
the TRELLIS endpoint in Settings. Glyph resolves Codex from the ChatGPT desktop app or a healthy CLI
installation, and uses its ChatGPT sign-in for agent planning.

To use a Glyph backend on another machine, create `backend.json` in Electron's
`glyph-desktop` application-data directory with `api_base` and `api_token` fields, or set
`GLYPH_API_BASE` and `GLYPH_API_TOKEN`. The Electron main process owns the credential and proxies
requests; the token is never exposed to renderer JavaScript. Remote source images are transferred
with `POST /api/source/upload` rather than filesystem paths that only exist on the desktop machine.

## Package the macOS app

```bash
npm install
npm run package:mac
open dist/Glyph-darwin-arm64/Glyph.app
```

## Harness backends

Glyph Agent invokes the Codex CLI with a strict JSON schema, attached images, and read-only
sandboxing. Codex must report that it is signed in with ChatGPT; API-key authentication is not used
by this flow. Typed plans pass through the same Blender preview and validation boundary.

## TRELLIS endpoint

Set the endpoint in Glyph's settings or launch with `GLYPH_TRELLIS_ENDPOINT`. Glyph submits:

```http
POST {endpoint}/jobs
Content-Type: application/json
```

For initial reconstruction, the versioned request contains the exact locked image bytes, prompt,
SHA-256 provenance hash, and requested GLB and validation outputs. Completed endpoint outputs can be
downloaded and approved directly; a local GLB/glTF can also be chosen manually. Blender must import
and find valid mesh geometry before the project advances to Edit.

The model-server placeholder and renderer response contract live together in
`glyph_harness/trellis_adapter.py`. Update `MODEL_SERVER` with the final create/status paths and
`EXPECTED_RESPONSE` with the server's job id, status, progress, message, and GLB field paths. Glyph
exposes that definition at `GET /api/trellis/contract`; the frontend uses the returned dot paths and
status groups instead of hard-coding one provider's response shape.

## Architecture

```text
Electron UI: Source → Meshify → Edit
            │ authenticated local HTTP
            ▼
 Persistent ProjectStore ─────────────► TRELLIS /jobs
            ▼
    Python AgentHarness ◄────────────── ChatGPT-authenticated Codex
            │ typed EditPlan
            ▼
  Blender 5 headless bridge
            │
            ├─ duplicate selection
            ├─ apply constrained operations
            ├─ validate protected geometry
            └─ accept with backup / reject
```

## Development checks

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup --python tests/blender_smoke_test.py
npm audit
```

The original Blender sidebar add-on remains in `blender_ai_editor/` as the shared edit engine and a
compatibility UI, but the primary Glyph experience is now the standalone app.

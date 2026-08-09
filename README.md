# Glyph

**Select. Describe. Transform.**

An early, usable vertical slice of a Blender interface controlled by:

- the current object/face/vertex selection;
- a natural-language instruction;
- optional reference images.

The add-on turns the instruction into a small typed edit plan, applies that plan only to duplicated
geometry, validates protected vertices, and presents **Accept** or **Reject**. Accepting preserves the
source objects in a hidden `AI_EDIT_BACKUP_*` collection.

## Install

Glyph requires Blender 5.0 or newer and is currently tested against Blender 5.0.1. From a clone of
this repository:

```bash
blender --background --python scripts/install_addon.py
```

Restart an already-running Blender instance after installation. The offline planner has no external
dependencies. Codex and TRELLIS.2 are optional integrations.

As of August 2026, Blender Foundation does not publish an ARM64 Linux archive alongside its Linux
x86-64 build. The included container definition provides the native Ubuntu ARM64 Blender 5.0.1
package used by Glyph's development machine:

```bash
docker build --platform linux/arm64 -f docker/blender-arm64.Dockerfile \
  -t glyph-blender:5.0.1-arm64 .
```

## Use it

Open Blender, press `N` in the 3D viewport, and choose the **Glyph** tab.

1. Select an object or enter Edit Mode and select vertices/faces.
2. Enter an instruction such as `inflate 0.04 and smooth 0.3`.
3. Add any reference images.
4. Choose a planner and click **Generate Preview**.
5. Inspect the result, then Accept or Reject.

`Local commands` is offline and currently understands scale, move, rotate, inflate, smooth, and
basic colors. `Codex (ChatGPT sign-in)` uses the installed Codex CLI, including `--image` inputs and
a strict output schema. `OpenAI API` uses the Responses API and requires `OPENAI_API_KEY` in the
environment that launched Blender.

## TRELLIS.2 boundary

The **TRELLIS.2 Bridge** panel detects `~/code/TRELLIS.2`, probes its isolated PyTorch
runtime for CUDA, and exports versioned jobs under `jobs/`. **Run Last Job on NVIDIA** starts the
worker outside Blender, refuses CPU fallback, generates a GLB from the first reference image, and
writes provenance and validation metadata beside it. The generated GLB is not imported yet; that is
the next safety boundary, where it will arrive as a fitted disposable preview rather than replacing
selected geometry immediately.

## Development checks

```bash
cd /path/to/glyph
python3 -m unittest discover -s tests -p 'test_*.py'
blender --background --factory-startup --python tests/blender_smoke_test.py
```

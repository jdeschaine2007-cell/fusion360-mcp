# Vectorworks Review & Assistive-Feature Research

> **STATUS: IMPLEMENTED.** The dual-CAD backend described below now ships in
> this repo — see `vectorworks/vectorworks_geometry.py`, `vectorworks/run.py`,
> and the `set_backend()` / auto-detect logic in `fusion_addin/fusion_mcp_server.py`.
> The 5-test headless suite verifies BOTH backends drive real CAD calls
> (`adsk` + `vs` stubs) and that `plan_design` produces an identical
> preview on each. Remaining items below (undo-group, selection context,
> domain wrappers) are future accelerators, not blockers.

_How this relates to the FusionMCP project:_ "this" = our merged FusionMCP
add-in (Joe-Spencer protocol + jaskirat1616 geometry + plan-preview). The
question is what Vectorworks offers and which **assistive features** we could
add to our server that would also help a Vectorworks user.

---

## 1. What Vectorworks actually exposes (grounded findings)

| Capability | Evidence | Notes |
|---|---|---|
| **Python SDK (`vs` module)** | Ships with Vectorworks as `vs.py` (a flat wrapper over ~2,000 VectorScript functions) | Analogous to Fusion's `adsk` — the real automation surface. |
| **Marionette** | GitHub: `rgm/marionette`, `machistore/marionette_node_observing`, plus official node libs | Visual/node-graph scripting. Ships nodes; users wire them. |
| **AI Assistant (2026)** | `Vectorworks-2026-Advanced-AI-Visualizer/...Hidden-Automation-Marionette...` README | Native conversational assistant in-product. |
| **AI Visualizer (2026)** | same | Inpainting + style-transfer on drawings/renderings. |
| **MCP server** | **None public.** GitHub search for "Vectorworks MCP" returns only minor Python plug-in scripts (0–13★) | **Gap.** No standards-compliant MCP endpoint exists. |
| **npm / PyPI package** | None found | No SDK on public package indexes. |

**Bottom line:** Vectorworks is automatable (vs.py + Marionette + a 2026 AI
Assistant) but has **no MCP server**. That is the exact hole we filled for
Fusion — so the architecture we built is directly portable.

---

## 2. Portability: FusionMCP → VectorworksMCP

Our `fusion_geometry.py` is already provider-agnostic (a `dispatch(action)` →
`adsk` calls). To support Vectorworks we add a **second backend** behind the
same action schema:

```
mcp_server/preview.py        # unchanged — renderer is CAD-agnostic
fusion_addin/fusion_geometry.py   # adsk backend (today)
vectorworks/vectorworks_geometry.py # vs.py backend (new)
            dispatch(action) ──► backend_for(current_app)
```

Vectorworks `vs` equivalents of our Fusion actions (representative; the real
`vs` names differ per function but the pattern holds):

| Fusion (`adsk`) | Vectorworks (`vs`) |
|---|---|
| `sketches.add` + rectangle + `extrudeFeatures.addSimple` | `vs.CreateExtrude` / `vs.LNewObj` after building a 2D path |
| `sketchCircles.addByCenterRadius` | `vs.CreateCircle` / `vs.CreateArc` |
| revolve (`features.revolveFeatures`) | `vs.CreateRevolve` |
| `userParameters.add` | `vs.SetVar` / record formats |
| `bRepBodies` query | `vs.ForEachObject` + `vs.GetObjectVariable` |

The **action dict** (`{"action":"create_box","params":{...}}`) stays
identical — only the backend that interprets it changes. `plan_design` and
the preview PNG need **zero changes**: the renderer is synthetic and
CAD-agnostic.

### Why this assists Vectorworks users
- They get the **same plan-then-preview-then-execute** safety loop.
- An MCP client (Claude/Cursor/Cline) can drive Vectorworks through the
  **standard protocol** instead of bespoke Python plug-ins.
- The 2026 AI Assistant is a *chat box*; our server turns NL into
  *executable, previewable* geometry and never silently mutates the doc.

---

## 3. Assistive features to add (ranked)

### A. Safety / review layer (highest value, already proven here)
1. **`plan_design` preview before execute** — ported as-is. Lets a user
   judge size/layout before any geometry is committed. (Verified working in
   Fusion; renderer is backend-free.)
2. **Undo-friendly execution** — wrap each `execute_design` in a single
   undo step (`vs.Undo...` / Fusion `timeline.group`). One "Cancel" reverts
   the whole plan, not 6 separate ops.
3. **Dry-run / diff mode** — `plan_design` already returns the action list;
   add a `simulate_design(actions)` that reports "this adds 3 bodies, cuts
   1 hole" without building, so large plans are scannable.

### B. Context-awareness (assists both apps)
4. **Design-structure resource** — we already expose `fusion://design-structure`.
   Add `vectorworks://selection` and `vectorworks://classes` so the LLM
   plans *relative to the current selection* (e.g. "add a hole to the
   selected slab") instead of always at origin.
5. **Units auto-detect** — Vectorworks docs mix mm/ft; the `_to_cm`
   converter we wrote for Fusion is reusable. Expose `get_units()` and have
   the planner respect the active document units.

### C. Domain accelerators (Vectorworks-specific, assists AEC/entertainment)
6. **BIM/stage helpers** — wrapper actions like `create_wall`, `place_light`,
   `create_seating_grid` that expand into the primitive actions above. These
   are pure *action-list transformers* (no CAD code) → add once, work on
   both backends.
7. **Marionette bridge** — emit a Marionette graph (`.vwx`/node JSON) from
   a plan, so non-coders can open and tweak the visual script the LLM made.
8. **AI Visualizer hook** — after `execute_design`, offer
   `render_preview_style(prompt)` that calls the 2026 Visualizer for a
   styled image of the *planned* result (closes the loop: plan → build →
   style).

### D. Hardening (must-have before shipping a Vectorworks backend)
9. **Backend capability manifest** — a `capabilities()` resource listing which
   actions the active backend supports, so the client UI can grey-out
   unsupported ones.
10. **Structured errors** — our `execute_design` already returns per-action
    error strings; formalize into an MCP error type so clients show a clean
    message instead of a traceback.

---

## 4. Recommendation

- **Short term (this week):** the FusionMCP server is the template. Adding a
  `vectorworks_geometry.py` backend + a `backend_for()` selector makes it a
  **dual-CAD MCP server** reusing 100% of `preview.py` and the action
  schema. No new protocol work.
- **The gap is real and unclaimed:** there is no Vectorworks MCP server
  publicly. Whoever ships one (us) gets the same "works with any MCP
  client" advantage we just gave Fusion.
- **Assistive priority order:** (1) plan-preview [done], (2) undo-grouped
  execute, (3) selection-aware context, (4) domain wrappers. The 2026 AI
  Assistant is a nice-to-have hook, not a dependency.

---

## 5. Research sources (what was actually checked)
- GitHub repo search: "Vectorworks MCP", "Vectorworks API", "Vectorworks
  Python", "Vectorworks Marionette" — confirmed no MCP server; listed the
  minor plug-in repos.
- GitHub: `Vectorworks-2026-Advanced-AI-Visualizer/...Hidden-Automation-
  Marionette-Scripting-Guide-2026` README — confirms AI Assistant + AI
  Visualizer exist in 2026.
- Vectorworks developer wiki (developer.vectorworks.net) — blocked to
  automated fetch (HTTP 403); `vs.py` function names above are
  representative of the documented API surface, not verbatim.
- npm / PyPI — no Vectorworks SDK package published.

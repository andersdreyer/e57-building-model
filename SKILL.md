---
name: e57-building-model
description: Analyse E57 point clouds and turn them into usable scan meshes or constraint-based architectural models for SketchUp, visualization, or 3D printing. Use when detail level, noisy angles, dominant building axes, reference plans, or trustworthy dimensions must guide reconstruction. Do not use for slicing an existing finished model.
---

# E57 Building Model

Convert measured point data into a model whose intended use, geometric assumptions, and uncertainty are explicit. Treat a raw scan mesh and a clean architectural reconstruction as different deliverables.

## Start with evidence

1. Keep the source E57 unchanged.
2. Run `scripts/run.sh doctor`, then `scripts/run.sh analyze <file.e57> --output <analysis.json> --markdown <analysis.md>`.
3. Read the report before choosing parameters. If full sampling is unsafe, use its metadata-only result and prepare a CloudCompare subsample as described in [references/workflow.md](references/workflow.md).
4. Ask the user to choose among the recommended detail profiles. Present the recommended profile first and include effective resolution, target triangle count, likely file size, and intended use. Allow a physical custom tolerance in millimetres.
5. Confirm ambiguous units. Never infer survey or legal accuracy from visual alignment alone.

For architectural and hybrid work, do not start full reconstruction after the scan report alone. First create an evidence register and orientation sheet that identify every in-scope object, its state at scan time, authoritative sources, cardinal/facade directions, locked facts, exclusions, and unresolved conflicts. Read [references/evidence-and-gates.md](references/evidence-and-gates.md) and pass its evidence-lock gate before modelling.

## Choose the modelling mode

- **Scan mesh:** Preserve measured irregularity. Use for documentation, visualization, organic geometry, and a reference layer in SketchUp.
- **Architectural reconstruction:** Detect planes and dominant axes, then fit clean walls, floors, roofs, openings, and footprints using explicit constraints. Use for editable SketchUp geometry.
- **Hybrid:** Produce a clean architectural model plus a lightweight scan reference and a deviation report. Prefer this for buildings.

Read [references/workflow.md](references/workflow.md) for execution and validation. Read [references/constraints.md](references/constraints.md) whenever angles, dimensions, property plans, floor plans, elevations, or other asserted facts are involved. Read [references/sketchup.md](references/sketchup.md) for SketchUp output.

## Detail and geometry decisions

- Base detail recommendations on measured point spacing, density variation, scene size, noise, available memory, and target application—not on arbitrary percentages.
- Do not recommend a surface resolution finer than the scan can support. Explain when extra polygons add no evidence.
- For architectural reconstruction, estimate dominant horizontal axes from well-supported vertical planes. Recommend orthogonalization only when the residuals support it.
- Never snap every near-right angle blindly. Separate `hard`, `soft`, and `evidence` constraints, retain residuals, and surface exceptions such as deliberately angled walls or an out-of-plumb structure.
- Before full reconstruction, prefer small representative previews for light, recommended, and detailed profiles when runtime or ambiguity is material.

## Reference plans and user facts

Plans do not automatically outrank the scan. Ask the user what is authoritative, then encode each item with a source and strength. User-declared facts are hard constraints unless they conflict with another hard constraint. Stop and ask for resolution when hard constraints conflict beyond tolerance.

Register a plan to the scan using embedded coordinates or at least two well-separated control points; prefer three or more to expose scale or skew errors. Record the transform and residual. Use locked footprints and boundaries for XY geometry while deriving heights and non-locked detail from the scan when that matches the user's instruction.

Treat a locked footprint as one complete object. Do not reinterpret one local scan plane as a different edge and shift the object. If a scan plane conflicts with a locked footprint, preserve the footprint and report the deviation. Encode topology and negative facts as constraints too: which wall contains an opening, which direction a door faces, what is connected or below another element, and what must be absent.

Absence of points is not proof of absence. Distinguish `observed`, `occluded`, `not_present_at_scan`, `added_after_scan`, `planned_not_built`, and `unknown`. Photographs may establish topology or later state without becoming metric evidence unless they are registered.

## Revision discipline

Validate reconstruction in orthographic plan, each in-scope facade, relevant sections, and terrain profiles before relying on perspective views. Record element counts, dimensions, orientation, clearances, topology, and exclusions as executable acceptance tests where possible. Freeze user-accepted objects or facades between revisions; do not alter them unless the user reopens them or a hard conflict is surfaced.

## Deliverables and storage

Always include:

- the selected profile and tolerances;
- the coordinate/origin transform;
- model files appropriate to the request;
- a human-readable analysis/deviation report;
- a list of locked facts, inferred geometry, and unresolved areas.

For SketchUp, deliver DAE as the portable interchange file and create native SKP through installed SketchUp when requested. Preserve a lightweight PLY reference when colors matter.

Store results in the user-provided project folder. Keep editable sources, analysis, constraints, reports, and output transforms together. Do not overwrite the source E57 or assume any local storage convention.

## Quality boundary

Do not claim that a result is an as-built survey, cadastral determination, or structurally exact model unless a qualified workflow establishes that. A successful result is geometrically coherent, traceable to sources, within stated tolerances, and usable for its declared purpose.

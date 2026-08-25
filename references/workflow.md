# Workflow

## 1. Inspect the machine and input

Run:

```bash
scripts/run.sh doctor
scripts/run.sh analyze INPUT.e57 --output analysis.json --markdown analysis.md
```

The analyzer reads scan headers first and estimates memory before loading points. Its default safety limit prevents an unexpectedly large E57 from being expanded into memory. Increase `--max-read-points` only after checking available RAM.

If Python E57 reading is unsuitable, use the installed CloudCompare application to open the E57, apply any required global shift, crop irrelevant regions, remove obvious outliers, and export a spatially subsampled PLY. Do not overwrite the E57. Record the shift and sampling distance, then analyze the PLY with a project-specific tool or continue the Open3D stage from that PLY.

## 2. Interpret the report

Check units and bounds, scan and point counts, nearest-neighbour spacing, estimated memory, detected planes, dominant-axis residuals, and the proposed detail profiles. If dimensions are implausible, confirm units before modelling.

## 3. Present the decision

Offer Light, Recommended, Detailed, and Custom. State physical resolution, maximum triangles, and intended use. Physical resolution describes the smallest supported surface scale, not guaranteed accuracy.

## 4. Create a scan mesh

```bash
scripts/run.sh mesh INPUT.e57 \
  --analysis analysis.json \
  --profile balanced \
  --output-base /ABSOLUTE/DELIVERY/PATH/model
```

The command writes PLY, OBJ, STL, DAE, and a JSON mesh report. PLY is the evidence/reference format; DAE is the normal SketchUp interchange; STL omits color and is only appropriate for a printable surface.

For a user-selected physical budget, use `--profile custom --resolution-mm VALUE --target-triangles VALUE`. The command rejects a resolution finer than the measured point spacing unless `--allow-unsupported-resolution` is deliberately supplied after review.

Poisson reconstruction requires oriented normals and tends to fill gaps. Inspect low-density areas and crop artifacts. Do not use a watertight result as proof that hidden surfaces were measured.

## 5. Create an architectural or hybrid model

1. Build the evidence register and orientation sheet from [evidence-and-gates.md](evidence-and-gates.md).
2. Load and register all authoritative footprints before assigning local scan planes to objects.
3. Detect and classify supported planar patches as horizontal, vertical, roof, or exceptional.
4. Isolate each candidate object in top view plus a facade or section before identifying its planes.
5. Infer dominant axes from well-supported vertical-plane normals.
6. Fit geometry globally, minimizing robust point-to-plane residuals while satisfying hard constraints and topology.
7. Keep intentionally angled, occluded, time-shifted, or poorly supported regions separate rather than forcing the dominant-axis model.
8. Generate the clean model, lightweight scan reference, signed deviation summary, evidence views, and acceptance measurements.

Use `scripts/run.sh init-constraints --analysis analysis.json --output constraints.json` as the project manifest starter. Populate it according to [constraints.md](constraints.md), then run `scripts/run.sh validate-constraints constraints.json` before reconstruction.

When a plan has control points, fit and record its transform without overwriting the original manifest:

```bash
scripts/run.sh register-plan constraints.json --plan-index 0 --output constraints-registered.json
```

Review the RMS and maximum residual before treating any plan geometry as locked.

The bundled script detects axes and validates constraints; project-specific wall/roof topology still requires reasoning from the actual scan and plan. Never imply that generic meshing created semantic walls or legal boundaries.

Pass the review gates in [evidence-and-gates.md](evidence-and-gates.md) incrementally. Do not hide unresolved footprint, orientation, or topology conflicts by proceeding to detailed windows, vegetation, or presentation renders. Once the user accepts a component, record it in `frozen_elements` and compare it in subsequent revisions.

## 6. Validate

- Verify units and at least one known dimension.
- Verify orientation and stored origin shift.
- Overlay every locked footprint as a complete polygon; check setbacks, clearances, and overlap.
- For each facade, overlay the model on an orthographic scan slice and applicable elevation. Count openings and verify the signed facade coordinate conversion.
- Confirm topological assertions such as opening wall, facing direction, roof fall, stair travel, and below/above relationships.
- Treat `occluded`, `not_present_at_scan`, and `planned_not_built` as different states in the report.
- Compare frozen elements with their accepted baseline.
- Inspect holes, self-intersections, disconnected fragments, and non-manifold edges.
- Compare the clean model with the scan using point-to-surface distances.
- Inspect median, 90th, 95th, and maximum residuals by element.
- Visually review regions that violate the snap tolerance.
- Run `scripts/run.sh validate-model constraints.json measurements.json --output acceptance-report.json` when acceptance tests are present.
- Open/import DAE in SketchUp before claiming SketchUp compatibility.
- Keep the source, analysis, constraints, and reports beside the final files.

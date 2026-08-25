# SketchUp output

## Preferred deliverables

- DAE: portable import with metre units and optional hierarchy.
- SKP: native file created inside the installed SketchUp application.
- PLY: lightweight colored scan reference; use an appropriate point-cloud importer if direct PLY support is unavailable.
- STL/3MF: only for a separately validated printable result.

## Performance

SketchUp usability depends more on face/edge count and grouping than file size alone. Use the analyzer's profiles as starting points, then validate on the installed version.

- Split large sites by building, storey, room, or spatial tile.
- Put scan reference, reconstructed shell, openings, roof, terrain, and uncertainty overlays in separate groups/tags.
- Keep stable object/facade identifiers in group names so acceptance tests and revision comparisons remain traceable.
- Put user-accepted components on clearly named frozen tags/groups; do not rebuild them incidentally during unrelated corrections.
- Soften internal triangulation edges on scan meshes.
- Keep the detailed reference disabled by default when a light work model exists.
- Recenter large global coordinates and store the reversible origin transform in the report.

## Native SKP

The SketchUp Ruby API runs only inside SketchUp. Use `scripts/sketchup_import.rb` by setting its input/output constants or environment variables, then load it through SketchUp's Ruby console. It imports DAE, creates a source tag, stores provenance attributes, and saves SKP.

Open the SKP, use Zoom Extents, verify one known dimension, inspect face orientation, and confirm the saved SketchUp version before delivery.

Also save fixed orthographic scenes for plan, each in-scope facade, and consequential sections. Compare these scenes with the corresponding evidence views. A perspective scene can reveal recognizability problems, but it does not replace signed-axis, element-count, clearance, or topology checks.

# Constraint model

## Source precedence

Every constraint has a `strength`:

- `hard`: user-declared fact; must be satisfied within its tolerance.
- `soft`: preferred design relationship; may move when evidence disagrees.
- `evidence`: measured scan observation with uncertainty.

Do not silently resolve hard-vs-hard conflicts. Report the sources, discrepancy, and affected geometry and ask the user which fact controls.

Apply precedence to the affected attribute rather than the whole object. A hard footprint can control XY while scan evidence controls height, an elevation controls opening layout, and a photograph controls topology or current appearance. Record that distinction explicitly.

## Typical constraints

- `parallel`: two planes or lines share direction.
- `perpendicular`: directions differ by exactly 90 degrees.
- `vertical` or `horizontal`: plane normal is locked to gravity/model Z.
- `coplanar`: separated patches belong to one plane.
- `distance`: wall spacing, width, height, or setback.
- `footprint`: locked XY polygon for a building or garage.
- `boundary`: property boundary or other reference line.
- `control_point`: correspondence between plan and scan coordinates.
- `preserve_angle`: deliberately non-orthogonal geometry.
- `topology`: an element belongs to, faces, supports, connects to, covers, or passes below another element.
- `count`: required number of openings, columns, steps, rooms, or similar elements.
- `absence`: an element must not exist in the model.
- `temporal_state`: observed at scan time, occluded, added later, removed, historical, or planned but not built.
- `clearance`: minimum or exact separation between complete objects.
- `freeze`: accepted geometry must remain unchanged across revisions.

An empty scan region is not an `absence` constraint. It is `occluded` or `unknown` unless another source establishes absence.

## Plan registration

Prefer vector PDF/DXF/DWG or coordinate-bearing data. A raster plan needs a known scale and control points. Record the source and page/layer, units and scale, control points in both spaces, transform type, registration residuals, and authoritative geometry.

Use a rigid transform when both sources already share scale. Use a similarity transform when a raster plan needs uniform scale. Avoid affine warping unless the source is known to be distorted; it can make inconsistent facts appear to agree.

## Orthogonalization

Estimate dominant axes from supported vertical planes, weighted by inlier count or area. Compare each candidate wall with the nearest dominant axis and retain the angular residual.

Recommend a right-angle lock only when several independent planes support the axes, residuals are small, registration is coherent, and no fact marks a wall as angled. After snapping directions, refit plane offsets globally to the scan so the clean model does not drift away from measured walls.

## Manifest shape

`init-constraints` creates a JSON manifest containing source priority, units and coordinate frame, reference plans, facts, regularization, exceptions, and unresolved conflicts. Keep coordinates numeric and source paths absolute. Put explanatory claims in `note`; do not encode facts only in filenames.

Each reference plan can contain `transform` (`rigid`, `similarity`, or `affine`), `tolerance_m`, and `control_points`. A control point contains `plan_xy` plus `scan_xy` or `scan_xyz`. Run `register-plan` to calculate the matrix and residuals. Prefer rigid/similarity registration; affine fitting can conceal source distortion and must be justified.

For architectural or hybrid reconstruction, also populate:

- `objects`: stable identifiers, scope class, scan-time state, and authoritative attributes;
- `evidence_register`: observations tied to an object and source;
- `facts.topologies`, `facts.counts`, `facts.exclusions`, and `facts.temporal_states` where applicable;
- `acceptance_tests`: executable expectations using stable measurement keys;
- `frozen_elements`: user-accepted objects/facades and their baseline revision or checksum;
- `review_gates`: gate status and evidence artifact paths.

Use `acceptance_tests` entries with:

- `id`: unique stable identifier;
- `metric`: key expected in the model measurements JSON;
- `operator`: `equals`, `within`, `minimum`, `maximum`, `range`, `present`, or `absent`;
- `expected`: scalar, string, boolean, list, or range as appropriate;
- `tolerance`: optional non-negative numeric tolerance for `equals`/`within`;
- `source`: fact provenance.

The validator checks manifest structure. `validate-model` compares these tests with a project-generated measurements JSON. Geometry-specific measurement extraction remains the responsibility of the project builder because semantic meshes differ between projects.

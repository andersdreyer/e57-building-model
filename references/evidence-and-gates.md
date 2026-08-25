# Evidence lock and review gates

Use this workflow for architectural reconstruction and hybrid models. Scale it down for a simple isolated object, but do not skip the evidence lock when multiple sources or structures must agree.

## Evidence register

Create one row per object or consequential feature. Record:

- stable object identifier and scope class (`building`, `secondary_building`, `terrain`, `hardscape`, `vegetation`, or `opening`);
- state relative to the scan: `observed`, `occluded`, `not_present_at_scan`, `added_after_scan`, `planned_not_built`, `historical`, or `unknown`;
- source, date/page/view where known, and whether it supplies metric geometry, topology, appearance, or existence only;
- constraint strength, tolerance or uncertainty, and conflicts;
- explicit exclusions and user-accepted/frozen status.

Plans, elevations, scans, and photographs can control different attributes of the same object. Apply precedence per attribute, not as one global source ranking. For example, a locked plan may control XY footprint while the scan controls height and a photograph controls which wall contains a door.

## Orientation sheet

Before reconstructing, produce a compact plan view that labels:

- model X/Y/Z and scan X/Y/Z;
- north, south, road, and garden or equivalent local directions;
- the signed coordinate conversion used by each facade projection;
- plan control points, transform type, residual, and one known dimension;
- every locked footprint and boundary.

Test one asymmetric feature in plan and facade coordinates. A plausible symmetric building is not enough to prove that road/garden or left/right has not been reversed.

## Object isolation

Do not assign a detected plane to an object merely because it lies near the expected location. Inspect the complete candidate object in top view, at least one facade or section, and its relationship to locked footprints. Distinguish building planes from boundary walls, terraces, paving, vegetation, and occluders. A local plane may constrain an offset only after the object identity is established.

## Review gates

For a substantial property model, use these gates. Each gate needs an observable pass result and unresolved items must remain visible in the manifest.

1. **Coordinate gate:** units, origin, axes, cardinal directions, and reversible transforms verified.
2. **Footprint gate:** parcel and all authoritative building footprints overlaid with the scan; setbacks and clearances checked.
3. **Massing and terrain gate:** primary volumes, roof directions, ground classification, and at least one terrain profile checked. Report the road-to-garden or equivalent level difference.
4. **Facade gate:** each facade reviewed separately against an orthographic scan slice and elevation/photo evidence. Count openings and verify signed placement, sill/head levels, subdivisions, and projections.
5. **Secondary-object gate:** entrances, stairs, garages, terraces, walls, and other topologically consequential objects checked in plan and section.
6. **Landscape gate:** in-scope vegetation and later/absent-at-scan features represented with explicit source and uncertainty.
7. **Delivery gate:** acceptance tests pass, frozen geometry is unchanged, deviation views are reviewed, and the interchange file opens in the target application.

Perspective renders are presentation views, not gate evidence. Use orthographic plan/facade/section overlays and measurement tables for approval.

## Revision freeze

When the user accepts an object, facade, or site component, add it to `frozen_elements` with the accepted revision and a measurable baseline such as a geometry checksum, element list, or critical dimensions. Later revisions must compare against that baseline. If a correction requires changing frozen geometry, surface the reason before changing it.

## Acceptance measurements

Prefer tests that express meaning, not merely mesh integrity:

- dimension or clearance within tolerance;
- element count;
- opening belongs to a named wall or facade;
- door/port faces a named direction;
- roof falls from one named side toward another;
- two footprints do not overlap;
- prohibited element is absent;
- accepted element is unchanged.

Project builders should write a small measurements JSON keyed by stable metric names. Run `scripts/run.sh validate-model CONSTRAINTS.json MEASUREMENTS.json --output REPORT.json` before delivery.

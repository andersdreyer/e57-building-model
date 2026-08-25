#!/usr/bin/env python3
"""Inspect E57 scans, recommend detail/axis constraints, and make reference meshes."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
DEFAULT_MAX_READ_POINTS = 30_000_000
DEFAULT_SAMPLE_POINTS = 250_000


def imports():
    try:
        import numpy as np
        import open3d as o3d
        import psutil
        import pye57
        from scipy.spatial import cKDTree
    except ImportError as exc:
        raise SystemExit(
            f"Missing runtime dependency {exc.name!r}. Run scripts/setup_runtime.sh first."
        ) from exc
    return np, o3d, psutil, pye57, cKDTree


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_dump(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def scan_count(reader: Any) -> int:
    count = getattr(reader, "scan_count", None)
    count = count() if callable(count) else count
    if count is None:
        raise RuntimeError("The E57 reader did not expose scan_count")
    return int(count)


def point_count(header: Any) -> int:
    for name in ("point_count", "pointCount"):
        value = getattr(header, name, None)
        if value is not None:
            return int(value)
    raise RuntimeError("The E57 scan header did not expose a point count")


def read_scan(reader: Any, index: int, colors: bool = True) -> dict[str, Any]:
    attempts = [
        {"intensity": True, "colors": colors, "transform": True, "ignore_missing_fields": True},
        {"intensity": True, "colors": colors, "transform": True},
        {},
    ]
    last_error: Exception | None = None
    for kwargs in attempts:
        try:
            return reader.read_scan(index, **kwargs)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not read E57 scan {index}: {last_error}")


def rgb_from_scan(data: dict[str, Any], indices: Any, np: Any) -> Any | None:
    keys = ("colorRed", "colorGreen", "colorBlue")
    if not all(key in data for key in keys):
        return None
    rgb = np.column_stack([data[key] for key in keys]).astype(np.float64, copy=False)
    if not len(rgb):
        return None
    rgb = rgb[indices]
    maximum = float(np.nanmax(rgb)) if rgb.size else 1.0
    scale = 65535.0 if maximum > 255.0 else 255.0 if maximum > 1.0 else 1.0
    return np.clip(rgb / scale, 0.0, 1.0)


@dataclass
class LoadedSample:
    points: Any
    colors: Any | None
    scan_counts: list[int]
    color_scans: int


def load_sample(path: Path, sample_points: int, max_read_points: int) -> LoadedSample:
    np, _o3d, _psutil, pye57, _cKDTree = imports()
    reader = pye57.E57(str(path))
    count = scan_count(reader)
    counts = [point_count(reader.get_header(i)) for i in range(count)]
    total = sum(counts)
    if total > max_read_points:
        raise MemoryError(
            f"E57 contains {total:,} points, above the safety limit of {max_read_points:,}. "
            "Use CloudCompare to make a spatially subsampled PLY or raise --max-read-points after checking RAM."
        )

    allocations = [max(1, round(sample_points * n / max(total, 1))) for n in counts]
    point_parts: list[Any] = []
    color_parts: list[Any] = []
    all_parts_have_color = True
    color_scans = 0
    for index, target in enumerate(allocations):
        data = read_scan(reader, index)
        raw_len = len(data.get("cartesianX", []))
        if not raw_len:
            continue
        chosen = np.linspace(0, raw_len - 1, min(target, raw_len), dtype=np.int64)
        xyz = np.column_stack(
            [data["cartesianX"], data["cartesianY"], data["cartesianZ"]]
        ).astype(np.float64, copy=False)[chosen]
        valid = np.isfinite(xyz).all(axis=1)
        xyz = xyz[valid]
        chosen = chosen[valid]
        point_parts.append(xyz)
        rgb = rgb_from_scan(data, chosen, np)
        if rgb is None:
            all_parts_have_color = False
        else:
            color_parts.append(rgb)
            color_scans += 1

    if not point_parts:
        raise RuntimeError("No finite Cartesian points could be sampled from the E57")
    points = np.concatenate(point_parts, axis=0)
    colors = np.concatenate(color_parts, axis=0) if all_parts_have_color and color_parts else None
    return LoadedSample(points, colors, counts, color_scans)


def spacing(points: Any, cKDTree: Any, np: Any) -> dict[str, float]:
    if len(points) < 3:
        return {"median_m": 0.0, "p10_m": 0.0, "p90_m": 0.0}
    limit = min(len(points), 50_000)
    chosen = points[np.linspace(0, len(points) - 1, limit, dtype=np.int64)]
    distances, _indices = cKDTree(chosen).query(chosen, k=2, workers=-1)
    nearest = distances[:, 1]
    nearest = nearest[np.isfinite(nearest) & (nearest > 0)]
    if not len(nearest):
        return {"median_m": 0.0, "p10_m": 0.0, "p90_m": 0.0}
    return {
        "median_m": float(np.median(nearest)),
        "p10_m": float(np.quantile(nearest, 0.10)),
        "p90_m": float(np.quantile(nearest, 0.90)),
    }


def detect_planes(points: Any, spacing_m: float, np: Any, o3d: Any) -> list[dict[str, Any]]:
    if len(points) < 1_000:
        return []
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    diagonal = float(np.linalg.norm(np.ptp(points, axis=0)))
    voxel = max(spacing_m * 1.5, diagonal / 4000.0, 0.002)
    remaining = cloud.voxel_down_sample(voxel)
    original_n = max(len(remaining.points), 1)
    threshold = max(voxel * 1.5, spacing_m * 2.0, 0.004)
    planes: list[dict[str, Any]] = []

    for plane_index in range(12):
        if len(remaining.points) < max(500, original_n * 0.01):
            break
        model, inliers = remaining.segment_plane(
            distance_threshold=threshold,
            ransac_n=3,
            num_iterations=800,
            probability=0.999,
        )
        if len(inliers) < max(250, original_n * 0.005):
            break
        normal = np.asarray(model[:3], dtype=float)
        norm = max(float(np.linalg.norm(normal)), 1e-12)
        normal /= norm
        abs_z = abs(float(normal[2]))
        if abs_z >= math.cos(math.radians(15)):
            classification = "horizontal"
        elif abs_z <= math.sin(math.radians(15)):
            classification = "vertical"
        else:
            classification = "sloped"
        azimuth = math.degrees(math.atan2(float(normal[1]), float(normal[0]))) % 180.0
        planes.append(
            {
                "index": plane_index,
                "normal": [float(v) for v in normal],
                "offset": float(model[3]) / norm,
                "classification": classification,
                "normal_azimuth_deg": azimuth,
                "inlier_points": len(inliers),
                "support_fraction": len(inliers) / original_n,
                "distance_threshold_m": threshold,
            }
        )
        remaining = remaining.select_by_index(inliers, invert=True)
    return planes


def axis_recommendation(planes: list[dict[str, Any]], np: Any) -> dict[str, Any]:
    vertical = [p for p in planes if p["classification"] == "vertical"]
    if len(vertical) < 2:
        return {
            "status": "insufficient_evidence",
            "reason": "Fewer than two supported vertical planes were detected.",
        }
    angles = np.radians([p["normal_azimuth_deg"] for p in vertical])
    weights = np.asarray([p["inlier_points"] for p in vertical], dtype=float)
    theta = math.atan2(
        float(np.sum(weights * np.sin(4 * angles))),
        float(np.sum(weights * np.cos(4 * angles))),
    ) / 4.0
    theta_deg = math.degrees(theta) % 90.0

    def residual(angle: float) -> float:
        return abs((angle - theta_deg + 45.0) % 90.0 - 45.0)

    residuals = np.asarray([residual(float(p["normal_azimuth_deg"])) for p in vertical])
    order = np.argsort(residuals)
    cumulative = np.cumsum(weights[order])
    weighted_median = float(residuals[order[np.searchsorted(cumulative, cumulative[-1] * 0.5)]])
    p90 = float(np.quantile(residuals, 0.9))
    suggested_tolerance = round(min(3.0, max(0.5, p90 * 1.25)), 1)
    recommend_lock = len(vertical) >= 3 and p90 <= 2.0
    return {
        "status": "supported",
        "primary_axis_deg": theta_deg,
        "orthogonal_axis_deg": (theta_deg + 90.0) % 180.0,
        "vertical_plane_count": len(vertical),
        "weighted_median_residual_deg": weighted_median,
        "p90_residual_deg": p90,
        "suggested_snap_tolerance_deg": suggested_tolerance,
        "recommend_orthogonal_lock": recommend_lock,
        "decision": "offer_90_degree_lock" if recommend_lock else "review_before_locking",
    }


def profiles(spacing_m: float, diagonal_m: float, total_points: int, total_ram: int) -> dict[str, Any]:
    evidence_floor = max(spacing_m, diagonal_m / 10_000.0, 0.001)
    ram_gb = total_ram / (1024**3)
    scale = 0.65 if ram_gb < 8 else 1.0 if ram_gb < 24 else 1.5
    counts = {"light": int(150_000 * scale), "balanced": int(500_000 * scale), "detailed": int(1_500_000 * scale)}
    items = {
        "light": {
            "effective_resolution_mm": round(evidence_floor * 4_000, 1),
            "target_triangles": counts["light"],
            "use": "context and fast SketchUp navigation",
        },
        "balanced": {
            "effective_resolution_mm": round(evidence_floor * 2_000, 1),
            "target_triangles": counts["balanced"],
            "use": "recommended editable/reference balance",
        },
        "detailed": {
            "effective_resolution_mm": round(evidence_floor * 1_000, 1),
            "target_triangles": counts["detailed"],
            "use": "inspection reference; may be heavy in SketchUp",
        },
    }
    recommended = "light" if diagonal_m > 250 or total_points > 200_000_000 or ram_gb < 8 else "balanced"
    return {"recommended": recommended, "profiles": items}


def write_markdown(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# E57 analysis",
        "",
        f"- Source: `{report.get('source', '')}`",
        f"- Status: **{report.get('analysis_status', 'unknown')}**",
        f"- Scans: {report.get('scan_count', 0)}",
        f"- Points: {report.get('total_points', 0):,}",
    ]
    if report.get("analysis_status") == "complete":
        dims = report["dimensions_m"]
        lines.extend(
            [
                f"- Sample bounds: {dims[0]:.3f} × {dims[1]:.3f} × {dims[2]:.3f} m",
                f"- Estimated representative spacing: {report['spacing']['median_m'] * 1000:.1f} mm",
                f"- Detected planes: {len(report.get('planes', []))}",
                "",
                "## Detail recommendation",
                "",
                f"Recommended: **{report['detail_recommendation']['recommended']}**",
                "",
            ]
        )
        for name, profile in report["detail_recommendation"]["profiles"].items():
            lines.append(
                f"- **{name}:** {profile['effective_resolution_mm']:.1f} mm, "
                f"{profile['target_triangles']:,} target triangles — {profile['use']}"
            )
        axes = report.get("dominant_axes", {})
        lines.extend(["", "## Dominant axes", ""])
        if axes.get("status") == "supported":
            lines.extend(
                [
                    f"- Primary axis: {axes['primary_axis_deg']:.2f}°",
                    f"- P90 angular residual: {axes['p90_residual_deg']:.2f}°",
                    f"- Suggested snap tolerance: {axes['suggested_snap_tolerance_deg']:.1f}°",
                    f"- Recommend 90° lock: {'yes' if axes['recommend_orthogonal_lock'] else 'review first'}",
                ]
            )
        else:
            lines.append(f"- {axes.get('reason', 'Insufficient evidence')}")
    else:
        lines.extend(["", "## Blocking reason", "", report.get("blocking_reason", "Unknown")])
    lines.extend(["", "## Required confirmation", "", "Confirm units, intended use, detail profile, and binding external facts.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def analyze(args: argparse.Namespace) -> int:
    np, o3d, psutil, pye57, cKDTree = imports()
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Input does not exist: {source}")
    reader = pye57.E57(str(source))
    count = scan_count(reader)
    counts = [point_count(reader.get_header(i)) for i in range(count)]
    total = sum(counts)
    memory = psutil.virtual_memory()
    available_ram = int(memory.available)
    total_ram = int(memory.total)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source": str(source),
        "source_size_bytes": source.stat().st_size,
        "scan_count": count,
        "scan_point_counts": counts,
        "total_points": total,
        "estimated_expanded_bytes": total * 32,
        "available_ram_bytes": available_ram,
        "total_ram_bytes": total_ram,
        "units": {"assumed": "metres", "status": "confirm_from_known_dimension"},
    }
    try:
        sample = load_sample(source, args.sample_points, args.max_read_points)
    except MemoryError as exc:
        report.update(
            {
                "analysis_status": "metadata_only",
                "blocking_reason": str(exc),
                "recommendation": "Create a spatially subsampled PLY in CloudCompare, preserving the global-shift record.",
            }
        )
        json_dump(report, Path(args.output).expanduser().resolve())
        if args.markdown:
            write_markdown(report, Path(args.markdown).expanduser().resolve())
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2

    points = sample.points
    bounds_min = points.min(axis=0)
    bounds_max = points.max(axis=0)
    dimensions = bounds_max - bounds_min
    diagonal = float(np.linalg.norm(dimensions))
    spacing_data = spacing(points, cKDTree, np)
    planes = detect_planes(points, spacing_data["median_m"], np, o3d)
    report.update(
        {
            "analysis_status": "complete",
            "sampled_points": len(points),
            "bounds_m": {"min": bounds_min.tolist(), "max": bounds_max.tolist()},
            "dimensions_m": dimensions.tolist(),
            "diagonal_m": diagonal,
            "spacing": spacing_data,
            "color": {"available": sample.colors is not None, "scans_with_color": sample.color_scans},
            "planes": planes,
            "dominant_axes": axis_recommendation(planes, np),
            "detail_recommendation": profiles(spacing_data["median_m"], diagonal, total, total_ram),
            "warnings": [
                "Nearest-neighbour spacing is estimated from a distributed sample.",
                "Detected planes and dominant axes are proposals, not facts.",
                "Confirm units using a known dimension before reconstruction.",
            ],
        }
    )
    json_dump(report, Path(args.output).expanduser().resolve())
    if args.markdown:
        write_markdown(report, Path(args.markdown).expanduser().resolve())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def profile_from_analysis(analysis: dict[str, Any], name: str) -> dict[str, Any]:
    profiles_data = analysis.get("detail_recommendation", {}).get("profiles", {})
    if name == "recommended":
        name = analysis.get("detail_recommendation", {}).get("recommended", "balanced")
    if name not in profiles_data:
        raise SystemExit(f"Profile {name!r} is unavailable in the analysis")
    return profiles_data[name] | {"name": name}


def profile_from_args(analysis: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.profile != "custom":
        return profile_from_analysis(analysis, args.profile)
    if args.resolution_mm is None or args.target_triangles is None:
        raise SystemExit("Custom profile requires both --resolution-mm and --target-triangles")
    if args.resolution_mm <= 0 or args.target_triangles <= 0:
        raise SystemExit("Custom resolution and triangle count must be positive")
    evidence_mm = analysis.get("spacing", {}).get("median_m", 0.0) * 1000.0
    if evidence_mm and args.resolution_mm < evidence_mm and not args.allow_unsupported_resolution:
        raise SystemExit(
            f"Custom resolution {args.resolution_mm:g} mm is finer than the estimated "
            f"scan spacing {evidence_mm:.1f} mm. Review this and pass --allow-unsupported-resolution to override."
        )
    return {
        "name": "custom",
        "effective_resolution_mm": float(args.resolution_mm),
        "target_triangles": int(args.target_triangles),
        "use": "user-selected physical resolution and polygon budget",
    }


def load_mesh_points(source: Path, max_points: int) -> tuple[Any, Any | None]:
    np, _o3d, _psutil, pye57, _cKDTree = imports()
    reader = pye57.E57(str(source))
    count = scan_count(reader)
    counts = [point_count(reader.get_header(i)) for i in range(count)]
    total = sum(counts)
    allocations = [max(1, round(max_points * n / max(total, 1))) for n in counts]
    point_parts: list[Any] = []
    color_parts: list[Any] = []
    all_color = True
    for index, allocation in enumerate(allocations):
        data = read_scan(reader, index)
        raw_len = len(data.get("cartesianX", []))
        if not raw_len:
            continue
        indices = np.linspace(0, raw_len - 1, min(allocation, raw_len), dtype=np.int64)
        xyz = np.column_stack([data["cartesianX"], data["cartesianY"], data["cartesianZ"]]).astype(np.float64, copy=False)[indices]
        valid = np.isfinite(xyz).all(axis=1)
        xyz = xyz[valid]
        indices = indices[valid]
        point_parts.append(xyz)
        rgb = rgb_from_scan(data, indices, np)
        if rgb is None:
            all_color = False
        else:
            color_parts.append(rgb)
    if not point_parts:
        raise RuntimeError("No finite Cartesian points could be loaded")
    return np.concatenate(point_parts), np.concatenate(color_parts) if all_color and color_parts else None


def write_dae(mesh: Any, path: Path, origin_offset: Iterable[float]) -> None:
    import xml.etree.ElementTree as ET

    np, _o3d, _psutil, _pye57, _cKDTree = imports()
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles, dtype=np.int64)
    ns = "http://www.collada.org/2005/11/COLLADASchema"
    ET.register_namespace("", ns)
    root = ET.Element(f"{{{ns}}}COLLADA", {"version": "1.4.1"})
    asset = ET.SubElement(root, f"{{{ns}}}asset")
    contributor = ET.SubElement(asset, f"{{{ns}}}contributor")
    ET.SubElement(contributor, f"{{{ns}}}authoring_tool").text = "Codex e57-building-model"
    ET.SubElement(asset, f"{{{ns}}}created").text = utc_now()
    ET.SubElement(asset, f"{{{ns}}}unit", {"name": "meter", "meter": "1"})
    ET.SubElement(asset, f"{{{ns}}}up_axis").text = "Z_UP"
    geometries = ET.SubElement(root, f"{{{ns}}}library_geometries")
    geometry = ET.SubElement(geometries, f"{{{ns}}}geometry", {"id": "e57-mesh", "name": "E57 mesh"})
    xml_mesh = ET.SubElement(geometry, f"{{{ns}}}mesh")
    source = ET.SubElement(xml_mesh, f"{{{ns}}}source", {"id": "e57-positions"})
    floats = ET.SubElement(source, f"{{{ns}}}float_array", {"id": "e57-positions-array", "count": str(vertices.size)})
    floats.text = " ".join(f"{value:.9g}" for value in vertices.ravel())
    technique = ET.SubElement(source, f"{{{ns}}}technique_common")
    accessor = ET.SubElement(technique, f"{{{ns}}}accessor", {"source": "#e57-positions-array", "count": str(len(vertices)), "stride": "3"})
    for axis in "XYZ":
        ET.SubElement(accessor, f"{{{ns}}}param", {"name": axis, "type": "float"})
    verts = ET.SubElement(xml_mesh, f"{{{ns}}}vertices", {"id": "e57-vertices"})
    ET.SubElement(verts, f"{{{ns}}}input", {"semantic": "POSITION", "source": "#e57-positions"})
    tris = ET.SubElement(xml_mesh, f"{{{ns}}}triangles", {"count": str(len(triangles))})
    ET.SubElement(tris, f"{{{ns}}}input", {"semantic": "VERTEX", "source": "#e57-vertices", "offset": "0"})
    ET.SubElement(tris, f"{{{ns}}}p").text = " ".join(str(int(value)) for value in triangles.ravel())
    scenes = ET.SubElement(root, f"{{{ns}}}library_visual_scenes")
    scene = ET.SubElement(scenes, f"{{{ns}}}visual_scene", {"id": "Scene", "name": "Scene"})
    node = ET.SubElement(scene, f"{{{ns}}}node", {"id": "E57Model", "name": "E57 reconstructed model", "type": "NODE"})
    ET.SubElement(node, f"{{{ns}}}instance_geometry", {"url": "#e57-mesh"})
    scene_root = ET.SubElement(root, f"{{{ns}}}scene")
    ET.SubElement(scene_root, f"{{{ns}}}instance_visual_scene", {"url": "#Scene"})
    root.append(ET.Comment(f" reversible_origin_offset_m={list(origin_offset)} "))
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def mesh_command(args: argparse.Namespace) -> int:
    np, o3d, _psutil, _pye57, _cKDTree = imports()
    source = Path(args.input).expanduser().resolve()
    analysis_path = Path(args.analysis).expanduser().resolve()
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    profile = profile_from_args(analysis, args)
    points, colors = load_mesh_points(source, args.max_points)
    origin_offset = np.zeros(3)
    if args.recenter == "centroid" or (args.recenter == "auto" and float(np.max(np.abs(points))) > 10_000):
        origin_offset = np.median(points, axis=0)
        points = points - origin_offset

    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    if colors is not None and len(colors) == len(points):
        cloud.colors = o3d.utility.Vector3dVector(colors)
    voxel = max(profile["effective_resolution_mm"] / 2000.0, 0.001)
    cloud = cloud.voxel_down_sample(voxel)
    cloud, _indices = cloud.remove_statistical_outlier(nb_neighbors=24, std_ratio=2.5)
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 4, max_nn=60))
    cloud.orient_normals_consistent_tangent_plane(min(50, max(10, len(cloud.points) // 10_000)))
    reconstructed, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        cloud, depth=args.poisson_depth, scale=1.05
    )
    density_array = np.asarray(densities)
    if args.trim_quantile > 0 and len(density_array):
        cutoff = float(np.quantile(density_array, args.trim_quantile))
        reconstructed.remove_vertices_by_mask(density_array < cutoff)
    reconstructed = reconstructed.crop(cloud.get_axis_aligned_bounding_box())
    reconstructed.remove_degenerate_triangles()
    reconstructed.remove_duplicated_triangles()
    reconstructed.remove_duplicated_vertices()
    reconstructed.remove_non_manifold_edges()
    target = min(int(profile["target_triangles"]), len(reconstructed.triangles))
    if target > 0 and len(reconstructed.triangles) > target:
        reconstructed = reconstructed.simplify_quadric_decimation(target)
    reconstructed.compute_vertex_normals()

    base = Path(args.output_base).expanduser().resolve()
    base.parent.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    for extension in ("ply", "obj", "stl"):
        destination = base.with_suffix(f".{extension}")
        if not o3d.io.write_triangle_mesh(str(destination), reconstructed, write_ascii=False):
            raise RuntimeError(f"Could not write {destination}")
        outputs[extension] = str(destination)
    dae = base.with_suffix(".dae")
    write_dae(reconstructed, dae, origin_offset)
    outputs["dae"] = str(dae)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source": str(source),
        "analysis": str(analysis_path),
        "profile": profile,
        "sampled_input_points": len(points),
        "mesh_vertices": len(reconstructed.vertices),
        "mesh_triangles": len(reconstructed.triangles),
        "origin_offset_m": origin_offset.tolist(),
        "voxel_m": voxel,
        "method": "poisson",
        "poisson_depth": args.poisson_depth,
        "outputs": outputs,
        "warnings": [
            "Poisson reconstruction can fill unmeasured gaps.",
            "STL and DAE do not preserve point-cloud provenance or legal accuracy.",
            "Visually inspect and verify a known dimension before use.",
        ],
    }
    json_dump(report, base.with_name(base.name + "_mesh-report.json"))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def init_constraints(args: argparse.Namespace) -> int:
    analysis_path = Path(args.analysis).expanduser().resolve()
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    axes = analysis.get("dominant_axes", {})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "analysis": str(analysis_path),
        "units": "metres",
        "coordinate_frame": {
            "z_axis": "up",
            "origin_offset_m": [0.0, 0.0, 0.0],
            "plan_x_direction": "confirm",
            "plan_y_direction": "confirm",
            "cardinal_north_deg": None,
            "status": "confirm",
        },
        "source_priority": ["user_locked_fact", "reference_plan", "architectural_regularization", "scan_evidence", "inference"],
        "reference_plans": [],
        "objects": [],
        "evidence_register": [],
        "facts": {
            "control_points": [],
            "footprints": [],
            "boundaries": [],
            "dimensions": [],
            "angles": [],
            "topologies": [],
            "counts": [],
            "exclusions": [],
            "temporal_states": [],
            "clearances": [],
        },
        "regularization": {
            "orthogonalization": {
                "mode": "recommend",
                "primary_axis_deg": axes.get("primary_axis_deg"),
                "snap_tolerance_deg": axes.get("suggested_snap_tolerance_deg"),
                "evidence_p90_residual_deg": axes.get("p90_residual_deg"),
            },
            "vertical_tolerance_deg": 2.0,
            "horizontal_tolerance_deg": 2.0,
        },
        "exceptions": [],
        "unresolved_conflicts": [],
        "acceptance_tests": [],
        "frozen_elements": [],
        "review_gates": [
            {"id": "coordinate", "status": "pending", "evidence": []},
            {"id": "footprint", "status": "pending", "evidence": []},
            {"id": "massing_terrain", "status": "pending", "evidence": []},
            {"id": "facades", "status": "pending", "evidence": []},
            {"id": "secondary_objects", "status": "pending", "evidence": []},
            {"id": "landscape", "status": "pending", "evidence": []},
            {"id": "delivery", "status": "pending", "evidence": []},
        ],
    }
    output = Path(args.output).expanduser().resolve()
    json_dump(manifest, output)
    print(output)
    return 0


def validate_constraints(args: argparse.Namespace) -> int:
    path = Path(args.input).expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if data.get("units") not in {"metres", "millimetres"}:
        errors.append("units must be 'metres' or 'millimetres'")
    if data.get("coordinate_frame", {}).get("status") != "confirmed":
        warnings.append("coordinate_frame.status is not 'confirmed'")
    for plan_index, plan in enumerate(data.get("reference_plans", [])):
        source = plan.get("source")
        if not source or not Path(source).expanduser().is_absolute():
            errors.append(f"reference_plans[{plan_index}].source must be an absolute path")
        transform = plan.get("transform", "similarity")
        minimum = 2 if transform in {"rigid", "similarity"} else 3
        if len(plan.get("control_points", [])) < minimum:
            warnings.append(f"reference_plans[{plan_index}] has fewer than {minimum} control points")
    for category, facts in data.get("facts", {}).items():
        for fact_index, fact in enumerate(facts):
            if fact.get("strength") not in {"hard", "soft", "evidence"}:
                errors.append(f"facts.{category}[{fact_index}].strength is invalid")
            if not fact.get("source"):
                errors.append(f"facts.{category}[{fact_index}] needs a source")
    object_ids: set[str] = set()
    object_states = {
        "observed", "occluded", "not_present_at_scan", "added_after_scan",
        "removed_before_scan", "planned_not_built", "historical", "unknown",
    }
    for object_index, item in enumerate(data.get("objects", [])):
        object_id = item.get("id")
        if not object_id:
            errors.append(f"objects[{object_index}] needs an id")
        elif object_id in object_ids:
            errors.append(f"objects[{object_index}].id {object_id!r} is duplicated")
        else:
            object_ids.add(object_id)
        if item.get("state") not in object_states:
            errors.append(f"objects[{object_index}].state is invalid")
    evidence_states = object_states | {"existing"}
    for evidence_index, item in enumerate(data.get("evidence_register", [])):
        if not item.get("object_id"):
            errors.append(f"evidence_register[{evidence_index}] needs object_id")
        if not item.get("source"):
            errors.append(f"evidence_register[{evidence_index}] needs source")
        if item.get("observation_status") not in evidence_states:
            errors.append(f"evidence_register[{evidence_index}].observation_status is invalid")
    gate_statuses = {"pending", "passed", "failed", "not_applicable"}
    gate_ids: set[str] = set()
    for gate_index, gate in enumerate(data.get("review_gates", [])):
        gate_id = gate.get("id")
        if not gate_id:
            errors.append(f"review_gates[{gate_index}] needs an id")
        elif gate_id in gate_ids:
            errors.append(f"review_gates[{gate_index}].id {gate_id!r} is duplicated")
        else:
            gate_ids.add(gate_id)
        if gate.get("status") not in gate_statuses:
            errors.append(f"review_gates[{gate_index}].status is invalid")
    operators = {"equals", "within", "minimum", "maximum", "range", "present", "absent"}
    test_ids: set[str] = set()
    for test_index, test in enumerate(data.get("acceptance_tests", [])):
        test_id = test.get("id")
        if not test_id:
            errors.append(f"acceptance_tests[{test_index}] needs an id")
        elif test_id in test_ids:
            errors.append(f"acceptance_tests[{test_index}].id {test_id!r} is duplicated")
        else:
            test_ids.add(test_id)
        if not test.get("metric"):
            errors.append(f"acceptance_tests[{test_index}] needs a metric")
        if test.get("operator") not in operators:
            errors.append(f"acceptance_tests[{test_index}].operator is invalid")
        if test.get("operator") not in {"present", "absent"} and "expected" not in test:
            errors.append(f"acceptance_tests[{test_index}] needs expected")
        if test.get("operator") == "within" and "tolerance" not in test:
            errors.append(f"acceptance_tests[{test_index}] using 'within' needs tolerance")
        if test.get("operator") == "range" and (
            not isinstance(test.get("expected"), list) or len(test.get("expected", [])) != 2
        ):
            errors.append(f"acceptance_tests[{test_index}] using 'range' needs expected [low, high]")
        tolerance = test.get("tolerance")
        if tolerance is not None and (not isinstance(tolerance, (int, float)) or tolerance < 0):
            errors.append(f"acceptance_tests[{test_index}].tolerance must be non-negative")
        if not test.get("source"):
            errors.append(f"acceptance_tests[{test_index}] needs a source")
    for frozen_index, item in enumerate(data.get("frozen_elements", [])):
        if not item.get("id"):
            errors.append(f"frozen_elements[{frozen_index}] needs an id")
        if not item.get("accepted_revision"):
            errors.append(f"frozen_elements[{frozen_index}] needs accepted_revision")
        if not item.get("source"):
            errors.append(f"frozen_elements[{frozen_index}] needs a source")
    if data.get("unresolved_conflicts"):
        warnings.append(f"{len(data['unresolved_conflicts'])} unresolved conflict(s) require review")
    result = {"valid": not errors, "errors": errors, "warnings": warnings}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 2


def metric_lookup(metrics: dict[str, Any], key: str) -> tuple[bool, Any]:
    current: Any = metrics
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def validate_model(args: argparse.Namespace) -> int:
    manifest_path = Path(args.constraints).expanduser().resolve()
    measurements_path = Path(args.measurements).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    measurement_data = json.loads(measurements_path.read_text(encoding="utf-8"))
    metrics = measurement_data.get("metrics", measurement_data)
    if not isinstance(metrics, dict):
        raise SystemExit("Measurements must be a JSON object or contain a 'metrics' object")

    tests = manifest.get("acceptance_tests", [])
    results: list[dict[str, Any]] = []
    for test in tests:
        metric = test.get("metric", "")
        operator = test.get("operator")
        found, actual = metric_lookup(metrics, metric)
        expected = test.get("expected")
        tolerance = float(test.get("tolerance", 0.0))
        passed = False
        reason = ""
        try:
            if not found:
                reason = "measurement missing"
            elif operator in {"equals", "within"}:
                if isinstance(actual, (int, float)) and not isinstance(actual, bool) and isinstance(expected, (int, float)) and not isinstance(expected, bool):
                    passed = abs(float(actual) - float(expected)) <= tolerance
                    reason = f"absolute error {abs(float(actual) - float(expected)):.9g}, tolerance {tolerance:.9g}"
                else:
                    passed = actual == expected
                    reason = "exact comparison"
            elif operator == "minimum":
                passed = float(actual) >= float(expected) - tolerance
                reason = f"minimum {expected} with tolerance {tolerance}"
            elif operator == "maximum":
                passed = float(actual) <= float(expected) + tolerance
                reason = f"maximum {expected} with tolerance {tolerance}"
            elif operator == "range":
                low, high = expected
                passed = float(low) - tolerance <= float(actual) <= float(high) + tolerance
                reason = f"range [{low}, {high}] with tolerance {tolerance}"
            elif operator == "present":
                passed = bool(actual)
                reason = "expected a truthy presence measurement"
            elif operator == "absent":
                passed = not bool(actual)
                reason = "expected a false absence measurement"
            else:
                reason = f"unsupported operator {operator!r}"
        except (TypeError, ValueError) as exc:
            reason = f"comparison error: {exc}"
        results.append({
            "id": test.get("id"),
            "metric": metric,
            "operator": operator,
            "expected": expected,
            "actual": actual if found else None,
            "passed": passed,
            "reason": reason,
            "source": test.get("source"),
        })

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "constraints": str(manifest_path),
        "measurements": str(measurements_path),
        "passed": bool(results) and all(item["passed"] for item in results),
        "tests_total": len(results),
        "tests_passed": sum(item["passed"] for item in results),
        "warnings": [] if results else ["Constraint manifest contains no acceptance_tests"],
        "results": results,
    }
    if args.output:
        json_dump(report, Path(args.output).expanduser().resolve())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 2


def register_plan(args: argparse.Namespace) -> int:
    np, _o3d, _psutil, _pye57, _cKDTree = imports()
    source = Path(args.input).expanduser().resolve()
    data = json.loads(source.read_text(encoding="utf-8"))
    plans = data.get("reference_plans", [])
    if args.plan_index < 0 or args.plan_index >= len(plans):
        raise SystemExit(f"Plan index {args.plan_index} does not exist")
    plan = plans[args.plan_index]
    controls = plan.get("control_points", [])
    transform_type = plan.get("transform", "similarity")
    minimum = 3 if transform_type == "affine" else 2
    if len(controls) < minimum:
        raise SystemExit(f"{transform_type} registration needs at least {minimum} control points")

    try:
        plan_xy = np.asarray([item["plan_xy"][:2] for item in controls], dtype=float)
        scan_xy = np.asarray(
            [(item.get("scan_xy") or item.get("scan_xyz"))[:2] for item in controls],
            dtype=float,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("Each control point needs numeric plan_xy and scan_xy or scan_xyz") from exc
    if plan_xy.shape != scan_xy.shape or plan_xy.shape[1] != 2 or not np.isfinite(plan_xy).all() or not np.isfinite(scan_xy).all():
        raise SystemExit("Control-point arrays must be finite Nx2 values")

    if transform_type in {"rigid", "similarity"}:
        source_center = plan_xy.mean(axis=0)
        target_center = scan_xy.mean(axis=0)
        centered_source = plan_xy - source_center
        centered_target = scan_xy - target_center
        u, singular, vt = np.linalg.svd(centered_source.T @ centered_target)
        rotation = vt.T @ u.T
        if np.linalg.det(rotation) < 0:
            vt[-1, :] *= -1
            rotation = vt.T @ u.T
        if transform_type == "similarity":
            denominator = float(np.sum(centered_source**2))
            if denominator <= 0:
                raise SystemExit("Plan control points do not span a measurable distance")
            scale = float(np.sum(singular) / denominator)
        else:
            scale = 1.0
        linear = scale * rotation
        translation = target_center - source_center @ linear.T
    elif transform_type == "affine":
        design = np.column_stack([plan_xy, np.ones(len(plan_xy))])
        coefficients, _residuals, rank, _singular = np.linalg.lstsq(design, scan_xy, rcond=None)
        if rank < 3:
            raise SystemExit("Affine control points are collinear or otherwise degenerate")
        linear = coefficients[:2, :].T
        translation = coefficients[2, :]
        scale = None
    else:
        raise SystemExit("Plan transform must be rigid, similarity, or affine")

    predicted = plan_xy @ linear.T + translation
    residuals = np.linalg.norm(predicted - scan_xy, axis=1)
    tolerance = float(plan.get("tolerance_m", args.tolerance_m))
    matrix = [
        [float(linear[0, 0]), float(linear[0, 1]), float(translation[0])],
        [float(linear[1, 0]), float(linear[1, 1]), float(translation[1])],
        [0.0, 0.0, 1.0],
    ]
    rms = float(np.sqrt(np.mean(residuals**2)))
    maximum = float(np.max(residuals))
    plan["registration"] = {
        "transform": transform_type,
        "matrix_3x3": matrix,
        "uniform_scale": scale,
        "rms_residual_m": rms,
        "max_residual_m": maximum,
        "control_point_residuals_m": residuals.tolist(),
        "tolerance_m": tolerance,
        "status": "within_tolerance" if maximum <= tolerance else "review_required",
        "generated_at": utc_now(),
    }
    output = Path(args.output).expanduser().resolve()
    json_dump(data, output)
    print(json.dumps(plan["registration"], indent=2, ensure_ascii=False))
    return 0 if maximum <= tolerance else 2


def doctor(_args: argparse.Namespace) -> int:
    details: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "cloudcompare": None,
        "sketchup": None,
        "dependencies": {},
    }
    details["cloudcompare"] = find_executable(
        "E57_MODEL_CLOUDCOMPARE",
        [Path("/Applications/CloudCompare.app/Contents/MacOS/CloudCompare")],
        ["CloudCompare", "cloudcompare"],
    )
    sketchup_candidates = sorted(
        Path("/Applications").glob("SketchUp */SketchUp.app/Contents/MacOS/SketchUp"),
        reverse=True,
    ) if sys.platform == "darwin" else []
    details["sketchup"] = find_executable(
        "E57_MODEL_SKETCHUP",
        sketchup_candidates,
        ["SketchUp", "SketchUp.exe"],
    )
    for name in ("numpy", "scipy", "pye57", "open3d", "psutil"):
        try:
            __import__(name)
            details["dependencies"][name] = importlib.metadata.version(name)
        except Exception as exc:
            details["dependencies"][name] = f"unavailable: {exc}"
    print(json.dumps(details, indent=2, ensure_ascii=False))
    dependencies_ok = all(not str(value).startswith("unavailable") for value in details["dependencies"].values())
    return 0 if dependencies_ok else 2


def find_executable(environment_variable: str, candidates: list[Path], commands: list[str]) -> str | None:
    configured = os.environ.get(environment_variable)
    if configured:
        configured_path = Path(configured).expanduser()
        return str(configured_path) if configured_path.exists() else None
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    for command in commands:
        found = shutil.which(command)
        if found:
            return found
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor", help="Check local applications and Python dependencies")
    doctor_parser.set_defaults(func=doctor)

    analyze_parser = sub.add_parser("analyze", help="Inspect an E57 and recommend model settings")
    analyze_parser.add_argument("input")
    analyze_parser.add_argument("--output", required=True)
    analyze_parser.add_argument("--markdown")
    analyze_parser.add_argument("--sample-points", type=int, default=DEFAULT_SAMPLE_POINTS)
    analyze_parser.add_argument("--max-read-points", type=int, default=DEFAULT_MAX_READ_POINTS)
    analyze_parser.set_defaults(func=analyze)

    mesh_parser = sub.add_parser("mesh", help="Create a cleaned reference mesh and SketchUp DAE")
    mesh_parser.add_argument("input")
    mesh_parser.add_argument("--analysis", required=True)
    mesh_parser.add_argument("--profile", choices=("recommended", "light", "balanced", "detailed", "custom"), default="recommended")
    mesh_parser.add_argument("--resolution-mm", type=float, help="Required physical resolution for --profile custom")
    mesh_parser.add_argument("--target-triangles", type=int, help="Required triangle budget for --profile custom")
    mesh_parser.add_argument("--allow-unsupported-resolution", action="store_true", help="Allow custom resolution finer than measured spacing")
    mesh_parser.add_argument("--output-base", required=True)
    mesh_parser.add_argument("--max-points", type=int, default=5_000_000)
    mesh_parser.add_argument("--poisson-depth", type=int, default=9)
    mesh_parser.add_argument("--trim-quantile", type=float, default=0.02)
    mesh_parser.add_argument("--recenter", choices=("auto", "centroid", "none"), default="auto")
    mesh_parser.set_defaults(func=mesh_command)

    init_parser = sub.add_parser("init-constraints", help="Create a constraint manifest from an analysis")
    init_parser.add_argument("--analysis", required=True)
    init_parser.add_argument("--output", required=True)
    init_parser.set_defaults(func=init_constraints)

    validate_parser = sub.add_parser("validate-constraints", help="Validate a constraint manifest")
    validate_parser.add_argument("input")
    validate_parser.set_defaults(func=validate_constraints)

    model_validate_parser = sub.add_parser("validate-model", help="Check model measurements against manifest acceptance tests")
    model_validate_parser.add_argument("constraints", help="Constraint manifest containing acceptance_tests")
    model_validate_parser.add_argument("measurements", help="Project-generated JSON measurements keyed by metric name")
    model_validate_parser.add_argument("--output", help="Optional JSON acceptance report")
    model_validate_parser.set_defaults(func=validate_model)

    register_parser = sub.add_parser("register-plan", help="Fit a plan-to-scan transform from control points")
    register_parser.add_argument("input", help="Constraint manifest with reference plan control points")
    register_parser.add_argument("--plan-index", type=int, default=0)
    register_parser.add_argument("--tolerance-m", type=float, default=0.05)
    register_parser.add_argument("--output", required=True)
    register_parser.set_defaults(func=register_plan)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

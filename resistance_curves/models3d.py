"""Orthographic inspection and metric landmarks for rigid mesh scenes."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image, ImageDraw

from .mechanics import FIELDS, estimate

AXES = dict(zip("xyz", np.eye(3)))
AXES.update({f"-{name}": -vector for name, vector in list(AXES.items())})
METRES = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254}


def _read_scene(path, units):
    import trimesh

    ext = path.suffix.lower()
    if ext not in (".glb", ".gltf", ".stl", ".obj", ".step", ".stp"):
        raise ValueError(f"Unsupported model format: {ext}. Export STEP, GLB, glTF, OBJ or STL.")
    if ext in (".glb", ".gltf", ".step", ".stp"):
        if units not in (None, "m"):
            raise ValueError("glTF and imported STEP world coordinates use metres. Use --units m or omit --units.")
        units = "m"
    if units not in METRES:
        raise ValueError("Supply --units m, cm, mm or in for OBJ and STL.")

    scene = trimesh.load_scene(path, process=False, skip_materials=True)
    objects, triangles = [], []
    geometry_hash = hashlib.sha256()
    for node in sorted(scene.graph.nodes_geometry):
        transform, key = scene.graph[node]
        mesh = scene.geometry[key]
        if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
            continue
        matrix = np.diag([METRES[units]] * 3 + [1]) @ transform
        vertices = trimesh.transform_points(mesh.vertices, matrix)
        if not np.isfinite(vertices).all():
            raise ValueError(f"Nonfinite geometry in {node}")
        triangles.append(vertices[mesh.faces])
        geometry_hash.update(triangles[-1].astype("<f8").tobytes())
        objects.append({"node": node, "mesh": key, "triangles": len(mesh.faces),
                        "bounds_m": [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()],
                        "local_to_world_m": matrix.tolist()})
    if not triangles:
        raise ValueError("The scene contains no readable triangle meshes.")
    return np.concatenate(triangles), {
        "file": path.name, "units": units, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "world_geometry_sha256": geometry_hash.hexdigest(), "parts": objects,
    }


def _render(triangles, center, scale, right, up, path):
    depth = np.cross(right, up)
    screen = np.stack((right, -up), axis=1)
    pixels = (triangles - center) @ screen * scale + 500
    order = np.argsort(triangles.mean(axis=1) @ depth)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    light = (depth + up * 0.7 - right * 0.4) / np.sqrt(1.65)
    intensity = np.abs(normals @ light) / np.maximum(lengths, 1e-30)
    shades = (90 + 125 * np.clip(intensity, 0, 1)).astype(int)
    image = Image.new("RGB", (1000, 1000), "white")
    draw = ImageDraw.Draw(image)
    for index in order:
        shade = int(shades[index])
        draw.polygon(pixels[index].ravel().tolist(), fill=(shade-16, shade-5, shade))
    image.save(path, quality=94)


def prepare_models(paths, folder, *, right="x", up="y", units=None, source):
    if not paths or not source.strip():
        raise ValueError("Supply posed model files in lifting order and their source.")
    horizontal, vertical = AXES[right], AXES[up]
    if np.dot(horizontal, vertical):
        raise ValueError("The right and up axes must be perpendicular.")
    if folder.exists():
        raise ValueError(f"Output directory already exists: {folder}")
    scenes = [_read_scene(path, units) for path in paths]
    bounds = np.array([part["bounds_m"] for _, asset in scenes for part in asset["parts"]])
    low, high = bounds[:, 0].min(axis=0), bounds[:, 1].max(axis=0)
    if (high - low).max() <= 0:
        raise ValueError("The model has zero extent.")
    center, scale = (low + high) / 2, 930 / (high - low).max()
    manifest = {"source": source, "center_m": center.tolist(), "px_per_m": float(scale),
                "right": right, "up": up, "assets": [asset for _, asset in scenes]}
    depth = np.cross(horizontal, vertical)
    folder.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=folder.parent) as temp:
        stage = Path(temp) / "session"
        stage.mkdir()
        for i, (triangles, _) in enumerate(scenes, 1):
            for name, r, u in [("pose", horizontal, vertical), ("end", -depth, vertical),
                                ("top", horizontal, -depth)]:
                _render(triangles, center, scale, r, u, stage / f"{name}-{i:03}.jpg")
        (stage / "model.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
        stage.rename(folder)
    return manifest


def _world_point(point, asset):
    if isinstance(point, dict):
        part = next((p for p in asset["parts"] if p["node"] == point.get("node")), None)
        if part is None:
            raise ValueError(f"Unknown model node: {point.get('node')}")
        xyz = np.asarray(point.get("local"), dtype=float)
        if xyz.shape != (3,) or not np.isfinite(xyz).all():
            raise ValueError("A node landmark needs three finite local coordinates.")
        return (np.asarray(part["local_to_world_m"]) @ np.append(xyz, 1))[:3]
    xyz = np.asarray(point, dtype=float)
    if xyz.shape != (3,) or not np.isfinite(xyz).all():
        raise ValueError("Expected three finite world coordinates in metres.")
    return xyz


def model_observation(manifest, landmarks):
    kind = landmarks.get("mechanism")
    if kind not in FIELDS:
        raise ValueError("Choose lever, belt_cam or sled for a supported load path.")
    poses = landmarks.get("poses")
    if not isinstance(poses, list) or len(poses) != len(manifest["assets"]):
        raise ValueError("Mark one pose per prepared mesh scene.")
    evidence = landmarks.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("Describe the moving parts, orientation and travel evidence.")
    space = landmarks.get("space", "world_m")
    if space not in ("world_m", "side_pixels"):
        raise ValueError("Choose world_m or side_pixels for landmark coordinates.")
    screen = np.stack((AXES[manifest["right"]], -AXES[manifest["up"]]))
    projected = []
    for pose, asset in zip(poses, manifest["assets"]):
        if not isinstance(pose, dict) or any(k not in pose for k in FIELDS[kind]):
            raise ValueError(f"Required {kind} landmarks: {', '.join(FIELDS[kind])}")
        points = {}
        for name in FIELDS[kind]:
            point = pose[name]
            if space == "world_m":
                delta = _world_point(point, asset) - manifest["center_m"]
                point = (500 + manifest["px_per_m"] * (screen @ delta)).tolist()
            points[name] = point
        projected.append(points)
    # Keep the record self-contained. The full scene graph stays in the work directory.
    provenance = {k: manifest[k] for k in ("source", "center_m", "px_per_m", "right", "up")}
    provenance["assets"] = [{k: v for k, v in a.items() if k != "parts"} for a in manifest["assets"]]
    provenance["space"] = space
    provenance["landmarks"] = poses
    if space == "world_m":
        provenance["world_m"] = [
            {name: _world_point(p[name], a).tolist() for name in FIELDS[kind]}
            for p, a in zip(poses, manifest["assets"])
        ]
    result = {"mechanism": kind, "poses": projected, "evidence": evidence, "model_source": provenance}
    if "sweep_deg" in landmarks:
        result["sweep_deg"] = landmarks["sweep_deg"]
    estimate(result)
    return result

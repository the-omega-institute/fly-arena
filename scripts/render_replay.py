"""Export map PNGs and recorded anatomical poses as MP4; never advance physics.

See docs/rendering.md for the verified GPU worker rendering environment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import imageio.v2 as imageio
import mujoco as mj
import numpy as np
from OpenGL import GL
from PIL import Image, ImageDraw, ImageFont

from flyarena.body import Bodies
from flyarena.scenarios import MAPS, scenario

COLORS = [(0.40, 0.86, 0.71, 1), (0.98, 0.48, 0.36, 1)]
BG = (18, 29, 30)


def font(size):
    for path in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


class Exporter:
    def __init__(self, scene, frame=None):
        self.scene = scene
        self.count = len(scene.get("flies", [])) or (len(frame["positions"]) if frame else (1 if scene.get("modes") == ["forage"] else 2))
        self.playback_label = "0.25x playback"
        self.bodies = Bodies(scene, self.count, 42)
        self.model, self.data = self.bodies.model, self.bodies.data
        self.manifest = scene.get("body") or self.bodies.rendering_manifest()
        # Pose ordering belongs to the recorded mesh manifest, not model iteration.
        for geom in self.manifest["geoms"]:
            name = mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_GEOM, geom["id"])
            if name != geom["name"]:
                raise ValueError("Replay requires its original FlyGym body version")
        self.model.vis.global_.offwidth = 1280
        self.model.vis.global_.offheight = 640
        self.model.vis.headlight.ambient[:] = .4
        self.model.vis.headlight.diffuse[:] = .8
        self.model.vis.quality.shadowsize = 2048
        self.renderer = mj.Renderer(self.model, width=1280, height=640)
        self.device = {"renderer": GL.glGetString(GL.GL_RENDERER).decode(),
                       "vendor": GL.glGetString(GL.GL_VENDOR).decode(),
                       "version": GL.glGetString(GL.GL_VERSION).decode()}
        self.camera = mj.MjvCamera()
        self.camera.lookat[:] = [0, 0, 0]
        self.camera.distance = scene["size"] * 1.6
        self.camera.azimuth = 90
        self.camera.elevation = -35 if scene.get("habitat") == "forest-floor" else -65
        if scene.get("habitat") == "forest-floor":
            self.camera.azimuth = 125
            self.camera.lookat[:] = [0, 0, .6]
        self.initial = frame or {
            **self.bodies.snapshot(), "food": [p["initial"] for p in scene["food"]],
            "scores": [0] * self.count, "eliminated": [False] * self.count}

    def geom(self, kind, size, pos, color, mat=None):
        sc = self.renderer.scene
        if sc.ngeom >= sc.maxgeom:
            raise ValueError("Render scene exceeds geometry capacity")
        g = sc.geoms[sc.ngeom]
        mj.mjv_initGeom(g, kind, np.array(size, float), np.array(pos, float),
                       np.eye(3).ravel() if mat is None else mat, np.array(color, float))
        sc.ngeom += 1
        return g

    def line(self, a, b, radius, color):
        g = self.geom(mj.mjtGeom.mjGEOM_CAPSULE, [1, 1, 1], [0, 0, 0], color)
        mj.mjv_connector(g, mj.mjtGeom.mjGEOM_CAPSULE, radius, np.array(a), np.array(b))

    def render(self, frame=None, history=()):
        frame = frame or self.initial
        if len(frame["poses"]) != len(self.manifest["geoms"]):
            raise ValueError("Recorded pose count does not match body manifest")
        self.renderer.update_scene(self.data, camera=self.camera)
        sc = self.renderer.scene
        # Extend the visual ground beyond the physics floor so the camera never
        # exposes the model's white skybox. This adds no collision geometry.
        self.geom(mj.mjtGeom.mjGEOM_PLANE, [200, 200, .1], [0, 0, -.025], [.10, .17, .17, 1])
        poses = {g["id"]: (g["slot"], p)
                 for g, p in zip(self.manifest["geoms"], frame["poses"], strict=True)}
        for g in sc.geoms[:sc.ngeom]:
            if g.objtype != mj.mjtObj.mjOBJ_GEOM:
                continue
            if g.objid in poses:
                slot, p = poses[g.objid]
                g.pos[:] = p[:3]
                mat = np.empty(9)
                quat = np.array(p[3:], dtype=float)
                quat /= np.linalg.norm(quat)
                mj.mju_quat2Mat(mat, quat)
                g.mat[:] = mat.reshape(3, 3)
                g.rgba[:] = COLORS[slot]
                g.matid = -1
            else:
                g.matid = -1
                if self.scene.get("habitat") == "forest-floor":
                    if g.type == mj.mjtGeom.mjGEOM_PLANE:
                        g.rgba[:] = [.20, .16, .10, 1]
                    elif 0 <= g.objid < self.model.ngeom:
                        g.rgba[:] = self.model.geom_rgba[g.objid]
                else:
                    g.rgba[:] = [.10, .17, .17, 1] if g.type == mj.mjtGeom.mjGEOM_PLANE else [.40, .43, .55, 1]
        h = self.scene["size"] / 2
        for t in ([] if self.scene.get("habitat") == "forest-floor" else np.arange(-h, h + .1, 2)):
            self.line([-h, t, .012], [h, t, .012], .012, [.19, .27, .27, 1])
            self.line([t, -h, .012], [t, h, .012], .012, [.19, .27, .27, 1])
        corners = [[-h, -h, .03], [h, -h, .03], [h, h, .03], [-h, h, .03]]
        for i in range(4):
            self.line(corners[i], corners[(i + 1) % 4], .045, [.66, .75, .68, 1])
        if "ring_radius" in self.scene:
            angles = np.linspace(0, 2 * np.pi, 97)
            points = [[self.scene["ring_radius"] * np.cos(a),
                       self.scene["ring_radius"] * np.sin(a), .04] for a in angles]
            for a, b in zip(points, points[1:]):
                self.line(a, b, .06, [.7, .88, .72, 1])
        for food, left in zip(self.scene["food"], frame["food"], strict=True):
            x, y, z = food["position"]
            self.geom(mj.mjtGeom.mjGEOM_CYLINDER, [1.1, .015, 0], [x, y, z - .115], [.35, .29, .14, 1])
            if left > 0:
                r = .8 * np.sqrt(left / food["initial"])
                self.geom(mj.mjtGeom.mjGEOM_ELLIPSOID, [r, r, .14], [x, y, z - .03], [.97, .72, .25, 1])
        for slot in range(self.count):
            for a, b in zip(history, history[1:]):
                self.line([*a["positions"][slot][:2], .07],
                          [*b["positions"][slot][:2], .07], .022, COLORS[slot])
        pixels = self.renderer.render()
        result = Image.new("RGB", (1280, 896), BG)
        result.paste(Image.fromarray(pixels), (0, 90))
        draw = ImageDraw.Draw(result)
        draw.text((36, 20), "FLY ARENA  /  " + self.scene["english"], font=font(30), fill="#e5eadb")
        title = "RECORDED LIFE  |  " + self.playback_label if "flies" in self.scene else "MAP PREVIEW  |  initial body poses"
        draw.text((38, 61), title, font=font(15), fill="#9bab9e")
        draw.text((38, 746), f"SIM TIME  {frame['time']:.2f} s    /    FOOD LEFT  {sum(frame['food']):.3f}", font=font(21), fill="#eac980")
        for slot in range(self.count):
            name = self.scene.get("flies", [{"name": "Fly A"}, {"name": "Fly B"}])[slot]["name"].split(" / ")[0]
            status = "  [EXITED]" if frame["eliminated"][slot] else ""
            label = f"{slot+1}  {name}   {frame['scores'][slot]:.4f}{status}"
            color = tuple(int(v * 255) for v in COLORS[slot][:3])
            draw.text((38 + slot * 625, 788), label, font=font(21), fill=color)
        draw.text((38, 850), "FlyGym anatomical meshes / mm   |   " + self.device["renderer"], font=font(14), fill="#9bab9e")
        return np.array(result)

    def close(self):
        self.renderer.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, help="Directory containing scene.json and frames.json")
    parser.add_argument("--maps", action="store_true", help="Export all map previews")
    parser.add_argument("--map", choices=list(MAPS), help="Export only one map preview")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-renderer", default="", help="Fail unless GL renderer contains this string")
    parser.add_argument("--frame-time", type=float, help="Export one actual replay sample at or before this simulation time")
    args = parser.parse_args()
    if args.frame_time is not None and not args.replay:
        parser.error("--frame-time requires --replay")
    if not args.maps and not args.map and not args.replay:
        parser.error("Provide --map, --maps and/or --replay")
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = []

    def open_export(scene, frame=None):
        export = Exporter(scene, frame)
        print(json.dumps(export.device), flush=True)
        if args.require_renderer.lower() not in export.device["renderer"].lower():
            export.close()
            raise RuntimeError("Requested GPU renderer is not active")
        return export

    if args.maps or args.map:
        for key in (MAPS if args.maps else [args.map]):
            export = open_export(scenario(key, 42))
            try:
                imageio.imwrite(args.output / f"map-{key}.png", export.render())
                evidence.append({"map": key, "kind": "initial-pose-preview", **export.device})
            finally:
                export.close()
    if args.replay:
        scene = json.loads((args.replay / "scene.json").read_text())
        frames = json.loads((args.replay / "frames.json").read_text())
        times = np.array([f["time"] for f in frames])
        if len(times) < 2 or np.any(np.diff(times) <= 0):
            raise ValueError("Replay timestamps must be strictly increasing")
        export = open_export(scene, frames[0])
        try:
            if args.frame_time is not None:
                if not np.isfinite(args.frame_time) or not times[0] <= args.frame_time <= times[-1]:
                    raise ValueError("Requested frame is outside the recorded replay")
                i = int(np.searchsorted(times, args.frame_time, side="right") - 1)
                export.playback_label = "recorded frame"
                imageio.imwrite(args.output / f"frame-{i:04d}.png", export.render(frames[i], frames[:i+1:4]))
                evidence.append({"kind":"recorded-pose-still", "source":str(args.replay),
                                 "simulation_time":float(times[i]), "participants":export.count, **export.device})
            else:
                # Resample by timestamps, including irregular terminal frames. No invented poses.
                playback = np.arange(times[0], times[-1] + 1e-9, .25 / 25)
                indices = np.searchsorted(times, playback, side="right") - 1
                indices = np.append(indices, len(frames) - 1) if indices[-1] != len(frames) - 1 else indices
                with imageio.get_writer(args.output / "replay.mp4", fps=25, codec="libx264", quality=8) as writer:
                    for i in indices:
                        pixels = export.render(frames[i], frames[:i+1:4])
                        writer.append_data(pixels)
                        if i in {0, len(frames)//2, len(frames)-1}:
                            imageio.imwrite(args.output / f"frame-{i:04d}.png", pixels)
                evidence.append({"kind": "recorded-pose-replay", "source": str(args.replay),
                                 "frames": len(frames), "video_frames": len(indices), "fps": 25,
                                 "playback_speed": .25, "simulation_seconds": float(times[-1]-times[0]),
                                 "encoding": "CPU libx264; scene rasterization uses reported GL renderer",
                                 **export.device})
        finally:
            export.close()
    (args.output / "render-info.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()

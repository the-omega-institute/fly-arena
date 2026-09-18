# Offline map and match rendering

`scripts/render_replay.py` exports four map previews and a recorded match as a
1280 × 896 MP4, with simulation time, scores, remaining food and exit status.
It renders the FlyGym anatomical meshes at their recorded world poses and never
steps physics or runs a neural simulation. Colored ground lines show recorded
thorax trajectories. Map previews use initial poses, not competition results.

Run from the repository with its existing Python environment:

```sh
python scripts/render_replay.py --maps \
  --replay var/runs/MATCH_ID/1 \
  --output var/renders/MATCH_ID
```

The input directory must contain `scene.json` and `frames.json`. Use the body
dependency version associated with the recording. The exporter checks geometry
names and pose counts before drawing. The current FlyGym dependency provides
MuJoCo, Pillow, PyOpenGL, imageio and imageio-ffmpeg.

## Verified RTX 4060 node

On `deepevo-4060-ssh`, the default EGL context reports **llvmpipe**, a CPU software
renderer. Finding a GPU with `nvidia-smi` does not establish GPU rasterization.
The WSLg D3D12 route below reports
`D3D12 (NVIDIA GeForce RTX 4060 Laptop GPU)`:

```sh
cd /tmp/fly-arena-embodied-v020
DISPLAY=:0 MUJOCO_GL=glfw GALLIUM_DRIVER=d3d12 \
LD_LIBRARY_PATH=/usr/lib/wsl/lib \
MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA \
flock -w 30 /tmp/fly-arena-gpu.lock \
  .venv/bin/python scripts/render_replay.py \
  --maps --replay var/node-jobs/MATCH_ID/evidence \
  --output var/renders/MATCH_ID --require-renderer 'RTX 4060'
```

This creates an invisible graphics context; it does not automate a browser.
`--require-renderer` fails if the expected GPU is absent. Each export saves the
actual OpenGL renderer, vendor and version in `render-info.json`. Video encoding
uses CPU libx264; scene rasterization uses the reported OpenGL device.

The video uses 25 frames per second and 0.25× playback. Timestamps select recorded
poses without invented gait or interpolated neural activity. Two simulation
seconds therefore produce approximately eight video seconds. PNG frames at the
start, midpoint and end provide a quick inspection alongside the MP4.

Rendered assets live under ignored `var/renders/`; do not commit large videos or
replay data. GPU rendering is independent of the current CPU/Numba neural worker
and does not imply that neural simulation or training uses CUDA.

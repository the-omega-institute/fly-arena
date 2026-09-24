# `arena-geometry-v1`

This document defines the geometry envelope shared by the Python simulator,
research reports, map preview API, and browser renderer. It describes recorded
and modeled scene geometry only; it does not imply that a pose, trajectory, or
neural activity was measured when the corresponding field is absent.

## Coordinates and units

All distances are millimetres. The world is right-handed: **X** is the arena's
east/west axis, **Y** is north/south, and **Z** is up. Ground is `z = 0`.
Coordinates in a food position are `[x, y, z]`. A food height is part of the
scene record; the common ground food height is `0.15` mm and raised food keeps
its explicit map height.

An obstacle `position` is its centre, and `size` is its full extent along its
local X, Y, and Z axes. A size of `[2, 4, 1]` therefore reaches one mm on
either side of its centre in local X, two in local Y, and 0.5 in local Z.
There is no half-extent encoding in the JSON contract. The renderer scales its
unit geometry by this full size before applying the rotation.

The supported shape tags are `box` and `ellipsoid`. A box uses a unit cube;
an ellipsoid uses a unit-diameter sphere scaled by the full size. Materials
(`leaf`, `rock`, and `fruit`) and an optional display colour do not affect
collision geometry. The terrarium ramps are boxes with a quaternion and a
thin Z extent; there is no separate `ramp` collision primitive. Cylinders and
other shape names are invalid until a versioned contract adds them.

## Rotations and spawns

Obstacle quaternions use MuJoCo's `[w, x, y, z]` order. The web renderer
converts that value to three.js `[x, y, z, w]` only at the rendering boundary;
the stored scene value stays MuJoCo order. A quaternion must contain finite
values and be non-zero. Consumers may normalize it for a matrix, but must not
rewrite the serialized scene (historical scene hashes depend on the original
decimal values).

A spawn is `[x, y, yaw]`. Its third value is a heading in radians around the
world Z axis and is never an altitude or a body pose. Seeded paired spawns are
part of each map's frozen layout. Food jitter is the only seeded change in a
legacy scenario.

The arena ground bounds are `[-size/2, size/2]` on X and Y, with the lower
ground plane at Z zero. Obstacles, food, and recorded trajectories may extend
above that nominal plane. A closed wall is represented by its individual box
segments, including each segment's centre, full size, and tangent quaternion;
segments are not silently replaced by an abstract boundary.

## Probe scenes

`experiments.probes.make_scene` emits the same obstacle, spawn, and food
vectors. Its additional `mirror`, chemical policy, and cue timing fields
describe the stimulus protocol, not extra geometry. `research.SceneObstacle`
and `ProbeScene` validate the shared vectors at report parsing time. A probe
report can contain planar trajectory samples (`x`, `y`, `yaw`); those samples
do not establish altitude, body articulation, gait, or an unrecorded pose.

The phenotype 3D view consumes only a validated probe scene and renders its
recorded planar tracks over illustrative ground and lighting. Missing,
malformed, or conflicting scenes leave the geometry unavailable. It never
fills missing dimensions with a guessed obstacle, food point, or pose.

## Boundary rules

`src/flyarena/geometry.py` is the reference validator. Scenario serialization,
the map preview endpoint, and research report models call it. Validation is
pure and preserves valid input representations so existing seeded scene
digests and MuJoCo collision inputs remain unchanged. The shared fixture at
`tests/fixtures/geometry_contract.json` is generated from Python scenes and
checked by both the Python and TypeScript test suites.
Exact generated bridge-scene digest pins are enforced on the macOS deployment platform (recorded as `pin_platform: darwin` in the fixture), while tolerant structural checks run on all platforms because cross-platform bitwise equality is not promised (see [operations](OPERATIONS.md)).

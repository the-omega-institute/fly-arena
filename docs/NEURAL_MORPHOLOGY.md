# Real neuron morphology and recorded activity

The previous anatomical view showed soma locations and straight lines between connected somata. That is insufficient for a fiber-level brain view: soma coordinates do not contain axonal paths or dendritic branching.

The MaleCNS v1.0 release supplies public centerline skeletons with the same body IDs used by Arena’s canonical graph. On 2026-09-20, the official download documentation and live SWC files were checked:

- [Official MaleCNS data, skeleton formats and license](https://male-cns.janelia.org/download/)
- [Example: recorded projection neuron 10084](https://storage.googleapis.com/flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/10084.swc)
- [Example: recorded tactile neuron 802939](https://storage.googleapis.com/flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/802939.swc)
- [Official Neuroglancer dataset scene](https://neuroglancer-demo.appspot.com/#!gs://flyem-male-cns/v1.0/male-cns-v1.0.json)
- [Neuroglancer renderer](https://github.com/google/neuroglancer): WebGL volumes, meshes and skeletons.
- [navis morphology tooling](https://navis-org.github.io/navis/): analysis and visualization; recommended by the MaleCNS documentation, including neuPrint access and coordinate transforms.

The public SWC directory needs no account or neuPrint token. Its coordinates are in MaleCNS EM space, **8 nm per coordinate unit**, matching the soma metadata already imported. Other distributions use nanometers or transformed template coordinates and must not be mixed without a transform. Source license: **CC-BY 4.0**, Male CNS Connectome, Berg et al., Cell (2026), FlyEM / Janelia and collaborators.

## What is implemented

`scripts/prepare_morphology.py` downloads the current replay’s recorded neuron skeletons and a bounded, explicitly labeled sample across source-annotated brain superclasses. It preserves all source parent branches and coordinates. The prepared sample contains 232 neurons and 723,390 segments, including all 66 recorded neurons in the example contest. The remaining structures provide anatomical context; they do not gain invented activity.

The browser renders actual fibers with Three.js, retaining the existing body and event clock. Geometry remains fixed while a small per-neuron GPU texture changes activity brightness, so replay does not rebuild hundreds of thousands of branches at every frame. Brain/CNS framing, rotation, zoom, and an expanded view are available.

- **Recorded activity:** each neuron’s recorded value controls brightness across its real skeleton, preserving spatial region colors. Unrecorded fibers stay dim and never flash. Zero and missing retain separate recording flags. Selection does not override activity brightness.
- **Neuron morphology:** color identifies the actual spatial neuropil compartment, not neuron class. Selection brightens the selected skeleton only in this static mode. The same neuron can cross several differently colored regions.
- Current LIF/rate models represent neurons as single compartments. Uniformly coloring a neuron’s morphology does **not** simulate voltage propagation along its axon or dendrites. No traveling light waves are invented.
- The prepared shape set is a sample, not 165,122 skeletons and not whole-brain activity imaging. Existing replays retain their original 66 activity samples. Loading additional skeletons cannot recover activity that was never recorded.

Installation on an existing dataset:

```sh
python scripts/prepare_morphology.py \
  --frames var/research/replay-gallery-v1/MATCH_ID-frames.json
```

This writes `data/connectome/morphology.json`, served by `/api/v1/connectome/morphology`. On deployments using a custom `ARENA_DATA`, install it under that directory’s `connectome/`. If absent, the page explicitly falls back to the soma/connectivity view. No network requests or morphology preprocessing enter the simulation loop.

## Remaining scientific visualization work

To display widespread activity over time, record dense neuron activity from new simulation runs into compact, time-chunked arrays and join by the canonical neuron IDs. The simulator already maintains a rate for every retained neuron; the current replay export only samples a small subset. Expand recording, not inference from the nearby soma or a group average.

For a 20-second single-fly run sampled at 20 Hz, 165,122 neurons at float16 require approximately 132 MB before compression. Make this an explicit observation option, stream only visible time windows, and keep the original sampling interval and units. Historical 66-neuron replays must stay labeled as such. Optional translucent neuropil surfaces can complement the implemented spatial fiber colors. Dense activity is not delivered merely by importing skeletons or parcellation.

## Spatial region colors

`scripts/prepare_brain_regions.py` samples the official [fullbrain-roi-v4 volume](https://storage.googleapis.com/flyem-male-cns/rois/fullbrain-roi-v4/info), using the source [region labels](https://storage.googleapis.com/flyem-male-cns/rois/fullbrain-roi-v4/segment_properties/info). The offline preprocessing tool needs `tensorstore`; the web server and simulator do not.

```sh
uv pip install tensorstore
python scripts/prepare_brain_regions.py
```

SWC coordinates are converted from 8 nm units to the volume’s 2048 nm voxel grid; each fiber segment receives the label of its midpoint’s containing voxel. This is a 2.048 µm anatomical assignment, with approximate compartment boundaries at that resolution. Neuron classes and soma locations are not used to guess regions. Gray means unassigned or outside the brain volume, including the VNC; zero labels are never filled by nearest-region guesses. Hues are a stable display palette, not experimentally measured colors.

The current sample assigns 577,645 segments to 86 spatial regions; 145,745 segments remain unassigned. The collapsible legend names regions including left/right hemisphere labels. Region colors are preserved in both structure and activity modes. There are no point sprites, randomly timed flashes, or traveling synthetic spikes in the fiber renderer. Activity is recorded rate data on the shared body/brain replay clock. The enlarged brain has the same play/pause and seek controls, including synchronized comparison playback.

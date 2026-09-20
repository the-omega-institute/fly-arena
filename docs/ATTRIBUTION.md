# Sources and scope

- MaleCNS v1.0: https://male-cns.janelia.org/ and official Janelia Google Cloud release `gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/`. Each downloaded/derived file is recorded in `data/connectome/manifest.json` with its SHA256. Follow the dataset's current citation and reuse terms when redistributing data; this repository does not vendor the dataset.
- FlyGym 2.1.0 / NeuroMechFly body, locomotion demonstration and MuJoCo integration: https://github.com/NeLy-EPFL/flygym . The package and its packaged meshes/controllers retain upstream licenses. The preview uses its simplified anatomical model. The fixed low-level gait is an upstream controller, not a learned fruit fly motor system.
- MuJoCo: https://github.com/google-deepmind/mujoco . Native physics implementation, locked with dependencies in `uv.lock`.
- Eon: used as a research reference for the documented LIF parameter family. No Eon implementation was copied into this repository. `neural.py` is an independent numerical implementation. MaleCNS is a different connectome from Eon's FlyWire setup; their behavior is not assumed equivalent.
- React, Three.js, React Three Fiber, Drei, Lucide, FastAPI, NumPy, SciPy, PyArrow and Numba retain their respective upstream licenses. `uv.lock` and `web/package-lock.json` record versions.

The model assigns ACh a positive sign and GABA/Glu a negative sign, leaving other/unknown signs zero. That is a simplifying modeling policy, not complete transmitter physiology. Anatomical zero-effective connections remain in the graph and manifest.

Current circuit labels identify annotation-derived groups of presynaptic neurons. They do not establish causal behavior labels such as “aggression +15%”. Current sliders therefore name actual circuits and require empirical comparison of behavior. Online learning and imported executable plasticity rules are deliberately absent from this alpha's contract.
- MaleCNS neuron centerline skeletons: official `gs://flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/`, Male CNS Connectome, Berg et al., Cell (2026), FlyEM / Janelia and collaborators, CC-BY 4.0. Arena preserves source coordinates and branches; display colors and activity overlays are Arena renderings. See [morphology notes](NEURAL_MORPHOLOGY.md).

The brain-region fiber colors use MaleCNS `fullbrain-roi-v4` (JRC2018M-derived, manually refined neuropil segmentation), in the same EM coordinate space. Region names come from its segment properties. Display hues are Arena choices; midpoint assignments use 2048 nm voxels. Source: https://storage.googleapis.com/flyem-male-cns/rois/fullbrain-roi-v4/info .

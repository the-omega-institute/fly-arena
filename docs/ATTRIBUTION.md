# Sources and scope

- MaleCNS v1.0: https://male-cns.janelia.org/ and official Janelia Google Cloud release `gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/`. Each downloaded/derived file is recorded in `data/connectome/manifest.json` with its SHA256. Follow the dataset's current citation and reuse terms when redistributing data; this repository does not vendor the dataset.
- FlyGym 2.1.0 / NeuroMechFly body, locomotion demonstration and MuJoCo integration: https://github.com/NeLy-EPFL/flygym . The package and its packaged meshes/controllers retain upstream licenses. The preview uses its simplified anatomical model. The fixed low-level gait is an upstream controller, not a learned fruit fly motor system.
- MuJoCo: https://github.com/google-deepmind/mujoco . Native physics implementation, locked with dependencies in `uv.lock`.
- Eon: used as a research reference for the documented LIF parameter family. No Eon implementation was copied into this repository. `neural.py` is an independent numerical implementation. MaleCNS is a different connectome from Eon's FlyWire setup; their behavior is not assumed equivalent.
- React, Three.js, React Three Fiber, Drei, Lucide, FastAPI, NumPy, SciPy, PyArrow and Numba retain their respective upstream licenses. `uv.lock` and `web/package-lock.json` record versions.

The model assigns ACh a positive sign and GABA/Glu a negative sign, leaving other/unknown signs zero. That is a simplifying modeling policy, not complete transmitter physiology. Anatomical zero-effective connections remain in the graph and manifest.

Current circuit labels identify annotation-derived groups of presynaptic neurons. They do not establish causal behavior labels such as “aggression +15%”. Current sliders therefore name actual circuits and require empirical comparison of behavior. Online learning and imported executable plasticity rules are deliberately absent from this alpha's contract.

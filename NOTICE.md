# Third-party notices

The MIT license in `LICENSE` covers project-authored source code only. The
materials below remain under their own terms. Check the upstream terms before
redistributing a downloaded dataset, model, mesh, font, or dependency.

## MaleCNS

MaleCNS connectome data and neuron centerline skeletons are third-party data
from Janelia and collaborators. The repository documentation identifies the
neuron skeletons and the public MaleCNS data as CC BY 4.0. Follow the current
MaleCNS citation and attribution requirements at
<https://male-cns.janelia.org/download/> and
<https://creativecommons.org/licenses/by/4.0/>. Raw MaleCNS data is not
vendored in this repository; users download it separately under its own terms.

## FlyGym and NeuroMechFly

The FlyGym source repository documents Apache-2.0 for its source code. The
specific FlyGym and NeuroMechFly models, meshes, controllers, and downloaded
assets used through the installed package have not been assigned a separate
license determination in this repository. See the upstream terms at
<https://github.com/NeLy-EPFL/flygym> and the relevant NeuroMechFly source
before redistributing those assets; this notice does not claim a license for
them.

## MuJoCo

MuJoCo is a third-party physics dependency under Apache-2.0. See
<https://github.com/google-deepmind/mujoco/blob/main/LICENSE>.

## Fonts

The web application loads DM Sans and Instrument Serif from Google Fonts.
Those font files are third-party materials under the SIL Open Font License
1.1. See <https://scripts.sil.org/OFL> and the Google Fonts pages for the
applicable font notices.

## Generated examples and research evidence

Files under `web/public/examples/*.png` are project-generated renders of
simulations, not third-party stock images. Their underlying simulated data and
assets remain subject to the separate terms above. Research evidence and replay
files are generated observations of the declared model and are not raw MaleCNS
data or biological recordings.

## Software dependencies

The Python and npm dependencies, including React, Three.js, React Three Fiber,
Drei, Lucide, FastAPI, NumPy, SciPy, PyArrow, Numba, and their transitive
dependencies, retain their own licenses. Version and package records are in
`uv.lock` and `web/package-lock.json`; consult each package's license for
redistribution obligations.

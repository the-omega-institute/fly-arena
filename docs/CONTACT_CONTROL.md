# Separate contact input and motor response experiments

`engineered-contact-context-v1` records food taste separately from left and right environmental touch. The body measures actual mouth–food and anatomical obstacle/opponent contacts. A food source with no remaining resource produces no taste input. Environmental side comes from the contact point in the current thorax frame: local Y above 0.05 mm is left, below −0.05 mm is right, and a center contact is delivered to both sides. Ground support and the invisible mouth probe do not become environmental touch.

The encoder sends an engineered 8 mV current to the annotated gustatory population for taste, and to the annotated left/right mechanosensory tactile populations for the corresponding environmental contact. Unknown anatomical sides are excluded. These are explicit model assumptions, not calibrated biological receptor responses. Historical sensory profiles retain their existing input meanings.

Replay samples include `taste`, `touch_left`, `touch_right`, `contact_environment_sides` and `contact_activity`. The last field contains measured population mean activity for the three groups, with missing groups represented as null. The brain panel displays these values alongside the body and shared time. An active input does not imply that a neuron fired or that the body performed the desired action.

The standard deployment still uses its frozen odor-trained motor readout. A separate research candidate fits a correction to that matrix from full canonical LIF descending activity under controlled odor, taste and lateral touch stimuli. Its targets are stopping during taste and turning away from lateral contact. The candidate has no intercept and receives only descending rates at runtime; contact flags and food coordinates are not decoder inputs. Calibration and embodied evaluation use separate datasets and retain the actual readout identity in each replay receipt.

Current local research artifacts live in `var/research/contact-control/`: mechanics probes, calibration input/output arrays, the separate candidate data directory and matched embodied replay files. `train_readout.py` and `run_embodied.py` there are the executed local experiment scripts. They use an exclusive shared compute lock and do not replace the deployment's canonical readout. The mechanics probe's intake proxy assumes undepleted food and is not a competition score. Read the embodied study results before drawing conclusions about feeding, stability or behavioral improvement.

## Experimental separation of support and lateral touch

`engineered-contact-support-v1` preserves the taste/left/right currents and neuron
selection of `engineered-contact-context-v1`, but partitions actual MuJoCo contact
points before forming lateral touch. A terrain contact counts as support only
when the contacted fly geom is tarsal, the contact is below the thorax, and the
normal pointing toward the fly has world-up component at least `sqrt(0.5)`.
Side, underside, non-tarsal and opponent contacts remain in lateral touch.

`contact_environment` continues to record all environmental targets.
`contact_support` records targets with qualifying support points, while
`contact_environment_sides` records the remaining points by body side. A target
may appear in both: one foot can be supported while another is trapped. Physics,
controller contact forces, food accounting and canonical brain weights are not
changed by this profile. This is an engineered partition, not a biological model
of proprioception or evidence of improved behavior.

The prior Nectar enclosure observation contains tarsal contacts with a 0.2 mm
leaf slab, including nearest-surface normals on its underside. A test that assumed
every contact with that leaf was normal support was invalid. Physical checks use
a thick platform to isolate upward support and a separate thin-slab fixture to
retain underside contact. The matched 10 s candidate keeps genome, motor readout,
map and seed fixed. Its completed replay and outcome belong in the research log;
no stability claim follows from the input change alone.

# Behavior playground (v0.7.7)

Two additional physical arenas are available to matches and evolution:

- **Canopy Crossroads** (`canopy`): mirrored starting positions, a raised leaf bridge with gentle ramps, ground detours, eleven physical obstacles and five shared food patches (four units each). The central food is on the bridge at 0.95 mm.
- **Husk Switchbacks** (`switchback`): staggered walls, rock and fruit obstacles, six limited food patches (two units each). This creates opportunities to compare obstacle contact, route choice and switching targets after depletion.
- **WT Blank Control** (`blank`): one fly, no food or obstacles, for baseline observation rather than competitive scoring.

Map previews and MuJoCo use the same seeded geometry. Visual food rays respect occlusion; the analytic odor field still passes through walls. The maps make more complex behavior possible, but do not establish that a particular controller has learned planning, navigation or memory. The recorded motion, feeding, contact and failures remain the evidence.

## Neural observations

New recordings include the 232 pinned MaleCNS neurons whose real skeletons are available in the anatomical viewer, plus any existing circuit samples. Every sample also includes mean activity, count above 1 Hz, and count above 400 Hz across the full retained network. These statistics are not spatial brain-region means. Old recordings retain their original coverage; missing activity is never synthesized.

`python scripts/wt_stimulus_controls.py --data DATA --output NEW_DIRECTORY` runs five independently reset WT brains: no input, left odor, taste, left touch and left vision. Inputs are enabled from 0.5 to 1.5 seconds of a two-second experiment. They use the full 165,122-neuron graph with the existing LIF and engineered sensory model. This is an open-loop neural experiment without a body, not a fitness evaluation. Install `summary.json` at `ARENA_VAR/research/wt-controls-v1/summary.json` to expose the comparison panel; `controls.json` retains the individual neuron samples.

In the first recorded controls, no input produced zero activity. At 1.5 s the odor condition had 106 neurons above 400 Hz, falling to 91 at 2 s after input removal. Taste and touch had no neurons above 400 Hz at those samples. The isolated visual pulse did not elicit spikes under the current model; this is a measured null result, not evidence that visual behavior is validated. These controls motivate further sensory-gain and network-dynamics experiments rather than cosmetic suppression of tonic activity.

## Compute and queue

Browser playback and 3D previews do not require the GPU worker. Current production neural simulation uses CPU/Numba with MuJoCo; offline images can use the GPU worker. Interactive matches precede recent evolution evaluations, while jobs waiting at least ten minutes return to oldest-first priority. Research jobs and matches alternate when both are waiting. Running jobs finish without preemption.

The queue displays current match position and approximate time based on the last 30 verified completions, including their queue wait. This is a conservative historical estimate, not a deadline. Without samples, or when research work may intervene, the wait is unknown. The local worker remains serial; this change does not add a distributed scheduler.

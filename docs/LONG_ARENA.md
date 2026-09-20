# Long arena observations

The browser can submit a single match for 2, 5, 10, 20, 30, 60, 180 or 300 simulated seconds. The API accepts integer horizons from 1 to 300 seconds. These are observation windows, not computation deadlines. A long run may take substantially longer than real time. Tournament and training episode budgets remain at their existing limits.

## Tasks

- **Labyrinth Benchmark** (`labyrinth`, `forage`, one fly): solid perimeter, alternating corridors and side dead ends. The goal is the single food source. Arrival is the first recorded actual mouth contact with that food, at the 100 Hz sensory clock. The metric is `null` if the goal was not reached; it is never a fabricated zero-time completion. Recording continues to the selected horizon after arrival. Path length is measured from sampled three-dimensional thorax positions. The ground trail projects those positions into XY.
- **Closed Contact Arena** (`duel`, `duel`, two flies): both bodies share one MuJoCo world. Physical contact is counted at the 0.1 ms physics step. The central cylinder has a 3 mm radius and a 3 mm maximum thorax height. Every 50 ms, a fly earns 0.05 points if it alone occupies that region. Simultaneous occupancy earns neither fly points. The judge reconstructs this score from recorded positions; equal totals are a draw. The window does not stop on first contact or territory change.

These two new layouts disable the game-energy motor cutoff, explicitly recorded as `unlimited-observation-v1`. This lets a five-minute observation study neural and physical behavior without an arbitrary reserve timer stopping locomotion. It is not a metabolism model. Historical maps and their energy rules are unchanged.

The labyrinth uses a broader analytic Gaussian odor field (sigma 18 mm) so the distant source can stimulate the baseline fly at its start. As in existing tasks, this field passes through walls; visual rays and physical contacts use actual geometry. The duel uses the opponent as an engineered odor source, with anatomical contact sent to the selected touch encoder. This is an engineered stimulus, not a calibrated fly pheromone model.

## What is and is not simulated

The LIF brain uses the retained MaleCNS structural connectome (165,122 neurons, 25,563,197 connections). Sensory encoding and the bilateral neural-to-locomotion decoder are engineered. Neural and physical integration remain at 0.1 ms, with sensorimotor exchange every 10 ms. The body has locomotion and collision responses; it does **not** yet have dedicated lunging, grappling, injury or other aggression actuators. The contact arena is therefore a pushing/territory benchmark, not validated biological fighting.

There is no scripted maze solver, waypoint following, wall teleportation, target-seeking override or neural reset to make a replay look successful. Collisions, circling, stalling, falls and failure to reach the target are legitimate observations. The fixed 232 morphological neurons displayed in the browser are a labelled activity sample; the simulation still integrates the full graph. The display is not whole-brain voltage imaging.

## Long replay format

Runs of at most 30 seconds retain `pose-100hz-events-20hz-v1`. Longer runs use `pose-20hz-events-20hz-v1`: 20 Hz body poses and neural activity, with the original event clocks. The scene and receipt identify the selected policy; the runtime declares supported policies. The duplicate legacy `top_nodes` alias is omitted from long runs; `sampled_nodes` contains the actual activity records. Historical policies remain readable.

At 180 seconds this produces 3,601 observation frames, including the initial and final states. At 300 seconds it produces 6,001. This reduces storage and browser memory without skipping neural integration or stretching a shorter simulation. Brain values are recorded samples; only body geometry is interpolated between poses. Contact onsets retain their physics ticks even when they fall between observation frames.

## Browser workflow

Save or select a fly → Arena → Labyrinth Benchmark or Closed Contact Arena → select opponent only for the duel → select 180 or 300 seconds → Run my simulation. The result includes task metrics, ground trails, a shared body/brain timeline and direct one-minute seek buttons. Use body-contact events to compare brain samples before and after actual interactions. Replay speed supports 0.5×, 1×, 2×, 5× and 10× and does not alter the recorded simulation clock.

# Selectable brain dynamics and response-gradient training

In Studio, choose **LIF** or **Continuous rate · experimental**, edit weights, then save. The model belongs to the fly's immutable birth design. A model change can retain the original parent as design ancestry; it does not inherit neural state. Each training session retains its founder model, so changing models requires a new session. Competition supports mixed models; the research-v2/Lab bridge remains LIF-only.

Both models use all retained MaleCNS neurons and edges, the same anatomical sign policy, multiplier budget, odor input, body and physics. LIF models discrete spikes, refractoriness and synaptic delays. The continuous model uses:

```
I = external + 0.005 Wᵀ r
r_target = 250 tanh(max(I - (7 + threshold_shift), 0) / 20)
r_next = exp(-1 / (20 tau_scale)) r + (1 - exp(-1 / (20 tau_scale))) r_target
```

Here `r` is a modeled rate in Hz; the neural step is 1 ms, synchronized to the existing 0.1 ms physics clock. There are no discrete spike counts, refractory periods, synaptic delays or within-match plasticity in this model. Receipts report its model profile and a null spike count. It transfers the existing frozen LIF descending readout without recalibration; both UI and profile identify this as experimental. Alternative dynamics are a research choice, not a claim of superior biological fidelity.

## Optimize weights

Evolution, random search and CEM work directly with either brain. For gradient training, `examples/optimizers/rate_adam.py` implements backpropagation through the full sparse rate network and Adam updates of three outgoing circuit multipliers (olfactory, projection, descending). It uses NumPy/SciPy on the user's device, requiring the prepared public graph and frozen readout; no additional ML framework is required. Arbitrary code is never loaded on the Arena server.

The teaching objective is mean squared error between a final motor response and the declared bilateral odor-response target used by the engineering decoder. Two stimuli, `(0.8,0.2)` and `(0.2,0.8)`, are the default. It is **not a differentiable physics reward**, PPO, online learning or proof of better foraging. The API evaluates exported candidates in real embodied matches, with their actual scores retained even if worse. A differentiable neural network and a differentiable environment are separate capabilities.

Create a custom optimizer session in the browser using a continuous-rate founder and a small explicit budget. With Arena installed in your local Python environment and `ARENA_URL`/`ARENA_TOKEN` set, create `rate-config.json`:

```json
{"data":"/absolute/path/to/data","output":"var/rate-training","updates":3,"steps":100,"learning_rate":0.02}
```

Then run:

```sh
python scripts/custom_strategy.py --run SESSION_ID \
  --plugin examples/optimizers/rate_adam.py --config rate-config.json
```

The client caches each proposal before submitting it. The trainer writes its teaching stimuli, update settings, full graph counts, losses, gradients and parameter trajectory to the configured output directory. Final changes are projected toward the parent if required by the authoritative compiler's budget. Recorded teaching losses describe the pre-projection trajectory; the returned FlySpec is the proposal actually evaluated. The first session slot remains the server baseline; later generations retain the best evaluated parent in slot 0.

## Compare and inspect

The unmodified continuous-rate reference is named **Rate baseline / 连续模型基线**. The standard WT shortcut selects the matching model/graph; an explicit Arena opponent selector permits rate-vs-LIF experiments. Strategy comparisons list the brain model and flag model differences. Life records and replay preserve the birth model, weights, final state, behavior and population activity. Historical LIF evidence and artifact identities remain readable.

Tests compare the reverse-mode gradient with central finite differences, verify optimizer loss reduction on an explicit tiny teaching fixture, exercise rate checkpoint/chunk behavior, and run both models in the same actual MuJoCo body simulation. Full-graph demonstrations are separate recorded experiments, not fixture evidence.

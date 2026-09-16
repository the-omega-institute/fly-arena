"""Deterministic addendum report producer for behavior-v12 correction."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flyarena.common import file_sha, write_json


PROFILE = "source-native-excursion-v12"


def _failed_swings(analysis: dict) -> dict[str, int]:
    counts = {leg: 0 for leg in ("LF", "LM", "LH", "RF", "RM", "RH")}
    for trial in analysis["trials"].values():
        if trial["conditions"]["profile"] != PROFILE or trial["conditions"]["case"][1] <= 0:
            continue
        for leg, cycles in zip(counts, trial["swing_cycles"]):
            counts[leg] += sum(cycle["status"] != "pass" for cycle in cycles)
    return counts


def produce(analysis_root: Path, plot_receipt_path: Path, tests_path: Path, output: Path, receipt: Path) -> dict:
    registration_path = analysis_root / "registration.json"
    analysis_path = analysis_root / "analysis.json"
    verification_path = analysis_root / "independent-verification.json"
    resources_path = analysis_root / "resource-receipt.json"
    fixture_path = analysis_root / "paired-native-fixture.json"
    registration = json.loads(registration_path.read_text())
    analysis = json.loads(analysis_path.read_text())
    verification = json.loads(verification_path.read_text())
    resources = json.loads(resources_path.read_text())
    fixture = json.loads(fixture_path.read_text())
    plot_receipt = json.loads(plot_receipt_path.read_text())
    tests = json.loads(tests_path.read_text())
    if not verification["passed"] or analysis["status"] != "complete":
        raise ValueError("report requires complete independently verified analysis")
    failures = _failed_swings(analysis)
    maxima = analysis["paired_state_maxima"]
    lines = [
        "# Behavior v12 paired-state correction addendum",
        "",
        "Verdict: the observer/arithmetic/provenance correction is implemented and independently verified, "
        "but the retained candidate does not pass the operational walking gates. This is a separately versioned "
        "read-only analysis, not a retroactive regrade of the historical v12 run. Held-out seeds, neural15, "
        "Wild Type/official/user phenotypes, ablations, Lab/API/replay, and product admission remain unrun and blocked.",
        "",
        "## Corrected phase ownership",
        "",
        "For every `k>=1`, raw contact/frame/wrench row `k` owns interval `((k-1)dt,kdt]`. Its cached "
        "geometry belongs to `core[k-1].qpos`. Coherent material velocity for the registered slip calculation "
        "is `J(core[k-1].qpos) @ core[k-1].qvel`; the historically saved velocity is retained only as the "
        "explicitly labeled hybrid diagnostic `J(core[k-1].qpos) @ core[k].qvel`. Physical endpoint pose and "
        "AP come from `core[k].qpos`; endpoint `k` independently matches next cache row `k+1` where that row exists. "
        "Tick zero is initialization and contributes no force or slip quadrature.",
        "",
        f"All reconstruction arithmetic casts frozen mesh vertices to float64 before the mean. The unchanged "
        f"strict tolerance is `{registration['numeric_contract']['strict_max_abs_tolerance']}`. Across all 32 trials, "
        f"cache-to-start geometry error was `{maxima['cache_vs_state_start_max_abs_mm']}` mm, endpoint-to-next-cache "
        f"error was `{maxima['endpoint_vs_next_cache_max_abs_mm']}` mm, saved-hybrid velocity error was "
        f"`{maxima['saved_hybrid_velocity_max_abs_mm_s']}` mm/s, and independent pre-state object/Jacobian error was "
        f"`{maxima['pre_object_velocity_vs_jacobian_max_abs_mm_s']}` mm/s.",
        "",
        "The earlier report's claim that the approximately `6e-9 mm` residual was an MJB serialization floor was "
        "unsupported and is superseded by this addendum. Frozen compiled arrays and the MJB-loaded arrays match "
        "exactly. The nonzero residual came from averaging float32 mesh vertices before conversion to float64, "
        "while the recorder converted before averaging. The historical report, figure, raw streams, failed decision, "
        "registration, source archive, and index remain byte-identical.",
        "",
        "## Retained-data result",
        "",
        f"The correction derived `{analysis['retained_trial_count']}/32` trials and `{analysis['raw_contact_rows']}` raw "
        f"contact rows. Whole-index closure checked 12,338 files and 3,217,398,285 bytes. Invalid interior phase "
        f"episodes: `{analysis['invalid_interior_phase_episodes']}`; legitimate analysis-window boundary partials remain "
        "separately recorded per leg and trial. Every derived trial retains unfiltered endpoint AP, whole-foot clearance, "
        "owned interval force, pre-state slip numerator, source row identities, ties, reversals, partials, and failures.",
        "",
        f"Candidate operational result: `{'pass' if analysis['candidate_operational_gates_passed'] else 'fail'}`. "
        f"Failed complete candidate swings by leg across nonzero development conditions were: "
        + ", ".join(f"{leg} `{count}`" for leg, count in failures.items()) + ". "
        "These are operational gate results under the unchanged policy. In particular, an inside leg remaining loaded "
        "during a strong turn can describe an anchored/pivoting strategy; the turn gate is not by itself a biological "
        "naturalness claim. Straight-condition hind-foot failures are independent of that interpretive ambiguity.",
        "",
        "![Phase-correct retained-data result](evidence/behavior-v12-correction.png)",
        "",
        "## Verification and boundaries",
        "",
        f"The detached paired-state fixture used `{fixture['integrations']}` integrations and "
        f"`{fixture['physical_seconds']}` physical seconds. It proved start-cache ownership, pre-state velocity, "
        "detection of wrong same-row and hybrid pairings, positive loaded contact, and bitwise trajectory/cache "
        "noninterference. The strengthened restoration receipt joined expected and replayed ticks 10001..10100 "
        "exactly to the corresponding retained core, dense, and contact rows; identity substitutions reject before "
        "comparison and the verifier has no live state to mutate.",
        "",
        f"Independent verification sampled `{sum(t['sampled_endpoint_rows'] for t in verification['trials'].values())}` "
        f"endpoint reconstructions and `{sum(t['sampled_contact_velocities'] for t in verification['trials'].values())}` "
        f"pre-state contact velocities, while closing all normal forces directly from raw contacts. It passed at the "
        f"same `{verification['tolerance']}` tolerance. Tests: `{tests['passed']}` passed, `{tests['failed']}` failed, "
        f"with JUnit SHA-256 `{tests['junit_sha256']}`.",
        "",
        f"Analysis resources: `{resources['analysis_wall_seconds']}` s wall, "
        f"`{resources['analysis_user_cpu_seconds']}` s user CPU, `{resources['analysis_system_cpu_seconds']}` s system CPU, "
        f"`{resources['peak_rss_bytes']}` bytes peak RSS, and `{resources['new_output_bytes_at_analysis']}` bytes of new "
        "registered output at analysis completion. One CPU worker, no network, no long physics, no full-network run. "
        f"Total tiny-fixture physics across the recorded implementation commands was `{tests['total_tiny_physics_seconds']}` s.",
        "",
        "The existing `ArtifactRepository`, `ResearchRepository`, `IdentityProvider`, `ExperimentExecutor`, "
        "`LocalProbeExecutor`, `ConditionSpec`, and `PhenotypeReport` ports remain unchanged. No new platform surface "
        "or candidate exposure was introduced. The remaining goal gap is actual qualified walking followed by the "
        "unchanged held-out, neural15, same-condition WT/official/user phenotype, ablation, and product path.",
        "",
        "## Receipts",
        "",
        f"- Correction registration SHA-256: `{file_sha(registration_path)}`",
        f"- Analysis SHA-256: `{file_sha(analysis_path)}`",
        f"- Independent verification SHA-256: `{file_sha(verification_path)}`",
        f"- Raw closure SHA-256: `{file_sha(analysis_root / 'raw-closure.json')}`",
        f"- Plot SHA-256: `{plot_receipt['png_sha256']}`",
        f"- Plot producer SHA-256: `{plot_receipt['producer_sha256']}`",
        f"- Original immutable evidence index SHA-256: `{registration['original_evidence_index_sha256']}`",
        f"- Original durable archive SHA-256 binding: `{registration['original_archive_sha256']}`",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    output.write_text("\n".join(lines), encoding="ascii")
    result = {
        "schema": "behavior-v12-correction-report-receipt/v1",
        "inputs": {
            "registration": file_sha(registration_path),
            "analysis": file_sha(analysis_path),
            "independent_verification": file_sha(verification_path),
            "resources": file_sha(resources_path),
            "fixture": file_sha(fixture_path),
            "plot_receipt": file_sha(plot_receipt_path),
            "tests": file_sha(tests_path),
        },
        "producer": str(Path(__file__).resolve()),
        "producer_sha256": file_sha(Path(__file__).resolve()),
        "output": str(output.resolve()),
        "report_sha256": file_sha(output),
        "supersedes_interpretation": "unsupported MJB-floor explanation; historical report remains immutable",
        "scientific_admission": False,
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if receipt.exists():
        raise FileExistsError(receipt)
    write_json(receipt, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-root", type=Path, required=True)
    parser.add_argument("--plot-receipt", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = produce(
        args.analysis_root.resolve(), args.plot_receipt.resolve(), args.tests.resolve(),
        args.output.resolve(), args.receipt.resolve(),
    )
    print(json.dumps({"report_sha256": result["report_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()

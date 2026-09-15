from __future__ import annotations

import sys
import traceback

from .common import digest
from .contracts import MatchRequest
from .judge import verify
from .runner import runtime_manifest, simulate
from .store import Store


def main():
    ident, lease, generation = sys.argv[1:4]
    store = Store()
    try:
        match = store.match(ident)
        if match["runtime_hash"] != digest(runtime_manifest()):
            raise ValueError("Runtime changed after admission; create a match under the current season")
        if match["attempt"] != int(generation):
            raise ValueError("Attempt generation changed")
        request = MatchRequest.model_validate(match["request"])
        flies = [store.fly(i) for i in request.fly_ids]
        if [f["artifact_id"] for f in flies] != match["artifacts"]:
            raise ValueError("Contestants changed after admission")
        folder = store.result_folder(match)
        store.heartbeat(ident, lease, 0)
        simulate(request, flies, folder, lambda p: store.heartbeat(ident, lease, p))
        verdict = verify(folder, expected_request=match["request"], expected_artifacts=match["artifacts"], expected_runtime_hash=match["runtime_hash"])
        store.finish(ident, lease, verdict)
    except BaseException as error:
        traceback.print_exc()
        try:
            store.finish(ident, lease, None, f"{type(error).__name__}: {error}")
        except RuntimeError:
            pass  # A fenced worker has no authority to change the current attempt.
        raise


if __name__ == "__main__":
    main()

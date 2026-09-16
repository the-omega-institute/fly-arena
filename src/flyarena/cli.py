from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import DATA


def main():
    parser = argparse.ArgumentParser(prog="arena")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="Download and import official MaleCNS, then calibrate the shared readout")
    server = sub.add_parser("serve", help="Start the API, web app, and one durable worker")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8080)
    server.add_argument("--no-worker", action="store_true")
    sub.add_parser("seed", help="Publish the canonical fly and two starter designs")
    validate = sub.add_parser("validate", help="Validate a FlySpec JSON file")
    validate.add_argument("file", type=Path)
    verify = sub.add_parser("verify", help="Verify a completed run's evidence")
    verify.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        from .connectome import download, import_connectome
        from .calibrate import calibrate
        download()
        if not (DATA / "connectome/manifest.json").exists():
            import_connectome()
        if not (DATA / "connectome/readout.json").exists():
            calibrate()
    elif args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(with_worker=not args.no_worker), host=args.host, port=args.port, access_log=False)
    elif args.command == "seed":
        from .connectome import Connectome
        from .compiler import Compiler
        from .contracts import FlySpec
        from .store import Store
        g, store = Connectome(), Store()
        c = Compiler(g)
        from .registry.platform_references import initialize_references
        for role, fly in initialize_references(store,c).items():
            print(f"Published trusted {role}: {fly['id']}")
        # Preserve the third starter without assigning it reference authority.
        spec = FlySpec(name="Moss / 苔原",color="violet",connectome_sha256=g.manifest['sha256'],
                       weight_mutations=[{'selector':'descending','scale':1.25},{'selector':'local','scale':1.12}])
        report = c.compile(spec,publish=True,root=store.root)
        if not any(f['owner']=='arena' and f['artifact_id']==report['artifact_id'] and f['spec'].get('weight_mutations')==spec.model_dump()['weight_mutations'] for f in store.flies()):
            print(f"Published starter: {store.add_fly('arena',spec.model_dump(),report)['id']}")
    elif args.command == "validate":
        from .connectome import Connectome
        from .compiler import Compiler
        from .contracts import FlySpec
        result = Compiler(Connectome()).compile(FlySpec.model_validate_json(args.file.read_text()))
        print(json.dumps(result, indent=2))
    elif args.command == "verify":
        from .judge import verify
        print(json.dumps(verify(args.directory), indent=2))


if __name__ == "__main__":
    main()

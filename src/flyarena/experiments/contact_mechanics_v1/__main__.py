"""One explicit CLI; scientific commands require exclusive preregistration anchors."""
import argparse,json,os

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('source-check','preregister','preflight','run','analyze','verify'))
    parser.add_argument('--root');parser.add_argument('--anchor')
    args=parser.parse_args()
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
    if args.operation=='source-check':
        from .registration import source_check
        result=source_check()
    elif args.operation=='preregister':
        if not args.root:parser.error('--root required')
        from .registration import preregister
        result=preregister(args.root)
    elif args.operation in ('preflight','run'):
        if not args.root or not args.anchor:parser.error('--root and literal --anchor required')
        from .runtime import preflight,run
        result=(preflight if args.operation=='preflight' else run)(args.root,args.anchor)
    else:
        if not args.root:parser.error('--root required')
        from .verify import independent_saved_review
        # Runtime performed the registered single shared geometry/action traversal.
        # Standalone read-only commands check its retained closure, never schedule
        # an unauthorized second native pass or silently rerun a failed trial.
        result=independent_saved_review(args.root)
    print(json.dumps(result,sort_keys=True,allow_nan=False))
if __name__=='__main__':main()

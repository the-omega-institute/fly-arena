"""Install project-local launchd definitions for this Mac's logged-in user."""
import os
import argparse
from pathlib import Path
import plistlib
import re
import subprocess

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--public-tunnel',action='store_true',help='Requires explicit public exposure approval')
    args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[1]
    label_prefix=os.environ.get('ARENA_LAUNCHD_LABEL_PREFIX','fly-arena').strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', label_prefix):
        parser.error('ARENA_LAUNCHD_LABEL_PREFIX must be a safe launchd label prefix')
    (root/'var/log').mkdir(parents=True,exist_ok=True)
    app_label=f'{label_prefix}-app'
    tunnel_label=f'{label_prefix}-tunnel'
    services={
     app_label:[str(root/'.venv/bin/arena'),'serve','--host','127.0.0.1','--port','8080'],
     tunnel_label:[str(root/'tools/cloudflared'),'tunnel','--url','http://127.0.0.1:8080','--no-autoupdate','--protocol','http2'],
    }
    if not args.public_tunnel:
        services.pop(tunnel_label)
    domain=f'gui/{os.getuid()}'
    for label,args in services.items():
        path=root/'deploy'/f'{label}.plist'
        path.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':args,'WorkingDirectory':str(root),
          'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':10,
          'EnvironmentVariables':{'PATH':str(root/'.venv/bin')+':/usr/bin:/bin:/usr/sbin:/sbin','PYTHONUNBUFFERED':'1'},
          'StandardOutPath':str(root/'var/log'/f'{label}.out.log'),
          'StandardErrorPath':str(root/'var/log'/f'{label}.err.log')}))
        current=subprocess.run(['launchctl','print',domain+'/'+label],capture_output=True)
        if current.returncode==0:
            print(label,'already loaded; leave running')
        else:
            subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
            print(label,'bootstrapped')


if __name__ == '__main__':
    main()

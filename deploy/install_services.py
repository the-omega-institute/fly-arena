"""Install project-local launchd definitions for this Mac's logged-in user."""
import os
import argparse
from pathlib import Path
import plistlib
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--public-tunnel',action='store_true',help='Requires explicit public exposure approval')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
(root/'var/log').mkdir(parents=True,exist_ok=True)
services={
 'institute.omega.fly-arena-alpha':[str(root/'.venv/bin/arena'),'serve','--host','127.0.0.1','--port','8080'],
 'institute.omega.fly-arena-tunnel':[str(root/'tools/cloudflared'),'tunnel','--url','http://127.0.0.1:8080','--no-autoupdate','--protocol','http2'],
}
if not args.public_tunnel:
    services.pop('institute.omega.fly-arena-tunnel')
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

#!/usr/bin/env python3
"""Plot recorded pilot/final approach and feeding evidence without simulation."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
import numpy as np
from flyarena.common import write_json, file_sha
from flyarena.experiments.probes import verify_evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root
    paths = sorted(root.glob('*/report.json'))
    paths = [p for p in paths if p.parent.name not in ['blank','output-ablation','delayed-cue','heldout-repeat']]
    fig, axes = plt.subplots(len(paths), 3, figsize=(15, 3.5*len(paths)), squeeze=False, layout='constrained')
    receipts = {}
    for (map_ax, drive_ax, food_ax), path in zip(axes, paths):
        r = json.loads(path.read_text())
        verify_evidence(path.parent, r)
        receipts[path.parent.name] = r['receipt_sha256']
        t = np.array([p['time'] for p in r['trajectory']])
        xy = np.array([[p['x'],p['y']] for p in r['trajectory']])
        goal = np.array(r['scene']['food'][0]['position'][:2])
        for obstacle in r['scene']['obstacles']:
            x,y,_ = obstacle['position']; w,h,_ = obstacle['size']
            map_ax.add_patch(Rectangle((x-w/2,y-h/2),w,h,color='#8895a1',alpha=.35))
        map_ax.plot(xy[:,0],xy[:,1],color='#2465a3')
        map_ax.scatter(*xy[0], marker='o', color='#16815d', label='Start')
        map_ax.scatter(*xy[-1], marker='x', color='#b23a39', label='End')
        map_ax.scatter(*goal,marker='*',color='#c4860a',s=100,label='Food')
        map_ax.add_patch(Circle(goal,1.1,fill=False,color='#c4860a',ls=':',label='Mouth intake radius'))
        map_ax.set(aspect='equal',xlabel='x (mm)',ylabel='y (mm)',title=f"{path.parent.name} | seed {r['seed']}")
        map_ax.legend(fontsize=7)
        command = np.array([[p['command_left'],p['command_right']] for p in r['neural_trace']])
        state = np.zeros(2); common = []
        for pair in command:
            state = .9*state+.1*pair; common.append(state.mean())
        drive = np.array([[p['drive_left'],p['drive_right']] for p in r['neural_trace']])
        drive_ax.plot(t,common,label='Filtered neural common',color='#8757a8')
        drive_ax.plot(t,drive.mean(axis=1),label='Physical common drive',color='#2465a3')
        drive_ax.set(xlabel='Time (s)',ylabel='Drive',title='Recorded neural signal and motor output')
        drive_ax.legend(fontsize=8)
        distance = np.linalg.norm(xy-goal,axis=1)
        food_ax.plot(t,distance,color='#2465a3',label='Thorax distance')
        food_ax.set(xlabel='Time (s)',ylabel='Thorax–food distance (mm)',title=f"Intake {r['metrics']['food_intake']:.2f}; closest {distance.min():.2f} mm")
        intake_ax = food_ax.twinx()
        intake_ax.plot(t,[p['food_intake'] for p in r['neural_trace']],color='#16815d',label='Cumulative intake')
        intake_ax.set(ylabel='Cumulative food intake',ylim=(0,10.5))
        food_ax.legend(loc='upper left',fontsize=8); intake_ax.legend(loc='upper right',fontsize=8)
        for ax in [map_ax,drive_ax,food_ax]: ax.grid(alpha=.2)
    fig.suptitle('Measured neural-only v4 motor approach; mouth criterion and task geometry unchanged',fontsize=14)
    target=root/'motor-approach.png'
    fig.savefig(target,dpi=145,bbox_inches='tight');plt.close(fig)
    write_json(root/'motor-plot.json',{'figure_sha256':file_sha(target),'script_sha256':file_sha(Path(__file__)),
        'receipts':receipts,'note':'Thorax position is plotted; actual feeding requires the unchanged mouth criterion. Development is not qualification.'})


if __name__ == '__main__':
    main()

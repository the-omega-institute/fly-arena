"""Headless scientific stills from recorded meshes, poses and neural samples.

CPU Matplotlib/Agg rendering; no OpenGL, physics stepping or invented activity.
Example: python scripts/render_observation.py --replay RUN --times .67 1.8 --output observation.png
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import mujoco as mj
import numpy as np


def rotation(q):
    q=np.asarray(q,dtype=float)
    if q.shape!=(4,) or not np.isfinite(q).all() or np.linalg.norm(q)==0:
        raise ValueError('Invalid recorded quaternion')
    out=np.empty(9);mj.mju_quat2Mat(out,q/np.linalg.norm(q));return out.reshape(3,3)


def collection(ax, triangles, color):
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    lengths=np.linalg.norm(normal,axis=1)
    normal/=np.maximum(lengths[:,None],1e-12)
    light=np.array([-.3,-.5,1.]);light/=np.linalg.norm(light)
    shade=.35+.65*np.maximum(0,normal@light)
    rgba=np.column_stack([np.clip(np.asarray(color)[None,:]*shade[:,None],0,1),np.ones(len(shade))])
    # Sort all triangles together: separate collections can paint the whole
    # floor over the fly despite correct world-space heights.
    ax.arena_triangles.append(triangles)
    ax.arena_colors.append(rgba)


def render(replay, times, output, slot=0):
    scene=json.loads((replay/'scene.json').read_text())
    frames=json.loads((replay/'frames.json').read_text())
    stamps=np.array([f['time'] for f in frames])
    if len(stamps)<2 or np.any(np.diff(stamps)<=0):raise ValueError('Expected ordered recorded frames')
    if not 0<=slot<len(scene['flies']):raise ValueError('Invalid participant')
    if any(not np.isfinite(t) or not stamps[0]<=t<=stamps[-1] for t in times):raise ValueError('Requested time outside recording')
    chosen=[int(np.searchsorted(stamps,t,side='right')-1) for t in times]
    meshes={k:(np.asarray(v['vertices']).reshape(-1,3),np.asarray(v['faces']).reshape(-1,3)) for k,v in scene['body']['meshes'].items()}
    geoms=scene['body']['geoms']
    thorax=next(i for i,g in enumerate(geoms) if g['slot']==slot and g['name'].endswith('/c_thorax'))
    initial=rotation(frames[0]['poses'][thorax][3:])
    up=np.array([(rotation(f['poses'][thorax][3:])@initial.T)[2,2] for f in frames])
    tilt=np.degrees(np.arccos(np.clip(up,-1,1)))
    plt.rcParams.update({'text.color':'#e9efe8','axes.labelcolor':'#b7c9c1','xtick.color':'#b7c9c1','ytick.color':'#b7c9c1','axes.edgecolor':'#496159','font.size':10,'savefig.facecolor':'#101e20'})
    fig=plt.figure(figsize=(14,9),facecolor='#101e20')
    grid=fig.add_gridspec(3,len(chosen),height_ratios=[3.1,1,1],hspace=.35)
    fig.suptitle(f"FLY ARENA  /  {scene['flies'][slot]['name'].split(' / ')[0]}\nRecorded body and neural activity",x=.06,ha='left',fontsize=20)
    for column,index in enumerate(chosen):
        f=frames[index]
        if len(f['poses'])!=len(geoms):raise ValueError('Pose/mesh manifest mismatch')
        ax=fig.add_subplot(grid[0,column],projection='3d',facecolor='#101e20')
        ax.arena_triangles=[];ax.arena_colors=[]
        center=np.asarray(f['positions'][slot]);radius=3.3
        for g,pose in zip(geoms,f['poses'],strict=True):
            if g['slot']!=slot:continue
            vertices,faces=meshes[g['mesh']]
            transformed=vertices@rotation(pose[3:]).T+np.asarray(pose[:3])
            color=[.57,.86,.69] if 'wing' not in g['name'] else [.62,.75,.79]
            collection(ax,transformed[faces],color)
        # Actual floor height and food radius; no decorative body animation.
        x,y=center[:2]
        ground=np.array([[x-radius,y-radius,0],[x+radius,y-radius,0],[x+radius,y+radius,0],[x-radius,y+radius,0]])
        collection(ax,ground[[[0,1,2],[0,2,3]]],[.18,.28,.27])
        # Boxes retain their recorded world position, dimensions and rotation.
        signs=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]])
        box_faces=np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
        for obstacle in scene['obstacles']:
            size=np.array(obstacle['size']);pos=np.array(obstacle['position'])
            if np.linalg.norm(pos[:2]-center[:2])>radius+np.linalg.norm(size[:2])/2:continue
            if obstacle.get('shape','box')=='ellipsoid':
                u,v=np.meshgrid(np.linspace(0,2*np.pi,25),np.linspace(0,np.pi,13))
                vertices=np.stack([np.cos(u)*np.sin(v),np.sin(u)*np.sin(v),np.cos(v)],axis=-1).reshape(-1,3)*size/2
                faces=np.array([[row*25+col,row*25+col+1,(row+1)*25+col+1] for row in range(12) for col in range(24)]+[[row*25+col,(row+1)*25+col+1,(row+1)*25+col] for row in range(12) for col in range(24)])
            else:
                vertices=signs*size/2;faces=box_faces
            vertices=vertices@rotation(obstacle.get('quaternion',[1,0,0,0])).T+pos
            collection(ax,vertices[faces],[.54,.50,.40])
        for food,left in zip(scene['food'],f['food'],strict=True):
            pos=np.asarray(food['position'])
            if left<=0 or np.linalg.norm(pos[:2]-center[:2])>radius:continue
            u,v=np.meshgrid(np.linspace(0,2*np.pi,24),np.linspace(0,np.pi,12))
            vertices=np.stack([np.cos(u)*np.sin(v),np.sin(u)*np.sin(v),np.cos(v)],axis=-1).reshape(-1,3)*.45+pos
            faces=np.array([[row*24+col,row*24+col+1,(row+1)*24+col+1] for row in range(11) for col in range(23)]+[[row*24+col,(row+1)*24+col+1,(row+1)*24+col] for row in range(11) for col in range(23)])
            collection(ax,vertices[faces],[.93,.72,.36])
        ax.add_collection3d(Poly3DCollection(np.concatenate(ax.arena_triangles),facecolors=np.concatenate(ax.arena_colors),edgecolors='none',rasterized=True))
        ax.set(xlim=(x-radius,x+radius),ylim=(y-radius,y+radius),zlim=(0,4.5))
        ax.set_box_aspect((6.6,6.6,4.5));ax.view_init(elev=45,azim=float(np.degrees(np.arctan2(-y,-x))));ax.set_axis_off()
        title=f"{f['time']:.2f} s  |  tilt {tilt[index]:.0f} deg"
        ax.set_title(title+'\n'+('Inverted posture' if up[index]<0 else 'Recorded posture'),color='#e9efe8',fontsize=12,pad=2)
    neural=fig.add_subplot(grid[1,:],facecolor='#101e20')
    tactile=[f['senses'][slot].get('tactile_activity',np.nan) for f in frames]
    descending=[f['traces'][slot].get('descending',np.nan) for f in frames]
    if any('contact_activity' in f['senses'][slot] for f in frames):
        for key,label,color in [('taste','Taste population','#efbc64'),('touch_left','Left tactile','#dba8be'),('touch_right','Right tactile','#86b1ed')]:
            values=[f['senses'][slot].get('contact_activity',{}).get(key,np.nan) for f in frames]
            neural.plot(stamps,values,color=color,label=label)
    else:
        neural.plot(stamps,tactile,color='#efbc64',label='Tactile population')
    neural.plot(stamps,descending,color='#6dc5bd',label='Descending population')
    neural.set_ylabel('Mean activity (Hz)');neural.legend(loc='lower right',bbox_to_anchor=(1,1.02),frameon=False,labelcolor='#e9efe8',ncol=4,fontsize=9)
    posture=fig.add_subplot(grid[2,:],facecolor='#101e20',sharex=neural)
    posture.plot(stamps,tilt,color='#dba8be',label='Thorax tilt from initial upright pose')
    posture.axhline(90,color='#82938d',ls='--',lw=.8);posture.set(ylabel='Tilt (degrees)',xlabel='Recorded simulation time (s)',ylim=(0,185),xlim=(stamps[0],stamps[-1]))
    posture.fill_between(stamps,90,180,where=up<0,color='#ad6570',alpha=.18)
    for ax in (neural,posture):
        ax.spines[['top','right']].set_visible(False)
        for i in chosen:ax.axvline(stamps[i],color='#9cab9f',ls=':',lw=.8)
    fig.text(.06,.022,'Actual recorded FlyGym meshes and poses / mm. CPU scientific rendering. Engineered sensory/motor model; no biological equivalence claim.',fontsize=9,color='#9fb4aa')
    fig.subplots_adjust(left=.08,right=.96,bottom=.085,top=.86)
    output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(output,dpi=120);plt.close(fig)
    output.with_suffix('.json').write_text(json.dumps({'source':str(replay),'renderer':'Matplotlib Agg CPU','slot':slot,'requested_times':times,'recorded_times':[float(stamps[i]) for i in chosen],'scope':'Recorded pose stills and neural measurements; not new simulation or browser/GPU acceptance'},indent=2))
    print(output,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--times',type=float,nargs='+',default=[.67,1.8]);p.add_argument('--slot',type=int,default=0);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not 1<=len(a.times)<=3:p.error('Choose one to three recorded times')
    render(a.replay,a.times,a.output,a.slot)


if __name__=='__main__':main()

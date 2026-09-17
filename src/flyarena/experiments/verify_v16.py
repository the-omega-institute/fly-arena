"""Independent retained-data v16 verification; never integrates the plant."""
import json
from pathlib import Path
import numpy as np
import mujoco as mj
from ..common import file_sha, write_json
from .mechanical_v16 import CORE, DENSE, CONTACT, DT, _slices, _width, panel, PROFILE, CONTROL, validate_freeze
from .behavior_v12_correction import ROWS, TOLERANCE, _validate_restoration_digest_sequences
from .verify_behavior_v12_correction import _read_stream, _cycle_gate, _geometry_sample, _jacobian_velocity, _validate_digest_document


def verify_phase_law(core, profile, registration):
    cs = _slices(CORE)
    theta = core[:-1, cs['phases']]
    magnitude = core[:-1, cs['magnitudes']]
    signal = core[1:, cs['input']]
    common = signal.mean(axis=1)
    asymmetry = np.divide(signal[:,1]-signal[:,0], 2*common, out=np.zeros_like(common), where=common>0)
    active = common > 1e-4
    weights=np.asarray(registration['controller']['coupling']);bias=np.asarray(registration['controller']['phase_biases'])
    native=2*np.pi*12+(magnitude[:,None,:]*weights[None,:,:]*np.sin(theta[:,None,:]-theta[:,:,None]-bias[None,:,:])).sum(axis=2)
    if profile not in (CONTROL,PROFILE):raise ValueError('unregistered profile')
    gain=np.zeros_like(theta);gain[active]=(common[active]/.6)[:,None]
    target=np.repeat(np.column_stack((1-asymmetry,1+asymmetry)),3,axis=1)
    expected_theta = theta+DT*gain*native
    expected_magnitude = magnitude.copy()
    expected_magnitude[active] += DT*20*(target[active]-magnitude[active])
    phase_error = float(np.max(np.abs(core[1:,cs['phases']]-expected_theta)))
    amplitude_error = float(np.max(np.abs(core[1:,cs['magnitudes']]-expected_magnitude)))
    if phase_error > TOLERANCE or amplitude_error > TOLERANCE:
        raise ValueError('retained trajectory violates registered pre-update phase/amplitude equation')
    if True:
        for field in ('phases','magnitudes','targets','ctrl','retraction','stumbling','persistence','net_correction','sensed_clearance','trigger_mask','minimum_geom','minimum_vertex','native_template','allocation','allocation_diagnostics','observation_tick','relaxation_diagnostics'):
            if not np.array_equal(core[1:,cs[field]][~active],core[:-1,cs[field]][~active]):
                raise ValueError('v16/v12 silence did not hold controller/action exactly')
    return {'controller_ticks_checked':len(common),'max_phase_equation_error':phase_error,'max_amplitude_equation_error':amplitude_error,
            'active_ticks':int(active.sum()),'uniform_v12_phase_law':True}


def verify_retraction_and_commands(core,profile,registration):
    # Independent equations; never invoke the candidate controller or its trigger helper.
    from flygym_demo.complex_terrain.preprogrammed import PreprogrammedSteps
    from flygym_demo.complex_terrain.common import get_default_locomotion_dof_order,dof_spec_to_jointdof
    cs=_slices(CORE);source=PreprogrammedSteps();order=get_default_locomotion_dof_order()
    active=core[1:,cs['input']].mean(axis=1)>1e-4
    phases=core[:-1,cs['phases']]%(2*np.pi)
    end=np.asarray(registration['controller']['release_end'])
    obs=core[:-1,cs['native_observation']]
    if profile in (PROFILE,CONTROL):
        selected=(phases>0)&(phases<end)&(core[1:,cs['sensed_clearance']]<.05)&active[:,None]
        if not np.array_equal(core[1:,cs['trigger_mask']][active],selected[active]):raise ValueError('new trigger prestate/strict-boundary mismatch')
    else:
        relative=obs[:,0,None]-obs[:,1:7];indices=np.argsort(relative,axis=1)
        values=np.take_along_axis(relative,indices,axis=1)
        selected=np.zeros_like(phases,dtype=bool)
        yes=values[:,-1]>values[:,-3]+.05
        selected[np.nonzero(yes)[0],indices[yes,-1]]=True
    oldr=core[:-1,cs['retraction']];olds=core[:-1,cs['stumbling']]
    persist=core[:-1,cs['persistence']].copy()
    persist[selected & (oldr>20)]=1
    persist[persist>0]+=1;persist[persist>20]=0
    retraction=np.where(selected|(persist>0),oldr+800*DT,np.maximum(0,oldr-700*DT))
    forces=obs[:,7:61].reshape(-1,6,3,3);heading=obs[:,61:64]
    stumble=(np.sum(forces*heading[:,None,None,:],axis=3)<-1).any(axis=2)
    stumbling=np.where(stumble,olds+2200*DT,np.maximum(0,olds-1800*DT))
    stumbling[retraction>0]=0
    raw=np.where(retraction>0,retraction,stumbling)
    postphase=core[1:,cs['phases']]%(2*np.pi)
    net=np.empty_like(raw)
    for i,leg in enumerate(source.legs):
        a,b=source.swing_period[leg]
        points=[a,(a+b)/2,b+np.pi/4,(b+2*np.pi)/2,2*np.pi]
        net[:,i]=np.clip(raw[:,i],0,80)*np.interp(postphase[:,i],points,[0,.8,0,-.1,0])
    if profile in (CONTROL,PROFILE):net[retraction>0]=0
    errors={}
    for field,want in [('retraction',retraction),('stumbling',stumbling),('persistence',persist),('net_correction',net)]:
        want[~active]=core[:-1,cs[field]][~active]
        error=float(np.max(np.abs(core[1:,cs[field]]-want)))
        errors[field]=error
        if error>TOLERANCE:raise ValueError('independent native reflex state equation: '+field)
        if np.any(core[0,cs[field]]!=0):raise ValueError('native reflex initial state')
    # Evaluate the installed spline assets in batches, and independently apply the
    # literal approved native correction vectors and exactly-once right sign.
    vectors={'f':np.array([-.03,0,0,-.03,0,.03,.03]),'m':np.array([-.015,.001,.025,-.02,0,-.02,0]),'h':np.array([0,0,0,-.02,0,.01,-.02])}
    native=np.empty((len(core),42));corrected=np.empty_like(native)
    for i,leg in enumerate(source.legs):
        q=source.get_joint_angles(leg,core[:,cs['phases']][:,i],core[:,cs['magnitudes']][:,i]).T
        vector=vectors[leg[1]]* (np.array([1,-1,-1,1,-1,1,1]) if leg.startswith('r') else 1)
        for j,spec in enumerate(source.dofs_per_leg):
            index=order.index(dof_spec_to_jointdof(leg,spec));native[:,index]=q[:,j]
            corrected[:,index]=q[:,j]+core[:,cs['net_correction']][:,i]*vector[j]
            if profile in (CONTROL,PROFILE):corrected[:,index]+=core[:,cs['allocation']].reshape(-1,6,7)[:,i,j]
    for key,want in [('native_template',native),('ctrl',corrected)]:
        actual=core[:,cs[key]][:,:42];error=float(np.max(np.abs(actual-want)))
        errors[key]=error
        if error>TOLERANCE:raise ValueError('independent native/applied target mismatch: '+key)
    adhesion=~((core[:,cs['phases']]%(2*np.pi)>0)&(core[:,cs['phases']]%(2*np.pi)<end))
    if not np.array_equal(core[:,cs['ctrl']][:,42:],adhesion) or not np.array_equal(core[:,cs['adhesion']],adhesion):raise ValueError('native adhesion predicate mismatch')
    return {'state_and_command_ticks_checked':len(core)-1,'max_errors':errors,
            'trigger_counts':core[1:,cs['trigger_mask']][active].sum(axis=0).astype(int).tolist(),
            'raw_retraction_max':core[:,cs['retraction']].max(axis=0).tolist(),
            'raw_scalar_over80_counts':(core[1:,cs['retraction']][active]>80).sum(axis=0).tolist()}


def verify_allocation_row(model,data,pre,post,minima,registration,profile=PROFILE):
    """Independent literal law from actual prestate and native target; no controller call."""
    cs=_slices(CORE)
    if profile==CONTROL:
        from .verify_v15 import verify_allocation_row as verify_control
        verify_control(model,data,pre,post,minima,registration)
        if np.any(post[_slices(CORE)['relaxation_diagnostics']]):raise ValueError('v15 has v16 diagnostics')
        return
    mapping=np.asarray(registration['controller']['allocation_joint_map'],dtype=int)
    joints=model.actuator_trnid[:42,0]
    lower=np.full(42,-np.inf);upper=np.full(42,np.inf)
    for i,j in enumerate(joints):
        if model.jnt_limited[j]:lower[i],upper[i]=model.jnt_range[j]
        if model.actuator_ctrllimited[i]:
            lower[i]=max(lower[i],model.actuator_ctrlrange[i,0]);upper[i]=min(upper[i],model.actuator_ctrlrange[i,1])
    offsets=post[cs['allocation']].reshape(6,7);diagnostics=post[cs['allocation_diagnostics']].reshape(6,8)
    relaxation=post[cs['relaxation_diagnostics']].reshape(6,5)
    phase=post[cs['phases']]%(2*np.pi);ends=registration['controller']['release_end']
    q0all=post[cs['native_template']];jacp=np.zeros((3,model.nv))
    for leg,(height,geom,vertex) in enumerate(minima):
        indices=mapping[leg];q0=q0all[indices];lo=lower[indices];hi=upper[indices]
        if np.any(q0<lo) or np.any(q0>hi):raise ValueError('independent infeasible q0')
        if not (post[cs['retraction']][leg]>0 and 0<phase[leg]<ends[leg]):
            if np.any(offsets[leg]!=0) or np.any(diagnostics[leg]!=0) or np.any(relaxation[leg]!=0):raise ValueError('strict retraction phase/priority violation')
            continue
        mesh=model.geom_dataid[geom];local=model.mesh_vert[model.mesh_vertadr[mesh]+vertex].astype(np.float64)
        point=data.geom_xpos[geom]+data.geom_xmat[geom].reshape(3,3)@local
        mj.mj_jac(model,data,jacp,None,point,int(model.geom_bodyid[geom]))
        J=jacp[:,model.jnt_dofadr[joints[indices]]]
        q=pre[cs['qpos']][model.jnt_qposadr[joints[indices]]]
        _,sigma,right=np.linalg.svd(J[:2],full_matrices=True)
        tau=64*np.finfo(float).eps*max(1.,np.linalg.norm(J,2))
        rank=int(np.sum(sigma>tau));basis=right[rank:]
        w=basis.T@(basis@J[2]);authority=float(np.linalg.norm(w));h0=float(height+J[2]@(q0-q))
        end=ends[leg]-np.pi/4
        gain=float(np.interp(phase[leg],[0,end/2,ends[leg],(end+2*np.pi)/2,2*np.pi],[0,.8,0,-.1,0]))
        norm=(.06,np.sqrt(.001651),.03)[leg%3]
        budget=min(max(post[cs['retraction']][leg],0),80)*max(gain,0)*norm
        if authority<=tau:
            if h0<.05:raise ValueError('retained infeasible normal allocation')
            expected=np.zeros(7);diag=np.array([h0,authority,0,budget,-1,0,rank,0]);extra=np.array([0,0,0,0,1.])
        else:
            n=w/authority;row=J[2]-w;c=float(np.linalg.norm(row));D=max(0.,.05-h0);requested=D/authority
            if D<=authority*budget or c<=tau:
                limits=[(hi[j]-q0[j])/n[j] if n[j]>0 else (lo[j]-q0[j])/n[j] if n[j]<0 else np.inf for j in range(7)]
                limit=min(limits);distance=min(requested,budget,limit);expected=distance*n
                flags=int(distance<requested and distance==budget)+2*int(distance<requested and distance==limit)
                diag=np.array([h0,authority,requested,budget,limit if np.isfinite(limit) else -1.,max(0.,.05-h0-authority*distance),rank,flags])
                nominal=min(requested,budget);extra=np.array([0,nominal,0,c,distance/nominal if nominal else 1.])
                if np.max(np.abs(J[:2]@offsets[leg]))>TOLERANCE:raise ValueError('feasible tangent preservation violation')
            else:
                magnitude=float(np.hypot(authority,c));m=row/c
                if D<magnitude*budget:
                    root=float(np.sqrt(max(0.,(magnitude*budget)**2-D**2)))
                    x=(authority*D+c*root)/magnitude**2;y=max(0.,(c*D-authority*root)/magnitude**2);branch=1
                else:x=budget*authority/magnitude;y=budget*c/magnitude;branch=2
                expected=x*n+y*m;length=float(np.linalg.norm(expected))
                if length>budget:
                    shrink=budget/length;expected*=shrink;x*=shrink;y*=shrink;length=float(np.linalg.norm(expected))
                ratios=[(hi[j]-q0[j])/expected[j] if expected[j]>0 else (lo[j]-q0[j])/expected[j] if expected[j]<0 else np.inf for j in range(7)]
                maxscale=min(ratios);scale=min(1.,maxscale);limit=length*maxscale if length and np.isfinite(maxscale) else -1.
                expected*=scale;flags=int(D>magnitude*budget)+2*int(scale<1.)
                diag=np.array([h0,authority,requested,budget,limit,max(0.,.05-float(h0+J[2]@expected)),rank,flags]);extra=np.array([branch,x,y,c,scale])
            if np.linalg.norm(offsets[leg])>budget+TOLERANCE or np.any(q0+offsets[leg]<lo-TOLERANCE) or np.any(q0+offsets[leg]>hi+TOLERANCE):
                raise ValueError('independent angular/range budget violation')
        if np.max(np.abs(expected-offsets[leg]))>TOLERANCE or np.max(np.abs(diag-diagnostics[leg]))>TOLERANCE or np.max(np.abs(extra-relaxation[leg]))>TOLERANCE:
            raise ValueError('independent two-direction allocation/diagnostics mismatch')


def verify_panel(root, stage, budget):
    registration = validate_freeze(root)
    analysis = json.loads((root/f'{stage}-analysis.json').read_text())
    expected = panel(stage)
    names = {f'{profile}--{seed}--{case[0]}' for profile,seed,case in expected}
    if set(analysis['trials']) != names or analysis['registration_sha256'] != file_sha(root/'registration.json'):
        raise ValueError('independent panel identity mismatch')
    model = mj.MjModel.from_binary_path(str(root/'model.mjb'))
    from flygym_demo.complex_terrain.preprogrammed import PreprogrammedSteps
    from flygym_demo.complex_terrain.common import get_default_locomotion_dof_order,dof_spec_to_jointdof
    native_steps=PreprogrammedSteps();order=get_default_locomotion_dof_order()
    mapping=[[order.index(dof_spec_to_jointdof(leg,spec)) for spec in native_steps.dofs_per_leg] for leg in native_steps.legs]
    if mapping!=registration['controller']['allocation_joint_map']:raise ValueError('independent anatomical joint map mismatch')
    foot = np.array(registration['measurement']['foot_geom_ids'],dtype=int)
    vertices,centroids=[],[]
    for geom in foot:
        mesh=model.geom_dataid[geom];begin=model.mesh_vertadr[mesh];count=model.mesh_vertnum[mesh]
        value=np.asarray(model.mesh_vert[begin:begin+count],dtype=np.float64)
        vertices.append(value);centroids.append(value.mean(axis=0))
    ground=int(mj.mj_name2id(model,mj.mjtObj.mjOBJ_GEOM,'ground_plane'))
    thorax=int(mj.mj_name2id(model,mj.mjtObj.mjOBJ_BODY,'fly-0/c_thorax'))
    leg_by_geom=np.full(model.ngeom,-1,dtype=int);leg_by_geom[foot]=np.arange(30)//5
    meta={'foot':foot,'vertices':vertices,'centroids':np.array(centroids),'thorax':thorax}
    cs,ds,es=_slices(CORE),_slices(DENSE),_slices(CONTACT)
    receipts={}
    for profile,seed,case in expected:
        name=f'{profile}--{seed}--{case[0]}';trial=root/stage/name;reported=analysis['trials'][name]
        wanted={'stage':stage,'profile':profile,'seed':seed,'case':case,'registration_sha256':file_sha(root/'registration.json'),'sources_sha256':registration['sources_sha256']}
        if any(json.loads((trial/stream/'start.json').read_text()) != wanted for stream in ('core','dense','contacts')):
            raise ValueError('independent trial stream identity mismatch')
        ticks,core=_read_stream(trial/'core',_width(CORE),ROWS)
        dense_ticks,dense=_read_stream(trial/'dense',_width(DENSE),ROWS)
        ct,contact=_read_stream(trial/'contacts',_width(CONTACT))
        if not np.array_equal(ticks,np.arange(ROWS)) or not np.array_equal(ticks,dense_ticks) or np.any(np.diff(ct)<0) or np.any((ct<0)|(ct>=ROWS)):
            raise ValueError('independent raw grids invalid')
        _,common,asymmetry=case
        inputs=np.zeros((ROWS,2));inputs[3001:25001]=[common*(1-asymmetry),common*(1+asymmetry)]
        if not np.array_equal(inputs,core[:,cs['input']]):raise ValueError('independent command waveform differs')
        law=verify_phase_law(core,profile,registration)
        reflex=verify_retraction_and_commands(core,profile,registration)
        derived_path=root/f'{stage}-derived'/reported['derived_npz']
        if file_sha(derived_path)!=reported['derived_npz_sha256']:raise ValueError('independent derived digest mismatch')
        with np.load(derived_path,allow_pickle=False) as archive:d={key:archive[key] for key in archive.files}
        vector_fields={'endpoint_source_core_row','interval_contact_row_tick','interval_state_start_core_row','interval_state_end_core_row','ticks'}
        six_fields={'endpoint_thorax_ap','endpoint_whole_foot_min_height','interval_summed_positive_normal','interval_force_weighted_pre_tangent','interval_peak_pre_tangent_speed'}
        if set(d)!=vector_fields|six_fields|{'endpoint_thorax_position','endpoint_thorax_rotation','coherent_contact_ticks','coherent_contact_velocity'}:raise ValueError('independent derived field contract')
        for key in vector_fields:
            wanted_grid=np.r_[-1,np.arange(ROWS-1)] if key=='interval_state_start_core_row' else np.arange(ROWS)
            if d[key].dtype!=np.int64 or not np.array_equal(d[key],wanted_grid):raise ValueError('independent derived grid contract')
        for key,width in [(key,6) for key in six_fields]+[('endpoint_thorax_position',3),('endpoint_thorax_rotation',9),('coherent_contact_velocity',3)]:
            rows=len(contact) if key=='coherent_contact_velocity' else ROWS
            if d[key].dtype!=np.float64 or d[key].shape!=(rows,width) or not np.isfinite(d[key]).all():raise ValueError('independent derived numeric contract')
        if d['coherent_contact_ticks'].dtype!=np.int64 or not np.array_equal(ct,d['coherent_contact_ticks']):raise ValueError('independent contact row join')
        normal=np.zeros((ROWS,6));weighted=np.zeros((ROWS,6));peak=np.zeros((ROWS,6))
        fg=contact[:,es['foot_geom']].astype(int).ravel();gg=contact[:,es['ground_geom']].astype(int).ravel()
        if np.any((fg<0)|(fg>=model.ngeom)) or np.any(gg!=ground) or np.any(leg_by_geom[fg]<0):raise ValueError('independent contact identity')
        legs=leg_by_geom[fg];fn=contact[:,es['wrench_contact_frame']][:,0]
        normals=contact[:,es['frame']].reshape(-1,3,3)[:,0]
        coherent=d['coherent_contact_velocity'];tangent=coherent-normals*np.sum(coherent*normals,axis=1)[:,None]
        speeds=np.linalg.norm(tangent,axis=1);loaded=(ct>0)&(fn>0)
        np.add.at(normal,(ct[loaded],legs[loaded]),fn[loaded]);np.add.at(weighted,(ct[loaded],legs[loaded]),fn[loaded]*speeds[loaded])
        np.maximum.at(peak,(ct[ct>0],legs[ct>0]),speeds[ct>0])
        if not np.array_equal(normal,d['interval_summed_positive_normal']) or np.max(np.abs(weighted-d['interval_force_weighted_pre_tangent']))>TOLERANCE or np.max(np.abs(peak-d['interval_peak_pre_tangent_speed']))>TOLERANCE:raise ValueError('independent raw contact quadrature closure')
        if np.any(coherent[ct==0]!=0):raise ValueError('tickzero has no coherent integration interval')
        data=mj.MjData(model);geometry_error=velocity_error=sensor_error=0.;checked=sensor_rows=0
        unique,first,counts=np.unique(ct,return_index=True,return_counts=True)
        groups={int(tick):(int(begin),int(begin+count)) for tick,begin,count in zip(unique,first,counts)}
        # Every endpoint and every retained contact velocity independently reconstructed.
        for tick in range(ROWS):
            if tick%1000==0:budget.check()
            height,ap=_geometry_sample(model,data,core[tick,cs['qpos']],meta)
            geometry_error=max(geometry_error,float(np.max(np.abs(height-d['endpoint_whole_foot_min_height'][tick]))),float(np.max(np.abs(ap-d['endpoint_thorax_ap'][tick]))),float(np.max(np.abs(data.xpos[thorax]-d['endpoint_thorax_position'][tick]))),float(np.max(np.abs(data.xmat[thorax]-d['endpoint_thorax_rotation'][tick]))))
            interval=tick+1
            if profile in (PROFILE,CONTROL) and interval<ROWS and core[interval,cs['input']].mean()>1e-4:
                sensor_error=max(sensor_error,float(np.max(np.abs(height-core[interval,cs['sensed_clearance']]))))
                minima=[(np.inf,-1,-1) for _ in range(6)]
                for index,(geom,verts) in enumerate(zip(foot,vertices)):
                    z=verts@data.geom_xmat[geom].reshape(3,3)[2]+data.geom_xpos[geom,2]
                    vertex=int(np.argmin(z));entry=(float(z[vertex]),int(geom),vertex);leg=index//5
                    if entry<minima[leg]:minima[leg]=entry
                if not np.array_equal(core[interval,cs['minimum_geom']],[v[1] for v in minima]) or not np.array_equal(core[interval,cs['minimum_vertex']],[v[2] for v in minima]):raise ValueError('independent sensor minimum vertex identity')
                if profile in (CONTROL,PROFILE):
                    if core[interval,cs['observation_tick']][0]!=tick:raise ValueError('observation prestate tick mismatch')
                    verify_allocation_row(model,data,core[tick],core[interval],minima,registration,profile)
                sensor_rows+=1
            if interval<ROWS and interval in groups:
                begin,end=groups[interval];data.qvel[:]=core[tick,cs['qvel']]
                velocity=_jacobian_velocity(model,data,contact[begin:end,es['position']],fg[begin:end],gg[begin:end])
                velocity_error=max(velocity_error,float(np.max(np.abs(velocity-coherent[begin:end]))));checked+=end-begin
        if geometry_error>TOLERANCE or velocity_error>TOLERANCE or sensor_error>TOLERANCE:raise ValueError('independent endpoint/prestate velocity mismatch')
        active=common>1e-4
        if active:
            recovery,support,invalid,status=_cycle_gate(core[:,cs['phases']],d['endpoint_thorax_ap'],d['endpoint_whole_foot_min_height'],normal,weighted,registration['controller']['swing_periods_strict_modulo'])
            if (recovery!=reported['recovery_passed'] or support!=reported['support_slip_passed'] or invalid!=reported['invalid_interior_phase_episodes']):raise ValueError('independent strict cycle outcome mismatch')
        else:
            recovery=support=False;invalid=0;status=[]
        pos=d['endpoint_thorax_position'];rot=d['endpoint_thorax_rotation'].reshape(-1,3,3)
        velocity=np.diff(pos,axis=0)/DT;yaw=np.unwrap(np.arctan2(rot[:,1,0],rot[:,0,0]))
        values={'forward_mean_mm_s':float(np.mean(np.sum(velocity[6000:25000]*rot[6000:25000,:,0],axis=1))),
                'mean_yaw_rate_rad_s':float((yaw[25000]-yaw[6000])/1.9),'net_active_yaw_rad':float(yaw[25000]-yaw[3000]),
                'min_upright_z':float(rot[:,2,2].min()),'stop_displacement_mm':float(np.linalg.norm(pos[40000]-pos[30000])),
                'stop_mean_speed_mm_s':float(np.linalg.norm(velocity[30000:40000],axis=1).mean())}
        if any(values[key]!=reported[key] for key in values):raise ValueError('independent endpoint kinematics mismatch')
        gates={'finite':True,'upright':values['min_upright_z']>.8,'stop':values['stop_displacement_mm']<.25 and values['stop_mean_speed_mm_s']<.1}
        if active:
            gates.update(recovery=recovery,support_slip=support)
            if asymmetry:gates['turn']=bool(np.sign(values['net_active_yaw_rad'])==np.sign(asymmetry) and abs(values['net_active_yaw_rad'])>.1)
            else:gates['straight_yaw']=abs(values['mean_yaw_rate_rad_s'])<.15
        if gates!=reported['gates']:raise ValueError('independent operational gate mismatch')
        # All stance-slip formulas, including failed cycles, are checked against retained sums.
        slips=0
        for leg,records in enumerate(reported['stance_cycles']):
            for record in records:
                start,end=record['start_tick'],record['end_tick_exclusive'];force=normal[start:end,leg]
                value=float(DT*np.divide(weighted[start:end,leg],force,out=np.zeros(end-start),where=force>0).sum())
                if abs(value-record['slip_mm'])>TOLERANCE:raise ValueError('independent stance slip formula mismatch')
                slips+=1
        receipts[name]={'identity':wanted,'gates':gates,'controller_law':law,'native_reflex_and_targets':reflex,'sensor_rows_checked':sensor_rows,'max_sensor_error':sensor_error,'endpoint_rows_checked':ROWS,'contact_velocities_checked':checked,'raw_contact_rows':len(contact),'stance_slips_checked':slips,'max_geometry_error':geometry_error,'max_velocity_error':velocity_error,'cycle_status':status}
        print(json.dumps({'verified':stage+'/'+name,'physical_seconds':budget.steps*DT}),flush=True)
    aggregates={}
    for profile in ((CONTROL,PROFILE) if stage=='development' else (PROFILE,)):
        for seed in ((42,43) if stage=='development' else (31042,31043)):
            speed=[analysis['trials'][f'{profile}--{seed}--{case}']['forward_mean_mm_s'] for case in ('straight-008','straight-02','straight-04')]
            aggregates[f'{profile}--{seed}--speed-dose']=bool(speed[0]>.2 and all(b-a>.2 for a,b in zip(speed,speed[1:])))
    admitted=all(all(receipt['gates'].values()) for name,receipt in receipts.items() if name.startswith(PROFILE+'--')) and all(value for name,value in aggregates.items() if name.startswith(PROFILE+'--'))
    if aggregates!=analysis['aggregate_gates'] or admitted!=analysis['candidate_passed']:raise ValueError('independent aggregate decision mismatch')
    result={'schema':'behavior-v16-independent-verification/v1','passed':True,'stage':stage,'candidate_passed':admitted,'scientific_admission':False,'registration_sha256':file_sha(root/'registration.json'),'analysis_sha256':file_sha(root/f'{stage}-analysis.json'),'trial_count':len(receipts),'trials':receipts,'aggregate_gates':aggregates,'resources':budget.report()}
    write_json(root/f'{stage}-independent-verification.json',result)
    return result


def verify_repeat(root):
    profile,seed,case=panel('repeat')[0];name=f'{profile}--{seed}--{case[0]}'
    for stream,schema in (('core',CORE),('dense',DENSE),('contacts',CONTACT)):
        left=_read_stream(root/'evaluation'/name/stream,_width(schema))
        right=_read_stream(root/'repeat'/name/stream,_width(schema))
        if not all(np.array_equal(a,b) for a,b in zip(left,right)):raise ValueError('exact repeat raw stream mismatch')
    write_json(root/'repeat-verification.json',{'passed':True,'trial':name,'streams':['core','dense','contacts'],'registration_sha256':file_sha(root/'registration.json')})


def _validate_restoration_arrays(arrays,integration_width):
    required={'core','dense','contacts','integration','contact_offsets'}
    if set(arrays)!=required:raise ValueError('restore exact fivefield schema')
    contacts=arrays['contacts'];expected={'core':((100,_width(CORE)),np.float64),'dense':((100,_width(DENSE)),np.float64),'contacts':((len(contacts),_width(CONTACT)),np.float64),'integration':((100,integration_width),np.float64),'contact_offsets':((101,),np.int64)}
    for key,(shape,dtype) in expected.items():
        if arrays[key].shape!=shape or arrays[key].dtype!=dtype or not np.isfinite(arrays[key]).all():raise ValueError('restore field contract')
    offsets=arrays['contact_offsets']
    if offsets[0]!=0 or offsets[-1]!=len(contacts) or np.any(np.diff(offsets)<0):raise ValueError('restore offsets')


def verify_restoration(root):
    dest=root/'restoration';checkpoint=json.loads((dest/'checkpoint.json').read_text())
    expected=json.loads((dest/'expected-digests.json').read_text());actual=json.loads((dest/'actual-digests.json').read_text())
    _validate_restoration_digest_sequences(expected,actual,checkpoint)
    _validate_digest_document(expected,checkpoint['cache'],'expected');_validate_digest_document(actual,checkpoint['cache'],'actual')
    with np.load(dest/'expected.npz',allow_pickle=False) as left,np.load(dest/'actual.npz',allow_pickle=False) as right:
        arrays={k:left[k] for k in left.files};other={k:right[k] for k in right.files}
        _validate_restoration_arrays(arrays,752);_validate_restoration_arrays(other,752)
        if any(not np.array_equal(arrays[k],other[k]) for k in arrays):raise ValueError('active restore exact fivefield mismatch')
        trial=root/checkpoint['binding']['trial'];ticks,core=_read_stream(trial/'core',_width(CORE),ROWS);_,dense=_read_stream(trial/'dense',_width(DENSE),ROWS);ct,contacts=_read_stream(trial/'contacts',_width(CONTACT))
        selected=(ct>=10001)&(ct<=10100)
        offsets=np.r_[0,np.cumsum([np.count_nonzero(ct==tick) for tick in range(10001,10101)])]
        if not np.array_equal(arrays['core'],core[10001:10101]) or not np.array_equal(arrays['dense'],dense[10001:10101]) or not np.array_equal(arrays['contacts'],contacts[selected]) or not np.array_equal(arrays['contact_offsets'],offsets):raise ValueError('active restoration original raw join mismatch')
    write_json(dest/'independent-verification.json',{'passed':True,'ticks':100,'additional_physical_seconds':.01,'reference_ticks_in_development_panel':[10001,10100],'registration_sha256':file_sha(root/'registration.json')})

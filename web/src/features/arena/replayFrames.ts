/** Bracket recorded timestamps; preserve recorded geometry at both endpoints. */
export function selectReplayFrames<T extends {time:number}>(frames:readonly T[],time:number) {
  if (!frames.length) return {frame:undefined,next:undefined,alpha:0}
  const last=frames.length-1
  const index=time>=frames[last].time?last:Math.max(0,frames.findIndex(f=>f.time>time)-1)
  const frame=frames[index],next=frames[Math.min(index+1,last)]
  const alpha=next.time>frame.time?Math.max(0,Math.min(1,(time-frame.time)/(next.time-frame.time))):0
  return {frame,next,alpha}
}

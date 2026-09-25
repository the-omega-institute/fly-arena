export type LineageNode={id:string;label:string;depth:number;relation:string;marker?:boolean;continuation?:string;redacted?:boolean}
export type LineageEdge={from:string;to:string;relation:string}
export type LineagePoint={x:number;y:number;width:number;height:number;node:LineageNode}
export type LineagePath=LineageEdge&{path:string;selected:boolean}

/** Stable, side-effect-free coordinates for the 2-D lineage view. */
export function lineageLayout(nodes:LineageNode[],edges:LineageEdge[],centerId:string,cardWidth=190,rowHeight=86){
 const byId=new Map(nodes.map(node=>[node.id,node]));
 const outgoing=new Map<string,LineageEdge[]>();const incoming=new Map<string,LineageEdge[]>()
 for(const edge of edges){if(!byId.has(edge.from)||!byId.has(edge.to)||edge.from===edge.to)continue;const from=outgoing.get(edge.from)||[];from.push(edge);outgoing.set(edge.from,from);const to=incoming.get(edge.to)||[];to.push(edge);incoming.set(edge.to,to)}
 const compare=(a:LineageNode,b:LineageNode)=>a.id===centerId?-1:b.id===centerId?1:a.depth-b.depth||a.label.localeCompare(b.label)||a.id.localeCompare(b.id)
 for(const list of outgoing.values())list.sort((a,b)=>compare(byId.get(a.to)!,byId.get(b.to)!))
 const roots=nodes.filter(node=>!(incoming.get(node.id)||[]).length).sort(compare)
 const yById=new Map<string,number>();const visiting=new Set<string>();const visited=new Set<string>();let cursor=0
 const place=(id:string):number=>{
  if(yById.has(id))return yById.get(id)!
  if(visiting.has(id))return cursor*rowHeight
  visiting.add(id)
  const children=(outgoing.get(id)||[]).map(edge=>edge.to).filter(child=>!visited.has(child))
  let y:number
  if(children.length){const childY=children.map(place);y=(Math.min(...childY)+Math.max(...childY))/2}else{y=cursor*rowHeight;cursor+=1}
  visiting.delete(id);visited.add(id);yById.set(id,y);return y
 }
 for(const node of roots)place(node.id)
 for(const node of [...nodes].sort(compare))if(!visited.has(node.id))place(node.id)
 const selectedPath=new Set<string>();let current=centerId;const seen=new Set<string>()
 while(byId.has(current)&&!seen.has(current)){
  seen.add(current);selectedPath.add(current)
  const parent=(incoming.get(current)||[]).filter(edge=>edge.relation!=='sibling').sort((a,b)=>compare(byId.get(a.from)!,byId.get(b.from)!))[0]
  if(!parent)break
  current=parent.from
 }
 const minDepth=Math.min(...nodes.map(node=>node.depth),0);const gap=Math.max(36,Math.round(cardWidth*.28));const nodeHeight=78
 const points=new Map<string,LineagePoint>()
 for(const node of nodes)points.set(node.id,{node,x:30+(node.depth-minDepth)*(cardWidth+gap),y:30+(yById.get(node.id)||0),width:cardWidth,height:nodeHeight})
 const width=Math.max(cardWidth+60,...Array.from(points.values(),point=>point.x+point.width+30));const maxY=Math.max(0,...Array.from(points.values(),point=>point.y));const height=Math.max(nodeHeight+58,maxY+nodeHeight+30)
 const paths:LineagePath[]=edges.flatMap(edge=>{const from=points.get(edge.from),to=points.get(edge.to);if(!from||!to)return[];const x1=from.x+from.width,x2=to.x,y1=from.y+from.height/2,y2=to.y+to.height/2;return [{...edge,selected:selectedPath.has(edge.from)&&selectedPath.has(edge.to)&&edge.relation!=='sibling',path:`M ${x1} ${y1} C ${(x1+x2)/2} ${y1}, ${(x1+x2)/2} ${y2}, ${x2} ${y2}`}]} )
 return {points:Array.from(points.values()),paths,width,height,selectedPath:[...selectedPath]}
}

export const layoutLineage=lineageLayout

/** The UI translates stable codes; API prose is retained only for older clients. */
export function lineageDeltaMessage(delta?:{code?:string;summary?:string;changed:boolean|null}|null){
 const messages:Record<string,string>={founder:'Founder design; no parent design was recorded.',changed:'Recorded changes relative to the parent FlySpec.',unchanged:'No design change relative to the parent FlySpec was recorded.',parent_unavailable:'Parent design is private; the relative delta is unavailable.'}
 if(delta?.code&&messages[delta.code])return messages[delta.code]
 // Older servers used these exact summaries, so localize those as well.
 if(delta?.summary&&Object.values(messages).includes(delta.summary))return delta.summary
 return 'Design delta unavailable.'
}

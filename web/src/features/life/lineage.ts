export type LineageNode={id:string;label:string;depth:number;relation:string;marker?:boolean;continuation?:string;redacted?:boolean}
export type LineageEdge={from:string;to:string;relation:string}
export type LineagePoint={x:number;y:number;width:number;height:number;node:LineageNode}

/** Stable, side-effect-free coordinates for the 2-D lineage view. */
export function lineageLayout(nodes:LineageNode[],edges:LineageEdge[],centerId:string,cardWidth=190,rowHeight=86){
 const columns=new Map<number,LineageNode[]>()
 for(const node of nodes){const column=columns.get(node.depth)||[];column.push(node);columns.set(node.depth,column)}
 for(const column of columns.values())column.sort((a,b)=>a.id===centerId?-1:b.id===centerId?1:a.label.localeCompare(b.label)||a.id.localeCompare(b.id))
 const points=new Map<string,LineagePoint>();const maxRows=Math.max(1,...Array.from(columns.values(),column=>column.length))
 for(const [depth,column] of columns){for(const [index,node] of column.entries())points.set(node.id,{node,x:30+(depth-Math.min(...columns.keys()))*cardWidth*1.35,y:30+index*rowHeight,width:cardWidth,height:58})}
 const width=Math.max(cardWidth+60,...Array.from(points.values(),point=>point.x+point.width+30));const height=Math.max(116,maxRows*rowHeight+30)
 const paths=edges.flatMap(edge=>{const from=points.get(edge.from),to=points.get(edge.to);if(!from||!to)return[];const x1=from.x+from.width,x2=to.x,y1=from.y+from.height/2,y2=to.y+to.height/2;return [{...edge,path:`M ${x1} ${y1} C ${(x1+x2)/2} ${y1}, ${(x1+x2)/2} ${y2}, ${x2} ${y2}`}]} )
 return {points:Array.from(points.values()),paths,width,height}
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

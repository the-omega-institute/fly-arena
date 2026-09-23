import type {guideMessages} from '../../shared/messages/guide'

export type GuideMessageKey=keyof typeof guideMessages
export type GuideSection={id:string;title:GuideMessageKey;summary:GuideMessageKey;details:readonly GuideMessageKey[];links?:readonly {label:GuideMessageKey;href:string}[]}
export type GuideAction='clone'|'design'|'compare'|'train'|'compete'
export type JourneyStep={id:string;title:GuideMessageKey;summary:GuideMessageKey;detail:GuideMessageKey;action?:GuideAction;label?:GuideMessageKey}

export const guideSections:readonly GuideSection[]=[
  {id:'basis',title:'guide.basis.title',summary:'guide.basis.summary',details:['guide.basis.anatomy','guide.basis.dynamics','guide.basis.body','guide.basis.limits'],links:[{label:'guide.source.malecns',href:'https://male-cns.janelia.org/'},{label:'guide.source.flygym',href:'https://github.com/NeLy-EPFL/flygym'}]},
  {id:'value',title:'guide.value.title',summary:'guide.value.summary',details:['guide.value.controls','guide.value.receipts','guide.value.failures']},
  {id:'meaning',title:'guide.meaning.title',summary:'guide.meaning.summary',details:['guide.meaning.exploration','guide.meaning.lineage']},
  {id:'data',title:'guide.data.title',summary:'guide.data.summary',details:['guide.data.pairs','guide.data.uses','guide.data.limits']},
  {id:'journey',title:'guide.journey.title',summary:'guide.journey.summary',details:['guide.journey.help']},
]

export const journeySteps:readonly JourneyStep[]=[
  {id:'clone',title:'guide.clone.title',summary:'guide.clone.summary',detail:'guide.clone.detail',action:'clone',label:'guide.action.clone'},
  {id:'edit',title:'guide.edit.title',summary:'guide.edit.summary',detail:'guide.edit.detail',action:'design',label:'guide.action.design'},
  {id:'save',title:'guide.save.title',summary:'guide.save.summary',detail:'guide.save.detail'},
  {id:'compare',title:'guide.compare.title',summary:'guide.compare.summary',detail:'guide.compare.detail',action:'compare',label:'guide.action.compare'},
  {id:'evolve',title:'guide.evolve.title',summary:'guide.evolve.summary',detail:'guide.evolve.detail',action:'train',label:'guide.action.train'},
  {id:'compete',title:'guide.compete.title',summary:'guide.compete.summary',detail:'guide.compete.detail',action:'compete',label:'guide.action.compete'},
]

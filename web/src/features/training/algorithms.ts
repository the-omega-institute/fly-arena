export const algorithms = [
  {id:'evolution',name:'Evolution · select and mutate',description:'Each generation retains its best parent and explores mutations around it.'},
  {id:'random_search',name:'Random search · explore from founder',description:'Each generation explores mutations around the original founder.'},
  {id:'cross_entropy',name:'CEM · learn a search distribution',description:'Fit a Gaussian to the top half of each generation, then sample new circuit weights. Retain the best parent.'},
  {id:'external',name:'Custom algorithm / model · Python or API',description:'Run your optimizer on your own device. Submit FlySpecs; Arena handles evaluation and limits.'},
] as const
export type Strategy=typeof algorithms[number]['id']
export const algorithmName=(id:string)=>algorithms.find(a=>a.id===id)?.name||id

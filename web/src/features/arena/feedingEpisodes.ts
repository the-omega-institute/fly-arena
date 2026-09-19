import type {ReplayEvent} from '../../types'

export type FeedingEpisode={food:number;foodId:string;firstTick:number;lastTick:number;start:number;end:number;amount:number;batches:number;contactTimes:number[]}
/** Consecutive positive accounting batches for each food, not inferred meals.
 * The first timestamp is a batch end; a short unobserved contact is never invented. */
export function feedingEpisodes(events:ReplayEvent[],slot:number,foodIds:string[],physicsDt:number,accountingTicks:number){
 const episodes:FeedingEpisode[]=[],lastByFood=new Map<number,FeedingEpisode>()
 let invalid=0
 if(!Number.isFinite(physicsDt)||physicsDt<=0||!Number.isInteger(accountingTicks)||accountingTicks<=0)return {episodes,invalid,timingAvailable:false}
 for(const event of events.filter(e=>e.type==='intake'&&e.slot===slot).sort((a,b)=>a.tick-b.tick)){
  const food=event.food,amount=event.amount
  if(!Number.isInteger(event.tick)||event.tick<0||typeof food!=='number'||!Number.isInteger(food)||food<0||food>=foodIds.length||typeof amount!=='number'||!Number.isFinite(amount)||amount<=0){invalid++;continue}
  let episode=lastByFood.get(food)
  if(!episode||event.tick-episode.lastTick>accountingTicks){
   episode={food,foodId:foodIds[food],firstTick:event.tick,lastTick:event.tick,start:event.tick*physicsDt,end:event.tick*physicsDt,amount:0,batches:0,contactTimes:[]}
   episodes.push(episode);lastByFood.set(food,episode)
  }
  episode.lastTick=event.tick;episode.end=event.tick*physicsDt;episode.amount+=amount;episode.batches++
 }
 for(const episode of episodes){
  episode.contactTimes=events.filter(e=>e.type==='food_contact'&&e.slot===slot&&Number.isFinite(e.tick)&&e.tick>=Math.max(0,episode.firstTick-accountingTicks)&&e.tick<=episode.lastTick&&Array.isArray(e.food)&&e.food.includes(episode.foodId)).map(e=>e.tick*physicsDt).sort((a,b)=>a-b)
 }
 return {episodes,invalid,timingAvailable:true}
}

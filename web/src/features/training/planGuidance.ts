export function shortHorizonTrainingGuidance({duration,fitnessObjective}:{duration:number;fitnessObjective:string}):string|null{
 if(duration<=2&&['food','sustained-foraging-v1'].includes(fitnessObjective))return 'A 1–2 second food horizon often records zero because fitness requires a verified intake event. Consider 5 seconds or more; a future versioned objective would need a graded approach component. This guidance does not change scoring.'
 return null
}

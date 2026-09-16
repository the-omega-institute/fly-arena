type OwnedDesign = {id:string;owner:string}
export type DesignSelection = {selected:string;owner:string|undefined;design:string}

// A refreshed collection validates a choice; only a new context initializes it.
export function reconcileDesignSelection(previous:DesignSelection|undefined, flies:OwnedDesign[], selected:string, owner:string|undefined):DesignSelection {
  const owned = (id:string) => !!owner && flies.some(f=>f.id===id&&f.owner===owner)
  if (!previous || previous.selected!==selected || previous.owner!==owner) {
    return {selected,owner,design:owned(selected)?selected:owner?flies.find(f=>f.owner===owner)?.id||'':''}
  }
  return previous.design && !owned(previous.design) ? {...previous,design:''} : previous
}

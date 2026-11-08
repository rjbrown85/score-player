(function(root){
  const api={
    bounds(start,end,total){const gap=Math.min(.25,total);const b=Math.min(total,Math.max(gap,Number(end)||total));return {start:Math.max(0,Math.min(Number(start)||0,b-gap)),end:b};},
    clip(notes,start,end){return notes.filter(n=>n.start<end&&n.start+n.duration>start).map(n=>{const s=Math.max(start,n.start);return {...n,start:s,duration:Math.min(end,n.start+n.duration)-s};}).sort((a,b)=>a.start-b.start);},
    wrap(beat,start,end){return beat<end?beat:start+((beat-end)%(end-start));}
  };
  if(typeof module!=='undefined')module.exports=api;else root.ScoreLoop=api;
})(typeof window!=='undefined'?window:globalThis);

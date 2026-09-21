(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  root.MostkulturaPlaceSearch=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const normalize=value=>String(value??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('cs-CZ').trim();

  function find(query,places,events){
    const needle=normalize(query);
    if(needle.length<2)return null;
    const candidates=[...(places||[]),...(events||[]).flatMap(event=>[event.place,event.venue])]
      .filter(Boolean);
    const match=candidates.find(candidate=>{
      const value=normalize(candidate);
      return value.includes(needle);
    });
    return match?{query:String(query).trim(),place:match}:null;
  }

  function panelState({match,tab,currentCount,allCount}){
    if(!match)return null;
    if(['today','tomorrow','weekend'].includes(tab)){
      return allCount ? {type:'cta',currentCount,allCount} : {type:'empty'};
    }
    return tab==='all'&&!allCount ? {type:'empty'} : null;
  }

  return {normalize,find,panelState};
});

(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  root.MostkulturaDateRange=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';

  function validISODate(value){
    if(!/^(?!0000)\d{4}-\d{2}-\d{2}$/.test(value||''))return false;
    const date=new Date(value+'T12:00:00Z');
    return !Number.isNaN(date.getTime())&&date.toISOString().slice(0,10)===value;
  }

  function normalizeRange(start,end,fallback){
    const safeFallback=validISODate(fallback)?fallback:'1970-01-01';
    const safeStart=validISODate(start)?start:safeFallback;
    const safeEnd=validISODate(end)?end:safeStart;
    return safeStart<=safeEnd?[safeStart,safeEnd]:[safeEnd,safeStart];
  }

  function addDays(iso,amount){
    if(!validISODate(iso))return null;
    const date=new Date(iso+'T12:00:00Z');
    date.setUTCDate(date.getUTCDate()+amount);
    const result=date.toISOString().slice(0,10);
    return validISODate(result)?result:null;
  }

  function length(start,end){
    const range=normalizeRange(start,end,start);
    return Math.round((new Date(range[1]+'T12:00:00Z')-new Date(range[0]+'T12:00:00Z'))/86400000)+1;
  }

  return {validISODate,normalizeRange,addDays,length};
});

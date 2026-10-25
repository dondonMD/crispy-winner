import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {Opportunity} from '../intelligenceTypes';

const LIMIT=20;

/** Retain display identity/order only; never retain fresh eligibility. */
export function useOpportunityInspection(ranked:Opportunity[],all:Opportunity[],scope:string,filtered:boolean){
 const previous=useRef<{scope:string;items:Opportunity[]}>({scope:'',items:[]});
 const [inspection,setInspection]=useState<string|null>(null);
 const [,setRevision]=useState(0);
 const held=filtered||inspection===scope;
 const latest=new Map(all.map(o=>[o.mint,o]));
 const retaining=held&&previous.current.scope===scope;
 const items:Opportunity[]=retaining
  ?previous.current.items.map(old=>latest.get(old.mint)||old):ranked.slice(0,LIMIT);
 const seen=new Set(items.map(o=>o.mint));
 if(retaining)for(const item of ranked){
  if(items.length>=LIMIT)break;
  if(!seen.has(item.mint)){items.push(item);seen.add(item.mint)}
 }
 useLayoutEffect(()=>{previous.current={scope,items}});
 useEffect(()=>{
  const scrolled=()=>{if(window.scrollY>0)setInspection(scope)};
  window.addEventListener('scroll',scrolled,{passive:true});
  return()=>window.removeEventListener('scroll',scrolled);
 },[scope]);
 function hold(){setInspection(scope)}
 function refresh(){previous.current={scope:'',items:[]};setInspection(null);setRevision(n=>n+1)}
 return {items,held,hold,refresh,pending:ranked.filter(o=>!seen.has(o.mint)).length,
         present:(mint:string|undefined)=>latest.has(mint)};
}

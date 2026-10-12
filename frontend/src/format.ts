export const money=(value:number|null|undefined,digits=2)=>value==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:digits}).format(value);
export const num=(value:unknown,digits=1)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(digits):'—';
export const pct=(value:number|null|undefined)=>value==null?'—':`${num(value)}%`;
export const age=(seconds:number)=>seconds<60?`${Math.floor(seconds)}s`:`${Math.floor(seconds/60)}m ${Math.floor(seconds%60)}s`;
export function filterTokens<T extends {name:string;symbol:string;mint:string;state:string}>(tokens:T[],query:string,stage:string){return tokens.filter(t=>(stage==='ALL'||t.state===stage)&&`${t.name} ${t.symbol} ${t.mint}`.toLowerCase().includes(query.toLowerCase()));}

export function providerStatus(p:{status?:string;connected:boolean;attempted?:boolean;rate_limited_until?:number}, now=Date.now()/1000){return (p.rate_limited_until||0)>now?'RATE LIMITED':p.status||(p.connected?'CURRENT':p.attempted?'DEGRADED':'NOT USED YET');}

export function curveLabel(progress:number|null|undefined,quality?:string){return progress==null?'Unknown':`${pct(progress)} ${quality==='CURRENT'?'current':'last observed'}${quality==='STALE'?' · stale':''}`;}

import {useState} from 'react';
import type {CompanionAction,CompanionToken} from '../types';
import {money,num,pct} from '../format';

export function ActionBadge({action}:{action:CompanionAction}){
 return <span className={`badge companion-action action-${action.toLowerCase()}`}>{action.replaceAll('_',' ')}</span>;
}
export function CopyMint({mint}:{mint:string}){
 const [status,setStatus]=useState(''),[fallback,setFallback]=useState(false);
 async function copy(){try{await navigator.clipboard.writeText(mint);setStatus('Copied');setFallback(false);setTimeout(()=>setStatus(''),2500);}catch{setStatus('Copy unavailable — select the mint below');setFallback(true);}}
 return <div className="copy-mint"><button className="subtle" onClick={()=>void copy()} aria-label={`Copy mint for ${mint}`}>Copy mint</button><span role="status">{status}</span>{fallback&&<input aria-label="Mint to copy manually" readOnly value={mint} onFocus={e=>e.target.select()}/>}</div>;
}
const labels:Record<string,string>={UNAVAILABLE:'Unavailable',CURRENT:'Current'};
function EvidenceList({title,items}:{title:string;items:string[]}){return items.length?<div><h4>{title}</h4><ul className="reasons">{items.map((text,i)=><li key={i}>{text}</li>)}</ul></div>:null;}
export function CompanionCard({token,onSelect,detail=false}:{token:CompanionToken;onSelect?:(mint:string)=>void;detail?:boolean}){
 const c=token.companion;
 const retreat=c.curve_progress!=null&&c.curve_peak_progress!=null?c.curve_peak_progress-c.curve_progress:0;
 return <section className={`card companion-card action-border-${c.action.toLowerCase()}`} aria-label={`FOMO Companion for ${token.name}`}>
  <div className="companion-heading"><div><div className="eyebrow">FOMO COMPANION{detail?' DECISION':''}</div><h3>{token.name||token.symbol||token.mint}</h3><code title={token.mint}>{token.mint}</code></div><ActionBadge action={c.action}/></div>
  <p className="companion-context">{c.attention} ATTENTION · Lifecycle: {c.lifecycle.replaceAll('_',' ')}</p><p>{c.summary}</p>
  <div className="companion-facts"><div><span>Current curve</span><b>{pct(c.curve_progress)} <small>{c.curve_quality.toLowerCase()}</small></b></div><div><span>Session peak</span><b>{pct(c.curve_peak_progress)}</b></div><div><span>Security</span><b>{c.security_quality}</b></div><div><span>Trade evidence</span><b>{token.features.coverage_state==='PENDING RECOVERY'?'Pending recovery · incomplete':labels[c.trade_evidence]||c.trade_evidence}</b></div><div><span>Chase risk · uncalibrated</span><b>{num(c.chase_risk,0)}</b></div><div><span>Liquidity</span><b>{money(token.liquidity)}</b></div><div><span>Buyer breadth</span><b>{c.trade_evidence==='CURRENT'?num(token.features.estimated_independent_buyers,0):'Unavailable'}</b></div><div><span>Buy/Sell flow</span><b>{c.trade_evidence==='CURRENT'&&typeof token.features.flow_ratio==='number'?`${num(token.features.flow_ratio)}×`:'Unavailable'}</b></div><div><span>Risk score</span><b>{c.security_risk_score==null?'Unavailable until verified':num(c.security_risk_score,0)}</b></div></div>
  {retreat>0&&<p className="muted">Retreated {num(retreat)} percentage points from session peak. Lifecycle is not investment quality.</p>}
  <EvidenceList title="Why watch" items={c.positive_evidence}/><EvidenceList title={c.action==='WAIT'?'Current blockers':c.action==='TOO_LATE'?'Why too late':'Core reasons'} items={c.blockers}/>
  <div className="companion-evidence"><h4>Evidence completeness</h4>{Object.entries(c.evidence_quality).map(([key,value])=><div key={key}><span>{key}</span><b>{value}</b></div>)}</div>
  <details open={c.action==='ENTRY_CANDIDATE'}><summary>$20 account economics</summary><div className="companion-facts"><div><span>Account balance</span><b>{money(token.viability.account_usd)}</b></div><div><span>Proposed position</span><b>{money(token.viability.proposed_position_usd)}</b></div><div><span>Allowed by economics</span><b>{money(token.viability.position_size_usd)}</b></div><div><span>Manual position ceiling</span><b>{money(c.manual_position_cap_usd)}</b></div><div><span>Round-trip estimate</span><b>{money(token.viability.costs?.round_trip_cost_usd)}</b></div><div><span>Break-even move</span><b>{pct(token.viability.break_even_move_pct)}</b></div></div><p className="muted">Maximum acceptable entry: UNAVAILABLE — no calibrated exit target. An economic allowance alone does not permit entry.</p><EvidenceList title="Economic blockers" items={token.viability.reasons}/></details>
  {c.action==='ENTRY_CANDIDATE'&&<><p className="manual-notice">Manual review required. No trade is executed by CRISPY WINNER. Manual position ceiling: {money(c.manual_position_cap_usd)}.</p><EvidenceList title="Current status remains valid only while" items={c.invalidation_conditions}/></>}
  <EvidenceList title="Warnings" items={c.warnings}/><div className="companion-buttons">{onSelect&&<button className="subtle" onClick={()=>onSelect(token.mint)}>View intelligence</button>}<CopyMint mint={token.mint}/></div><p className="muted">Copy this mint and search it in your trading interface.</p>
 </section>;
}
export function companionQueue(tokens:CompanionToken[],action:string,stage:string,attention:string,query:string){
 const rank=(t:CompanionToken)=>t.companion.action==='ENTRY_CANDIDATE'?0:t.companion.action==='WAIT'?({HIGH:1,MEDIUM:2,LOW:3}[t.companion.attention]):t.companion.action==='TOO_LATE'?4:5;
 return tokens.filter(t=>(action==='ALL'||t.companion.action===action)&&(stage==='ALL'||t.companion.lifecycle===stage)&&(attention==='ALL'||t.companion.attention===attention)&&`${t.name} ${t.symbol} ${t.mint}`.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>rank(a)-rank(b));
}
export function CompanionPage({tokens,examples=[],mode,onSelect}:{tokens:CompanionToken[];examples?:CompanionToken[];mode:string;onSelect:(mint:string)=>void}){
 const [action,setAction]=useState('ALL'),[stage,setStage]=useState('ALL'),[attention,setAttention]=useState('ALL'),[query,setQuery]=useState('');
 const rows=companionQueue(tokens,action,stage,attention,query);
 return <><section className="card manual-notice"><h2>FOMO COMPANION</h2><p>Manual decision support only. CRISPY WINNER does not execute trades or connect to your wallet.</p><b>Mode: {mode}</b></section>
 <div className="metrics overview">{[['ENTRY CANDIDATES',tokens.filter(t=>t.companion.action==='ENTRY_CANDIDATE').length],['HIGH-ATTENTION WAITS',tokens.filter(t=>t.companion.action==='WAIT'&&t.companion.attention==='HIGH').length],['TOO LATE',tokens.filter(t=>t.companion.action==='TOO_LATE').length],['REJECTED',tokens.filter(t=>t.companion.action==='REJECT').length]].map(([label,count])=><div className="metric" key={label}><span>{label}</span><strong>{count}</strong></div>)}</div>
 <section className="card"><h3>Action queue</h3><div className="filters"><select aria-label="Companion action" value={action} onChange={e=>setAction(e.target.value)}>{['ALL','ENTRY_CANDIDATE','WAIT','TOO_LATE','REJECT'].map(v=><option key={v} value={v}>{v.replaceAll('_',' ')}</option>)}</select><select aria-label="Companion lifecycle" value={stage} onChange={e=>setStage(e.target.value)}>{['ALL','WATCHING','MATURING','NEAR_GRADUATION','POST_GRAD_OBSERVATION'].map(v=><option key={v} value={v}>{v.replaceAll('_',' ')}</option>)}</select><select aria-label="Companion attention" value={attention} onChange={e=>setAttention(e.target.value)}>{['ALL','HIGH','MEDIUM','LOW'].map(v=><option key={v}>{v}</option>)}</select><input aria-label="Search companion tokens" placeholder="Name, symbol or mint" value={query} onChange={e=>setQuery(e.target.value)}/></div><p className="muted">Attention is monitoring priority, not a buy score. Near graduation is lifecycle progress, not investment quality.</p></section>
 <div className="companion-grid">{rows.map(t=><CompanionCard key={t.mint} token={t} onSelect={onSelect}/>)}</div>{!rows.length&&<p className="muted">No matching companion candidates.</p>}
 {mode==='DEMO'&&examples.length>0&&<><div className="banner simulated">SIMULATED UI EXAMPLES · All four actions below use synthetic evidence. These examples are excluded from scanner counts, paper trading and Strategy Lab.</div><div className="companion-grid">{examples.map(t=><CompanionCard key={t.mint} token={t}/>)}</div></>}
 <p className="muted">ENTRY CANDIDATE means the configured evidence and risk gates currently pass. It does not predict profit. Highly speculative tokens can lose most or all value.</p></>;
}

// @vitest-environment jsdom
import {afterEach,expect,test,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import {renderToStaticMarkup} from 'react-dom/server';
import type {EarlyMarket,Opportunity,Opportunities} from '../intelligenceTypes';
import {EarlyMarketPanel,OpportunityPage,speculativeReview} from './Opportunity';

afterEach(()=>{cleanup();vi.useRealTimers()});
function early():EarlyMarket {const now=Date.now()/1000;return {version:'SYNTHETIC-early-v2',observed_at:now,valid_until:now+20,classification:'EMERGING BULLISH',direction:'BULLISH',attention_rank:2,uncertainty:'VERY HIGH',basis:'CANONICAL EVENT COUNTS ONLY',speculative_review:true,windows:Object.fromEntries([10,30,60,180].map(s=>[String(s),{samples:4,buys:3,sells:1,coverage_seconds:Math.min(s,15),complete:s===10,freshness:'RECENT',units_valid:false,currency:null,raw_unique_buyers:3,independent_buyers:null,net_flow:null,flow_ratio:null,arrival_acceleration:null,buying_persistence:null,whale_share:null,coordination_suspected:null,pending_recovery:false,limitations:['Unknown amounts; incomplete long history']} ])),price:null,curve_progress:35,curve_retreat_pp:0,security:'UNKNOWN / STALE',interpretation:['Observed buy-count dominance, not a profit prediction'],missing:['Security unknown','No executed price series'],warnings:['180s incomplete'],strengthens:['Verified security and independent breadth'],invalidates:['Creator selling or loss of fresh observations'],manual_only:true,validated_edge:false}}
function opportunity():Opportunity {return {mint:'SYNTHETIC-MINT',name:'Synthetic early example',symbol:'DEMO',simulated:true,action:'DEVELOPING',attention:'LOW',ranking_score:1,score_components:{},evidence_grade:'LIMITED',headline:'DEVELOPING',summary:'Synthetic research only',why_now:[],blockers:['Strict approval unavailable'],warnings:[],missing_evidence:['180s unavailable'],lifecycle:'WATCHING',dynamics:{current:35,peak:35,retreat_pp:0,short_velocity_pp_min:null,medium_velocity_pp_min:null,acceleration_pp_min2:null,persistence:null,samples:2,coverage_seconds:15,region_seconds:15,net_progress_pp:5,quality:'INCREASING',freshness:'CURRENT'},security_quality:'UNKNOWN / STALE',trade_evidence:'UNAVAILABLE',market_context:{source:'UNAVAILABLE',status:'UNKNOWN',observed_at:null,price_usd:null,market_cap_usd:null},entry_context:{review_zone:null,maximum_chase:null,status:'UNAVAILABLE',reason:'No execution quote'},invalidation_conditions:[],manual_execution_only:true,validated_edge:false,research_version:'SYNTHETIC-v1',early_market:early()}}
function data(items:Opportunity[]):Opportunities {return {status:'UNVALIDATED RESEARCH SIGNALS',items,counts:{},signals_this_session:0,outcomes_this_session:0,pending_research:0,validated_edge:false,research_version:'SYNTHETIC-v1'}}

test('short-window speculative review is visible without changing strict WAIT',()=>{
 const o=opportunity();const before=JSON.stringify(o);
 render(<OpportunityPage mode="DEMO" examples={[o]} onSelect={()=>{}}/>);
 expect(screen.getAllByText(/SPECULATIVE REVIEW — RESEARCH ONLY/).length).toBeGreaterThan(0);
 expect(screen.getByText('NO QUALIFYING ENTRY REVIEW')).toBeTruthy();
 expect(screen.getAllByText('WAIT').length).toBeGreaterThan(0);
 expect(screen.getAllByText(/UNKNOWN \/ MIXED/).length).toBeGreaterThan(0);
 expect(screen.getAllByText(/No current supported price chart/).length).toBeGreaterThan(0);
 expect(JSON.stringify(o)).toBe(before);
});

test('expiry and disconnected monitoring never keep a bullish interpretation current',()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-25T12:00:00Z'));
 const e=early();const {rerender}=render(<EarlyMarketPanel value={e}/>);
 expect(screen.getByText(/EMERGING BULLISH/)).toBeTruthy();
 act(()=>{vi.advanceTimersByTime(21000)});
 expect(screen.getByText(/EARLY MARKET RESEARCH · DATA STALE/)).toBeTruthy();
 expect(screen.queryByText(/EMERGING BULLISH/)).toBeNull();
 rerender(<EarlyMarketPanel value={early()} live={false}/>);
 expect(screen.getByText(/EARLY MARKET RESEARCH · DATA STALE/)).toBeTruthy();
});

test('risk, lifecycle and filtering do not present rejected evidence as speculative review',()=>{
 const o=opportunity();o.action='AVOID';o.early_market={...early(),classification:'AVOID',direction:'RISK',speculative_review:false};
 expect(speculativeReview(o,Date.now()/1000)).toBe(false);
 render(<OpportunityPage data={data([o])} mode="OBSERVE" onSelect={()=>{}}/>);
 expect(screen.getAllByText('REJECT').length).toBeGreaterThan(0);
 fireEvent.click(screen.getByLabelText('SPECULATIVE REVIEW lane only'));
 expect(screen.getByText('No matching candidates. Missing evidence stays visible.')).toBeTruthy();
});

test('ordinal early ranking is separate and reversible',()=>{
 const a=opportunity(),b={...opportunity(),name:'Higher lifecycle score',mint:'SYNTHETIC-OTHER',ranking_score:90,early_market:{...early(),attention_rank:0,speculative_review:false,classification:'NEUTRAL / WAIT'}};
 render(<OpportunityPage data={data([b,a])} mode="DEMO" onSelect={()=>{}}/>);
 expect(screen.getAllByRole('region')[0].getAttribute('aria-label')).toContain(a.name);
 fireEvent.change(screen.getByLabelText('Rank opportunities'),{target:{value:'ORIGINAL'}});
 expect(screen.getAllByRole('region')[0].getAttribute('aria-label')).toContain(b.name);
});

test('React renders the DEMO research component offline',()=>{
 const markup=renderToStaticMarkup(<OpportunityPage examples={[opportunity()]} mode="DEMO" onSelect={()=>{}}/>);
 expect(markup).toContain('SPECULATIVE REVIEW');expect(markup).toContain('180s strict approval unchanged');
});

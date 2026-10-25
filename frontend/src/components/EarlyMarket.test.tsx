// @vitest-environment jsdom
import {afterEach,expect,test,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import {renderToStaticMarkup} from 'react-dom/server';
import type {EarlyMarket,Opportunity,Opportunities} from '../intelligenceTypes';
import {EarlyMarketPanel,OpportunityPage,speculativeReview} from './Opportunity';
import App from '../App';
import type {Dashboard} from '../types';

afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();Object.defineProperty(window,'scrollY',{configurable:true,value:0})});
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

test('retains expired speculative cards for historical inspection without eligibility',()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-25T12:00:00Z'));
 const o=opportunity();render(<OpportunityPage data={data([o])} mode="OBSERVE" onSelect={()=>{}}/>);
 fireEvent.click(screen.getByLabelText('SPECULATIVE REVIEW lane only'));
 const card=screen.getByRole('region',{name:`Opportunity for ${o.name}`});
 const details=card.querySelector('details')!;details.open=true;
 Object.defineProperty(window,'scrollY',{configurable:true,value:700});fireEvent.scroll(window);
 act(()=>vi.advanceTimersByTime(21000));
 expect(screen.getByRole('region',{name:`Opportunity for ${o.name}`})).toBe(card);
 expect((screen.getByLabelText('SPECULATIVE REVIEW lane only') as HTMLInputElement).checked).toBe(true);
 expect(details.open).toBe(true);
 expect(screen.getAllByText(/DATA STALE/).length).toBeGreaterThan(0);
 expect(speculativeReview(o,Date.now()/1000)).toBe(false);
 Object.defineProperty(window,'scrollY',{configurable:true,value:0});
});

test('holds reading order during scrolling updates but explicit ranking refresh applies new order',()=>{
 const a={...opportunity(),mint:'ALPHA',name:'Alpha',ranking_score:1};
 const b={...opportunity(),mint:'BETA',name:'Beta',ranking_score:2};
 const {rerender}=render(<OpportunityPage data={data([a,b])} mode="OBSERVE" onSelect={()=>{}}/>);
 const before=screen.getAllByRole('region');expect(before[0].getAttribute('aria-label')).toContain('Beta');
 Object.defineProperty(window,'scrollY',{configurable:true,value:700});fireEvent.scroll(window);
 rerender(<OpportunityPage data={data([{...a,ranking_score:90},b])} mode="OBSERVE" onSelect={()=>{}}/>);
 expect(screen.getAllByRole('region')[0]).toBe(before[0]);
 fireEvent.click(screen.getByRole('button',{name:'Refresh ranking'}));
 expect(screen.getAllByRole('region')[0].getAttribute('aria-label')).toContain('Alpha');
 Object.defineProperty(window,'scrollY',{configurable:true,value:0});
});

test('actual App SSE updates preserve filter and card identity; navigation resets the page session',()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-25T12:00:00Z'));
 class Stream {
  static instances:Stream[]=[];
  onmessage:((event:{data:string})=>void)|null=null;
  onerror:(()=>void)|null=null;
  closed=false;
  constructor(){Stream.instances.push(this)}
  close(){this.closed=true}
  send(items:Opportunity[]){this.onmessage?.({data:JSON.stringify({session:'synthetic-scroll',timestamp:Date.now()/1000,mode:'DEMO',simulated:true,tokens:[],alerts:[],paper:{equity_estimate:20,realized_net_pnl:0,trades:0},lab:{},health:{resource_pressure:false,providers:{}},opportunities:data([]),intelligence_examples:{opportunities:items,positions:[]}} as unknown as Dashboard)})}
 }
 vi.stubGlobal('EventSource',Stream);
 const scroll=vi.spyOn(window,'scrollTo').mockImplementation(()=>{});
 const app=render(<App/>);const stream=Stream.instances[0];
 const a={...opportunity(),mint:'ALPHA',name:'Alpha'},b={...opportunity(),mint:'BETA',name:'Beta'};
 act(()=>stream.send([a,b]));
 fireEvent.click(screen.getByLabelText('SPECULATIVE REVIEW lane only'));
 const card=screen.getByRole('region',{name:'Opportunity for Alpha'});
 const details=card.querySelector('details')!;fireEvent.click(within(card).getAllByText('Short-window evidence, risks and invalidation')[0]);expect(details.open).toBe(true);
 Object.defineProperty(window,'scrollY',{configurable:true,value:800});fireEvent.scroll(window);
 const root=app.container.querySelector('.layout');
 act(()=>{vi.advanceTimersByTime(2000);stream.send([{...b,ranking_score:90},a])});
 expect(app.container.querySelector('.layout')).toBe(root);
 expect(screen.getAllByRole('region')[0]).toBe(card);
 expect(details.open).toBe(true);
 expect((screen.getByLabelText('SPECULATIVE REVIEW lane only') as HTMLInputElement).checked).toBe(true);
 act(()=>vi.advanceTimersByTime(19000));
 expect(screen.getByRole('region',{name:'Opportunity for Alpha'})).toBe(card);
 expect(within(card).getAllByText(/DATA STALE/).length).toBeGreaterThan(0);
 expect(within(card).getAllByText('Historical interpretation').length).toBeGreaterThan(0);
 fireEvent.click(details.querySelector('summary')!);expect(details.open).toBe(false);
 fireEvent.click(details.querySelector('summary')!);expect(details.open).toBe(true);
 const c={...opportunity(),mint:'GAMMA',name:'Gamma'};
 act(()=>stream.send([c])); // A/B removed from the current feed; retain only historical views.
 expect(screen.getByRole('region',{name:'Opportunity for Gamma'})).toBeTruthy();
 expect(within(card).getByText(/No longer in the current feed/)).toBeTruthy();
 expect(Stream.instances).toHaveLength(1);
 expect(scroll).not.toHaveBeenCalled();expect(window.scrollY).toBe(800); // jsdom: no layout/clamping simulation.
 fireEvent.click(screen.getByRole('button',{name:'FOMO Companion'}));
 expect(screen.queryByLabelText('SPECULATIVE REVIEW lane only')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Opportunity'}));
 expect((screen.getByLabelText('SPECULATIVE REVIEW lane only') as HTMLInputElement).checked).toBe(false);
 expect(screen.queryByRole('region',{name:'Opportunity for Alpha'})).toBeNull();
 app.unmount();expect(stream.closed).toBe(true);scroll.mockRestore();
});

test('retained cards stay bounded and mode/filter changes clear historical selection',()=>{
 const rows=Array.from({length:20},(_,i)=>({...opportunity(),mint:`SYNTHETIC-${i}`,name:`Original ${i}`}));
 const {rerender}=render(<OpportunityPage data={data(rows)} mode="DEMO" onSelect={()=>{}}/>);
 fireEvent.click(screen.getByLabelText('SPECULATIVE REVIEW lane only'));
 const newest={...opportunity(),mint:'NEWEST',name:'Newest',ranking_score:999};
 rerender(<OpportunityPage data={data([newest])} mode="DEMO" onSelect={()=>{}}/>);
 expect(screen.getAllByRole('region')).toHaveLength(20);
 expect(screen.getByText(/1 matching candidates outside this reading list/)).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Refresh ranking'}));
 expect(screen.getAllByRole('region')).toHaveLength(1);
 expect(screen.getByRole('region',{name:'Opportunity for Newest'})).toBeTruthy();
 rerender(<OpportunityPage data={data([])} mode="OBSERVE" onSelect={()=>{}}/>);
 expect(screen.queryByRole('region')).toBeNull();
});

test('SSE receipt between clock ticks uses actual render time without accepting future data',()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-25T12:00:00Z'));
 const {rerender}=render(<OpportunityPage data={data([opportunity()])} mode="OBSERVE" onSelect={()=>{}}/>);
 fireEvent.click(screen.getByLabelText('SPECULATIVE REVIEW lane only'));
 // A new SSE frame arrives 500ms after the last interval tick.
 vi.setSystemTime(new Date('2026-10-25T12:00:00.500Z'));
 const updated=opportunity();
 rerender(<OpportunityPage data={data([updated])} mode="OBSERVE" onSelect={()=>{}}/>);
 expect(screen.getByText(/1 fresh speculative reviews/)).toBeTruthy();
 const future={...updated,early_market:{...updated.early_market!,observed_at:Date.now()/1000+1}};
 rerender(<OpportunityPage data={data([future])} mode="OBSERVE" onSelect={()=>{}}/>);
 expect(screen.getByText(/0 fresh speculative reviews/)).toBeTruthy();
 expect(screen.getAllByText(/DATA STALE/).length).toBeGreaterThan(0);
});

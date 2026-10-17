import type {PumpSwapHealth} from '../types';
export function PumpSwapHealthCard({health:h}:{health?:PumpSwapHealth}){
 if(!h)return null;
 return <section className="card"><h3>POST-GRAD PUMPSWAP FLOW</h3><p>{h.connected?'Connected':'Disconnected'} · verified pool subscriptions only</p><dl>
 <dt>Eligible / subscribed / capacity</dt><dd>{h.eligible_pools} / {h.subscribed_pools} / {h.capacity}</dd>
 <dt>Capacity limited / ACKs / reconnects</dt><dd>{h.capacity_limited} / {h.acks} / {h.reconnects}</dd>
 <dt>BuyEvents / SellEvents / tracked accepted</dt><dd>{h.buy_events} / {h.sell_events} / {h.accepted}</dd>
 <dt>Invalid units / duplicates / decode failures / local gaps</dt><dd>{h.invalid_units} / {h.duplicates} / {h.decode_failures} / {h.token_local_gaps}</dd>
 <dt>Post-grad CURRENT / PARTIAL / UNAVAILABLE</dt><dd>{['CURRENT','PARTIAL','UNAVAILABLE'].map(s=>h.evidence_counts[s]??0).join(' / ')}</dd>
 </dl><p>Pre-grad flow does not count toward the new 180-second post-grad window.</p></section>;
}

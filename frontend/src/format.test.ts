import {describe,it,expect} from 'vitest';
import {money,filterTokens,num,providerStatus,curveLabel} from './format';
describe('dashboard data semantics',()=>{it('missing economics is unknown',()=>{expect(money(null)).toBe('—');expect(num(undefined)).toBe('—')});it('filters canonical mints and stage',()=>{const tokens=[{mint:'mintA',name:'<script>',symbol:'A',state:'WATCHING'},{mint:'mintB',name:'Other',symbol:'B',state:'REJECTED'}];expect(filterTokens(tokens,'minta','ALL')).toHaveLength(1);expect(filterTokens(tokens,'','WATCHING')).toHaveLength(1);expect(filterTokens(tokens,'','MATURING')).toHaveLength(0)})});

it('provider activity and unavailable flow are distinct',()=>{expect(providerStatus({connected:false})).toBe('NOT USED YET');expect(providerStatus({connected:true,attempted:true})).toBe('CURRENT');expect(providerStatus({connected:false,attempted:true})).toBe('DEGRADED');expect(providerStatus({connected:false,attempted:true,rate_limited_until:200},100)).toBe('RATE LIMITED');expect(num(null)).toBe('—')});

it('curve wording separates current, stale and unknown lifecycle evidence',()=>{expect(curveLabel(60.2,'CURRENT')).toBe('60.2% current');expect(curveLabel(88.4,'STALE')).toBe('88.4% last observed · stale');expect(curveLabel(null,'UNKNOWN')).toBe('Unknown')});

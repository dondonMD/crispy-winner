import {describe,it,expect} from 'vitest';
import {money,filterTokens,num} from './format';
describe('dashboard data semantics',()=>{it('missing economics is unknown',()=>{expect(money(null)).toBe('—');expect(num(undefined)).toBe('—')});it('filters canonical mints and stage',()=>{const tokens=[{mint:'mintA',name:'<script>',symbol:'A',state:'WATCHING'},{mint:'mintB',name:'Other',symbol:'B',state:'REJECTED'}];expect(filterTokens(tokens,'minta','ALL')).toHaveLength(1);expect(filterTokens(tokens,'','WATCHING')).toHaveLength(1);expect(filterTokens(tokens,'','MATURING')).toHaveLength(0)})});

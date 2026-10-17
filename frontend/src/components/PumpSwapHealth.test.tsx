// @vitest-environment jsdom
import {render,screen,cleanup} from '@testing-library/react';
import {afterEach,expect,test} from 'vitest';
import {PumpSwapHealthCard} from './PumpSwapHealth';
afterEach(cleanup);
test('post-grad health is explicit and capacity loss stays visible',()=>{
 render(<PumpSwapHealthCard health={{connected:true,eligible_pools:30,subscribed_pools:25,capacity:25,capacity_limited:5,acks:25,reconnects:1,buy_events:7,sell_events:2,accepted:9,invalid_units:1,duplicates:0,decode_failures:1,token_local_gaps:1,evidence_counts:{CURRENT:1,PARTIAL:2,UNAVAILABLE:27}}}/>);
 expect(screen.getByText('POST-GRAD PUMPSWAP FLOW')).toBeTruthy();
 expect(screen.getByText('30 / 25 / 25')).toBeTruthy();
 expect(screen.getByText('1 / 2 / 27')).toBeTruthy();
 expect(screen.getByText(/Pre-grad flow does not count/)).toBeTruthy();
});

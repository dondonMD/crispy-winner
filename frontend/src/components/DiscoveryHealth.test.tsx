// @vitest-environment jsdom
import {render,screen,cleanup} from '@testing-library/react';
import {afterEach,expect,test} from 'vitest';
import {DiscoveryHealth} from './DiscoveryHealth';
afterEach(cleanup);
test('shows unavailable discovery truthfully',()=>{render(<DiscoveryHealth status="UNAVAILABLE" providers={{}}/>);expect(screen.getByText(/No connected discovery source/)).toBeTruthy()});
test('shows decoded launches and diagnostic counts',()=>{render(<DiscoveryHealth status="CURRENT" providers={{'Onchain discovery':{connected:true,last_event:1,last_success:1,errors:2,messages:100,launch_events:7,decoding_errors:2}}}/>);expect(screen.getByText(/creates decoded: 7/)).toBeTruthy();expect(screen.queryByText(/No connected discovery source/)).toBeNull()});
test('demo is explicit and never implies live discovery',()=>{render(<DiscoveryHealth status="UNAVAILABLE" providers={{}} simulated/>);expect(screen.getByText(/DEMO — synthetic/)).toBeTruthy();expect(screen.queryByText(/No connected discovery source/)).toBeNull()});

// @vitest-environment jsdom
// Offline artifact generator; outside the browser TypeScript program, no runtime dependency.
import {test,expect,vi} from 'vitest';
import {readFileSync,writeFileSync} from 'node:fs';
import {renderToStaticMarkup} from 'react-dom/server';
import {OpportunityPage} from '../src/components/Opportunity';

test('render the existing opportunity page from explicit offline DEMO fixtures',()=>{
 let examples=[];
 if(process.env.EARLY_MARKET_FIXTURE){const fixture=JSON.parse(readFileSync(process.env.EARLY_MARKET_FIXTURE,'utf8'));vi.useFakeTimers();vi.setSystemTime(fixture.now*1000);examples=fixture.opportunities;}
 try{
  const markup=renderToStaticMarkup(<OpportunityPage examples={examples} mode="DEMO" onSelect={()=>{}}/>);
  expect(markup).toContain('Speculative early research');expect(markup).toContain('UNVALIDATED RESEARCH SIGNALS');
  if(process.env.EARLY_MARKET_RENDER){if(!process.env.EARLY_MARKET_FIXTURE)throw new Error('Explicit DEMO fixture required');const css=readFileSync('src/style.css','utf8');writeFileSync(process.env.EARLY_MARKET_RENDER,`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>CRISPY WINNER · DEMO early research</title><style>${css}</style><body><main><h1>CRISPY WINNER · DEMO ONLY</h1><p>Offline React-rendered synthetic interface. No provider, cohort or transaction.</p>${markup}</main></body></html>`);}
 }finally{vi.useRealTimers()}
});

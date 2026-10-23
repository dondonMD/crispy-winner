// Independent pinned official quote helpers only. No builders, wallet or RPC.
const fs=require('fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const calls={};
if(input.audit){for(const [name,methods] of [['bigint-buffer',['toBigIntLE','toBigIntBE']],['toml',['parse']],['uuid',['v3','v5','v6']]]){const m=require(name);for(const k of methods){if(typeof m[k]==='function'){const f=m[k];try{m[k]=function(...a){calls[name+'.'+k]=(calls[name+'.'+k]||0)+1;return f.apply(this,a);};}catch{}}}}}
const BN=require('bn.js');
const {PublicKey}=require('@solana/web3.js');
const pump=require('@pump-fun/pump-sdk');
const amm=require('@pump-fun/pump-swap-sdk');
const {state:s,budget}=input;
const B=x=>new BN(String(x)), P=x=>new PublicKey(x);
const nonzero='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
const zero=PublicKey.default;
const baseMint=P(s.base_mint||'So11111111111111111111111111111111111111112');
const creator=s.creator?P(s.creator):(s.canonical_pool?PublicKey.findProgramAddressSync([Buffer.from('pool-authority'),baseMint.toBuffer()],P('6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'))[0]:zero);
const coinCreator=s.coin_creator?P(s.coin_creator):(s.has_creator?P(nonzero):zero);
const cv=f=>({lpFeeBps:B(f.lp_fee_bps),protocolFeeBps:B(f.protocol_fee_bps),creatorFeeBps:B(f.creator_fee_bps)});
const tiers=ts=>ts.map(t=>({marketCapLamportsThreshold:B(t.market_cap_lamports_threshold),fees:cv(t.fees)}));
const fc={flatFees:cv(s.fee_config.flat_fees),exoticFlatFees:cv(s.fee_config.exotic_flat_fees),feeTiers:tiers(s.fee_config.fee_tiers),stableFeeTiers:tiers(s.fee_config.stable_fee_tiers)};
const global={creatorFeeConfigurable:s.creator_fee_configurable};
let result;
if(s.venue==='PUMP'){
 const curve={virtualTokenReserves:B(s.base_reserve),virtualQuoteReserves:B(s.effective_quote),realTokenReserves:B(s.real_token_reserves),realQuoteReserves:B(s.real_quote_reserves),quoteMint:P(s.quote_mint),creator:coinCreator,creatorFeeBps:B(s.creator_fee_bps),isMayhemMode:s.is_mayhem_mode};
 const params={global,feeConfig:fc,mintSupply:B(s.mint_supply),bondingCurve:curve,quoteMint:P(s.quote_mint)};
 const q=pump.getBuyTokenAmountFromSolAmount({...params,amount:B(budget)});
 const cost=pump.getBuySolAmountFromTokenAmount({...params,amount:q});
 const exit=pump.getSellSolAmountFromTokenAmount({...params,amount:q});
 const gross=q.mul(B(s.effective_quote)).div(B(s.base_reserve).add(q));
 result={quantity:q.toString(),entry_cost:cost.toString(),exit:exit.toString(),gross:gross.toString()};
}else{
 const q=B(s.base_reserve).divn(1000000);
 const exit=amm.sellBaseInput({base:q,slippage:0,baseReserve:B(s.base_reserve),quoteReserve:B(s.quote_vault_reserve??s.effective_quote),virtualQuoteReserves:B(s.virtual_quote_reserves??0),feeBucketsTotal:B(s.fee_buckets_total??(s.effective_quote-s.real_quote_reserves)),globalConfig:global,feeConfig:fc,baseMintAccount:{supply:BigInt(s.mint_supply)},baseMint,creator,coinCreator,quoteMint:P(s.quote_mint),isMayhemMode:s.is_mayhem_mode,creatorFeeBps:B(s.creator_fee_bps)});
 result={quantity:q.toString(),exit:exit.uiQuote.toString(),gross:exit.internalQuoteAmountOut.toString()};
}
if(input.audit){const loaded=[...new Set(Object.keys(require.cache).map(p=>{const m=p.match(/node_modules\/((?:@[^/]+\/)?[^/]+)/g);return m?m[m.length-1].slice(13):null;}).filter(Boolean))].sort();result={quote:result,loaded,calls,native_addons:Object.keys(require.cache).filter(p=>p.endsWith('.node')).map(p=>p.split('/').pop())};}
console.log(JSON.stringify(result));

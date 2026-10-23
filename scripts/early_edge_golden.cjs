// Read-only official SDK golden generator. Never builds or sends instructions.
// Usage: NODE_PATH=<temporary pinned reference node_modules> node scripts/early_edge_golden.cjs
const fs = require('fs');
const BN = require('bn.js');
const {PublicKey} = require('@solana/web3.js');
const pump = require('@pump-fun/pump-sdk');
const amm = require('@pump-fun/pump-swap-sdk');
const B=x=>new BN(String(x));
const mint=new PublicKey('So11111111111111111111111111111111111111112');
const creator=PublicKey.findProgramAddressSync([Buffer.from('pool-authority'),mint.toBuffer()],new PublicKey('6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'))[0];
const creatorKey=new PublicKey('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v');
const fees={lp_fee_bps:20,protocol_fee_bps:95,creator_fee_bps:30};
const out=[];
for(const quote of [mint.toBase58(),creatorKey.toBase58()])for(const mayhem of [false,true])for(const override of [0,50]){
 const stable=quote===creatorKey.toBase58();
 const scale=stable?1000000:1000000000;
 const state={venue:'PUMP',quote_mint:quote,base_reserve:800000000000000,effective_quote:70*scale,
 real_token_reserves:600000000000000,real_quote_reserves:40*scale,complete:false,canonical_pool:true,
 has_creator:true,mint_supply:900000000000000,is_mayhem_mode:mayhem,creator_fee_bps:override,creator_fee_configurable:true,
 fee_config:{flat_fees:fees,exotic_flat_fees:fees,fee_tiers:[{market_cap_lamports_threshold:0,fees},
 {market_cap_lamports_threshold:85*scale,fees:{lp_fee_bps:25,protocol_fee_bps:80,creator_fee_bps:35}}],stable_fee_tiers:[]}};
 const cv=f=>({lpFeeBps:B(f.lp_fee_bps),protocolFeeBps:B(f.protocol_fee_bps),creatorFeeBps:B(f.creator_fee_bps)});
 const fc={flatFees:cv(fees),exoticFlatFees:cv(fees),feeTiers:state.fee_config.fee_tiers.map(t=>({marketCapLamportsThreshold:B(t.market_cap_lamports_threshold),fees:cv(t.fees)})),stableFeeTiers:[]};
 const curve={virtualTokenReserves:B(state.base_reserve),virtualQuoteReserves:B(state.effective_quote),realTokenReserves:B(state.real_token_reserves),
 realQuoteReserves:B(state.real_quote_reserves),quoteMint:new PublicKey(quote),creator:creatorKey,creatorFeeBps:B(override),isMayhemMode:mayhem};
 const global={creatorFeeConfigurable:true};
 for(const usd of [2,4,6]){
 const budget=Math.floor(usd/(stable?1:150)*scale);
 const params={global,feeConfig:fc,mintSupply:B(state.mint_supply),bondingCurve:curve,quoteMint:new PublicKey(quote)};
 const qty=pump.getBuyTokenAmountFromSolAmount({...params,amount:B(budget)});
 const cost=pump.getBuySolAmountFromTokenAmount({...params,amount:qty});
 const exit=pump.getSellSolAmountFromTokenAmount({...params,amount:qty});
 out.push({synthetic:true,source:'@pump-fun/pump-sdk@4.1.0',state,budget,quantity:qty.toString(),entry_cost:cost.toString(),exit:exit.toString()});
 const poolState={...state,venue:'PUMPSWAP',effective_quote:65*scale,real_quote_reserves:60*scale};
 const result=amm.sellBaseInput({base:qty,slippage:0,baseReserve:B(state.base_reserve),quoteReserve:B(70*scale),virtualQuoteReserves:B(-5*scale),feeBucketsTotal:B(10*scale),
 globalConfig:global,feeConfig:fc,baseMintAccount:{supply:BigInt(state.mint_supply)},baseMint:mint,creator,coinCreator:creatorKey,quoteMint:new PublicKey(quote),isMayhemMode:mayhem,creatorFeeBps:B(override)});
 out.push({synthetic:true,source:'@pump-fun/pump-swap-sdk@2.1.0',state:poolState,quantity:qty.toString(),exit:result.uiQuote.toString(),gross:result.internalQuoteAmountOut.toString()});
 }
}
// No writes: regeneration is an opt-in isolated comparison, never an overwrite.
process.stdout.write(JSON.stringify({synthetic:true,vectors:out}));

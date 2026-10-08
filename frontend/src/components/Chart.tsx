import {num} from '../format';
export function Chart({data,field,title,color='#61e4b6'}:{data:Record<string,number|null>[];field:string;title:string;color?:string}){
 const values=data.filter(d=>typeof d[field]==='number'); const numbers=values.map(d=>d[field] as number);
 const low=Math.min(...numbers),high=Math.max(...numbers),range=high-low||Math.max(Math.abs(high)*.02,1e-8);
 const points=numbers.map((v,i)=>`${20+i*560/Math.max(1,numbers.length-1)},${150-(v-low)*120/range}`).join(' ');
 return <section className="card chart"><div className="section-title"><h3>{title}</h3><span>{numbers.length?num(numbers.at(-1),field==='price'?7:1):'No observations'}</span></div>{numbers.length>1?<svg viewBox="0 0 600 180" role="img" aria-label={`${title} over recorded observations`}><path d="M20 30H580 M20 90H580 M20 150H580" stroke="#263340" fill="none"/><polyline points={points} fill="none" stroke={color} strokeWidth="2.5"/><text x="20" y="175" fill="#80929e" fontSize="11">Older observations</text><text x="515" y="175" fill="#80929e" fontSize="11">Latest</text></svg>:<div className="empty compact">Waiting for a second observation</div>}</section>
}

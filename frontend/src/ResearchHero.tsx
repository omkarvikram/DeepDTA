import {ArrowUpRight,ArrowRight,FlaskConical} from 'lucide-react';

export default function ResearchHero({navigate}:{navigate:(page:string)=>void}){
 return <section className="research-hero">
  <div className="hero-copy"><span className="eyebrow"><span className="hero-status-dot"/> MOLECULAR RESEARCH WORKBENCH</span>
   <h2>Build your next<br/><em>binding hypothesis.</em></h2>
   <p>Explore drug–protein affinity, compare candidates and connect your predictions with published evidence.</p>
   <div className="hero-actions"><button className="primary" onClick={()=>navigate('Affinity predictor')}><FlaskConical size={17}/>Start a prediction<ArrowUpRight size={17}/></button><button className="text-button" onClick={()=>navigate('Similar candidates')}>Explore similar candidates<ArrowRight size={15}/></button></div>
   <div className="hero-tags"><span>Davis · pKd</span><span>KIBA · score</span><span>Traceable reports</span></div>
  </div>
  <div className="molecular-study" aria-label="Conceptual illustration of a molecule and protein; not a computed binding pose" role="img">
   <svg viewBox="0 0 460 340" fill="none" aria-hidden="true">
    <defs><radialGradient id="molecule-field"><stop stopColor="currentColor" stopOpacity=".14"/><stop offset="1" stopColor="currentColor" stopOpacity="0"/></radialGradient></defs>
    <circle cx="240" cy="170" r="160" fill="url(#molecule-field)"/>
    <g className="study-guides"><circle cx="243" cy="165" r="128"/><circle cx="243" cy="165" r="94" strokeDasharray="3 8"/><path d="M243 20V310M98 165H390" strokeDasharray="2 9"/><path d="M43 51h18M52 42v18M400 279h18M409 270v18"/></g>
    <g className="protein-ribbon"><path d="M286 59C344 31 386 83 352 116C324 145 282 91 269 121C246 168 363 156 343 207C329 245 270 241 270 213C270 177 365 207 344 264C334 292 300 285 286 268"/>
     <path className="ribbon-rung" d="M280 71C293 106 365 69 366 99M274 135C293 171 339 126 351 158M280 194C305 173 337 193 341 217M281 246C299 260 333 232 345 248"/>
    </g>
    <g className="drug-structure"><path d="M95 137l32-18 32 18v37l-32 19-32-19zM159 137l32-18 32 18v37l-32 19-32-19M95 137l-27-16M223 174l26 15M127 193v31M191 119V89"/><path d="M103 142v27l24 14M167 142l24-14 24 14M191 183l24-14" className="double-bond"/>
     {[[95,137],[127,119],[159,137],[159,174],[127,193],[95,174],[191,119],[223,137],[223,174],[191,193]].map(([x,y],i)=><circle key={i} cx={x} cy={y} r="4"/>)}
    </g>
    <g className="study-atoms"><circle cx="68" cy="121" r="9"/><circle cx="127" cy="231" r="9"/><circle cx="191" cy="81" r="9"/><circle cx="249" cy="189" r="9"/></g>
    <path className="study-link" d="M248 170Q267 152 289 164" strokeDasharray="4 5"/>
    <g className="study-label"><text x="45" y="96">MOLECULE</text><text x="322" y="34">PROTEIN</text><text x="96" y="304">STRUCTURE → SEQUENCE → SCORE</text></g>
   </svg>
   <span className="study-caption">Conceptual illustration · no binding pose implied</span>
  </div>
 </section>;
}

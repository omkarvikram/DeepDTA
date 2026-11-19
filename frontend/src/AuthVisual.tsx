import {useEffect,useState} from 'react';
import {ArrowUpRight,Dna,Pause,Play} from 'lucide-react';

// Illustrative ribbon geometry, deliberately independent of scientific results.
function Helix({x,y,angle,length,radius,phase=0}:{x:number,y:number,angle:number,length:number,radius:number,phase?:number}){
 const count=156, turns=3.15, width=13;
 const edge=(i:number,side:number)=>{
  const u=i/count,t=u*Math.PI*2*turns+phase;
  const dx=radius*Math.cos(t)*Math.PI*2*turns;
  const dy=length-radius*.32*Math.sin(t)*Math.PI*2*turns;
  const norm=Math.hypot(dx,dy);
  return [radius*Math.sin(t)+side*width*dy/norm, length*(u-.5)+radius*.32*Math.cos(t)-side*width*dx/norm];
 };
 return <g transform={`translate(${x} ${y}) rotate(${angle})`}>{Array.from({length:count},(_,i)=>{
  const z=(Math.cos((i+.5)/count*Math.PI*2*turns+phase)+1)/2;
  const color=`hsl(${190+z*12} 57% ${29+z*36}%)`;
  const points=[edge(i,-.5),edge(i+1,-.5),edge(i+1,.5),edge(i,.5)];
  return <path key={i} d={`M${points.map(p=>p.join(',')).join('L')}Z`} fill={color} stroke={color} strokeWidth=".65"/>;
 })}</g>;
}

const atoms=[[424,181],[452,165],[480,181],[480,213],[452,229],[424,213],[508,165],[536,181],[536,213],[508,229],[452,133],[565,229],[396,165]];
const bonds=[[0,1],[1,2],[2,3],[3,4],[4,5],[5,0],[2,6],[6,7],[7,8],[8,9],[9,3],[1,10],[8,11],[0,12]];

export default function AuthVisual(){
 const[paused,setPaused]=useState(false),[reduced,setReduced]=useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches),[hidden,setHidden]=useState(document.hidden);
 useEffect(()=>{
  const media=window.matchMedia('(prefers-reduced-motion: reduce)');
  const motion=()=>setReduced(media.matches),visibility=()=>setHidden(document.hidden);
  media.addEventListener('change',motion);document.addEventListener('visibilitychange',visibility);
  return()=>{media.removeEventListener('change',motion);document.removeEventListener('visibilitychange',visibility)};
 },[]);
 return <section className="auth-story auth-science" data-paused={paused||reduced||hidden} aria-label="About DeepDTA">
  <div className="auth-story-top"><div className="brand"><span className="auth-brand-mark"><Dna size={25}/></span><span>DeepDTA<small>RESEARCH WORKSPACE</small></span></div><span className="auth-edition">MOLECULAR RESEARCH</span></div>
  <div className="auth-story-copy"><span className="eyebrow"><span className="auth-live-dot"/> EXPLORE THE INTERACTION</span><h1>Small molecules.<br/><em>New possibilities.</em></h1><p>Bring compounds and proteins together.<br/>Explore their affinity. Follow the evidence.</p></div>
  <figure className="auth-molecular-figure">
   <svg className="auth-molecular-scene" viewBox="0 0 640 400" fill="none" role="img" aria-labelledby="auth-molecule-title auth-molecule-description">
    <title id="auth-molecule-title">A molecular encounter</title><desc id="auth-molecule-description">An illustrative folded protein ribbon beside a small molecule. This animated artwork is not a calculated binding pose.</desc>
    <defs>
     <radialGradient id="auth-field"><stop stopColor="#4ab8c5" stopOpacity=".16"/><stop offset="1" stopColor="#4ab8c5" stopOpacity="0"/></radialGradient>
     <radialGradient id="auth-atom" cx="30%" cy="25%"><stop stopColor="#e5fff7"/><stop offset=".4" stopColor="#88e7cf"/><stop offset="1" stopColor="#227f80"/></radialGradient>
     <radialGradient id="auth-atom-blue" cx="30%" cy="25%"><stop stopColor="#e2f2ff"/><stop offset=".4" stopColor="#8ab8f2"/><stop offset="1" stopColor="#31558e"/></radialGradient>
     <linearGradient id="auth-bond" x1="390" y1="130" x2="560" y2="230" gradientUnits="userSpaceOnUse"><stop stopColor="#8bb8c4"/><stop offset="1" stopColor="#598b9c"/></linearGradient>
     <linearGradient id="auth-loop" x1="130" y1="75" x2="375" y2="310" gradientUnits="userSpaceOnUse"><stop stopColor="#65b4cc"/><stop offset=".55" stopColor="#28687f"/><stop offset="1" stopColor="#8fcfe0"/></linearGradient>
    </defs>
    <ellipse cx="300" cy="208" rx="245" ry="183" fill="url(#auth-field)"/>
    <g className="auth-scene-guides" stroke="currentColor"><circle cx="283" cy="205" r="164"/><circle cx="283" cy="205" r="124" strokeDasharray="2 8"/><path d="M283 20V383M63 205H604" strokeDasharray="2 10"/><path d="M55 58h14m-7-7v14M570 330h14m-7-7v14"/></g>
    <g className="auth-orbit" stroke="#86cbd8" strokeOpacity=".3"><ellipse cx="283" cy="205" rx="191" ry="88" transform="rotate(-27 283 205)"/><circle cx="454" cy="126" r="3" fill="#9eece0" stroke="none"/></g>
    <g className="auth-protein-float">
     <path d="M158 104C103 77 99 149 146 150S244 86 279 100S345 126 342 165M205 311C248 353 322 326 332 282M165 263C122 301 88 229 133 219" stroke="url(#auth-loop)" strokeWidth="5" strokeLinecap="round"/>
     <Helix x={185} y={184} angle={-24} length={177} radius={30}/>
     <Helix x={277} y={172} angle={28} length={161} radius={27} phase={1}/>
     <path d="M220 106C233 48 287 51 306 94M190 279C238 307 279 274 304 248" stroke="url(#auth-loop)" strokeWidth="6" strokeLinecap="round"/>
     <Helix x={239} y={262} angle={-62} length={151} radius={25} phase={2}/>
     <Helix x={330} y={226} angle={13} length={125} radius={23} phase={.5}/>
     <path d="M334 158C376 121 410 160 386 191S357 220 373 263" stroke="url(#auth-loop)" strokeWidth="5" strokeLinecap="round"/>
    </g>
    <g className="auth-ligand-float">
     <ellipse cx="481" cy="266" rx="71" ry="13" fill="#020d1a" opacity=".15"/>
     <g stroke="url(#auth-bond)" strokeWidth="5" strokeLinecap="round">{bonds.map(([a,b],i)=><path key={i} d={`M${atoms[a].join(' ')}L${atoms[b].join(' ')}`}/>)}</g>
     <g stroke="#a9d6d5" strokeWidth="1.5" opacity=".6"><path d="M431 185v24M452 173l21 12M452 221l21-12M508 173l21 12M529 209l-21 12"/></g>
     {atoms.map(([x,y],i)=><circle key={i} cx={x} cy={y} r={i>9?9:7} fill={`url(#${i===10||i===12?'auth-atom-blue':'auth-atom'})`}/>)}
    </g>
    <g className="auth-contact-halo"><circle cx="382" cy="207" r="21" stroke="#a9efe0" strokeOpacity=".5" strokeDasharray="2 5"/><circle cx="382" cy="207" r="35" stroke="#a9efe0" strokeOpacity=".12"/></g>
    <g className="auth-scene-labels"><path d="M105 340h57l27-35M485 91h-45l-17 35" fill="none" stroke="currentColor" strokeOpacity=".4"/><text x="104" y="359">PROTEIN TARGET</text><text x="443" y="78">SMALL MOLECULE</text><text x="568" y="369" className="auth-axis-label">x / y / z</text></g>
   </svg>
   <figcaption><span>Conceptual illustration · no binding pose implied</span><button type="button" className="auth-motion-control" onClick={()=>setPaused(p=>!p)} disabled={reduced} aria-label={reduced?'Animation disabled by reduced-motion preference':paused?'Play molecular animation':'Pause molecular animation'}>{paused||reduced?<Play size={12}/>:<Pause size={12}/>}<span>{reduced?'Reduced motion':paused?'Play motion':'Pause motion'}</span></button></figcaption>
  </figure>
  <div className="auth-research-path"><span><b>Explore</b> compounds & targets</span><ArrowUpRight size={16}/><span><b>Predict</b> binding affinity</span><ArrowUpRight size={16}/><span><b>Compare</b> published evidence</span></div>
  <div className="auth-story-footer"><span>BUILT FOR THE NEXT QUESTION.</span><span>For research use</span></div>
 </section>;
}

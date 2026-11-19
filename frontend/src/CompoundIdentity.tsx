import {useEffect,useState} from 'react';
import {api} from './api';
export default function CompoundIdentity({predictionId}:{predictionId:string}){
 const [data,setData]=useState<any>(null),[error,setError]=useState('');
 useEffect(()=>{setData(null);api(`/predictions/${predictionId}/compound-identity`).then(setData).catch(e=>setError(e.message))},[predictionId]);
 return <section className="compound-identity"><h3>What compound was scored?</h3>{error?<p>{error}</p>:!data?<p>Checking the exact structure against PubChem…</p>:data.matched?<><p><strong>{data.name}</strong> · {data.formula} · {data.molecular_weight} g/mol</p>{data.description&&<p>{data.description}</p>}<p><a href={data.source} target="_blank" rel="noreferrer">PubChem CID {data.cid} ↗</a></p><small>{data.note}</small></>:<p>{data.reason}</p>}</section>
}

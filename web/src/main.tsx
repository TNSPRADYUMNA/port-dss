import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type Job = {id:string; kind:string; resource:string; crane:string|null; arrival:number; start:number; end:number}
type Plan = {status:string; objective:number|null; best_bound?:number; rows:Job[]}
type Run = {id:string; seed:number; scenario:string; optimized:Plan; baseline:Plan}
const resources = ['B1','B2','Q1','Q2','G1','G2']

async function request<T>(path:string, options?:RequestInit):Promise<T> {
  const res = await fetch(path, options)
  if (!res.ok) throw new Error('Port API returned ' + res.status)
  return res.json()
}

function App() {
  const [scenario,setScenario] = useState('normal')
  const [seed,setSeed] = useState(17)
  const [runs,setRuns] = useState<Run[]>([])
  const [selected,setSelected] = useState('')
  const [mode,setMode] = useState<'optimized'|'baseline'>('optimized')
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [connected,setConnected] = useState(false)
  const refresh = () => request<Run[]>('/api/history').then(setRuns).catch(e=>setError(e.message))
  useEffect(() => {
    let socket:WebSocket
    let stopped=false
    let retry:number
    function connect() {
      const protocol=location.protocol==='https:'?'wss:':'ws:'
      socket=new WebSocket(protocol+'//'+location.host+'/api/events')
      socket.onopen=()=>{setConnected(true);refresh()}
      socket.onmessage=()=>refresh()
      socket.onclose=()=>{setConnected(false); if(!stopped) retry=window.setTimeout(connect,1500)}
    }
    refresh()
    connect()
    return ()=>{stopped=true; clearTimeout(retry); socket?.close()}
  },[])
  const run=runs.find(item=>item.id===selected) ?? runs[0]
  const plan=run?.[mode]
  const extent=Math.max(60,...(plan?.rows.map(row=>row.end)??[]))
  async function schedule(event:React.FormEvent) {
    event.preventDefault();setBusy(true);setError('')
    try {
      const result=await request<Run>('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({seed,scenario})})
      setSelected(result.id)
      await refresh()
    } catch (e) {setError(String(e))}
    finally {setBusy(false)}
  }

  return <main className="mx-auto max-w-6xl px-5 pb-12">
    <header className="flex justify-between border-b border-slate-300 py-5">
      <a href="/" className="font-bold">Port-DSS</a><span role="status">{connected?'Updates connected':'Connecting updates'}</span>
    </header>
    <h1 className="my-7 text-4xl font-bold tracking-tight md:text-5xl">Terminal schedule</h1>
    <form className="panel flex flex-wrap items-end gap-4" onSubmit={schedule}>
      <label>Scenario<select value={scenario} onChange={e=>setScenario(e.target.value)}>
        <option value="normal">Normal operations</option><option value="surge">Arrival surge</option><option value="outage">Crane outage</option>
      </select></label>
      <label>Workload seed<input value={seed} type="number" min="0" max="100000" required onChange={e=>setSeed(Number(e.target.value))} /></label>
      <button disabled={busy}>{busy?'Scheduling…':'Generate schedule'}</button>
    </form>
    {error&&<p role="alert" className="mt-4 text-red-800">{error}</p>}
    {!run&&<p className="mt-5">Generate a schedule to compare operations.</p>}
    {run&&plan&&<section className="mt-6 space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="panel">CP-SAT cost<strong>{run.optimized.objective ?? 'Unavailable'}</strong></div>
        <div className="panel">FCFS cost<strong>{run.baseline.objective}</strong></div>
        <div className="panel">Solver status<strong>{run.optimized.status}</strong></div>
      </div>
      <article className="panel">
        <div className="flex flex-wrap justify-between gap-4">
          <label>Saved run<select value={run.id} onChange={e=>setSelected(e.target.value)}>{runs.map((r,i)=><option key={r.id} value={r.id}>#{runs.length-i} · {r.scenario} · seed {r.seed}</option>)}</select></label>
          <label>Plan<select value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="optimized">CP-SAT</option><option value="baseline">First come, first served</option></select></label>
        </div>
        <h2 className="mb-2 mt-4 text-xl font-bold">Resource timeline</h2>
        <p className="mb-3 text-sm">Minutes from shift start · {extent} min shown</p>
        {resources.map(resource=><div key={resource} className="mb-2 flex gap-3">
          <span className="w-8 font-mono">{resource}</span>
          <div className="track" aria-hidden="true">
            {plan.rows.filter(job=>job.resource===resource||job.crane===resource).map(job=><div key={job.id} className={job.kind==='truck'?'bar truck':'bar'}
              title={job.id+' · '+job.start+'–'+job.end} style={{left:100*job.start/extent+'%',width:100*(job.end-job.start)/extent+'%'}}>{job.id}</div>)}
          </div>
        </div>)}
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-left text-sm"><caption className="pb-2 text-left font-bold">Scheduled jobs</caption>
            <thead><tr>{['Job','Resource','Crane','Arrival','Start','End'].map(col=><th key={col} scope="col">{col}</th>)}</tr></thead>
            <tbody>{plan.rows.slice().sort((a,b)=>a.start-b.start).map(row=><tr key={row.id}>
              <th scope="row">{row.id}</th><td>{row.resource}</td><td>{row.crane??'—'}</td><td>{row.arrival}</td><td>{row.start}</td><td>{row.end}</td></tr>)}</tbody>
          </table>
        </div>
      </article>
    </section>}
  </main>
}
createRoot(document.getElementById('root')!).render(<App/>)

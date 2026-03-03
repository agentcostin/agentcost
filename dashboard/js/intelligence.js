/* ── AgentCost: Phase 6 Intelligence Components ────────────────────────────
 * ForecastView, OptimizerView, EstimatorView
 * Depends on: React, AgentCost.api, AgentCost.MODEL_REGISTRY
 */

const {useState,useEffect} = React;
const {BarChart,Bar,XAxis,YAxis,Tooltip,ResponsiveContainer,CartesianGrid,Cell} = Recharts;
const _api = AgentCost.api;

/* ═══════════════════════════════════════════════════════════════════════════
 * FORECAST VIEW
 * ═══════════════════════════════════════════════════════════════════════════*/
function ForecastView({project}){
  const [forecast,setForecast]=useState(null);
  const [days,setDays]=useState(14);
  const [method,setMethod]=useState('ensemble');
  const [exhaustion,setExhaustion]=useState(null);
  const [budget,setBudget]=useState(500);
  const [loading,setLoading]=useState(false);

  async function load(){
    setLoading(true);
    try{
      const p=project||'default';
      const [f,e]=await Promise.all([
        _api(`/api/forecast/${p}?days=${days}&method=${method}`),
        _api(`/api/forecast/${p}/budget-exhaustion?budget=${budget}`)
      ]);
      setForecast(f); setExhaustion(e);
    }catch(e){console.error(e)}
    setLoading(false);
  }
  useEffect(()=>{load()},[project,days,method]);

  const trendColor=f=>f?.trend==='increasing'?'var(--red)':f?.trend==='decreasing'?'var(--green)':'var(--text-2)';
  const sel={padding:'.35rem .5rem',borderRadius:'var(--radius-sm)',border:'1px solid var(--border)',background:'var(--bg-2)',color:'var(--text-1)',fontSize:'.8rem'};

  return <div>
    <div className="card">
      <div className="card-header">
        <h3>📈 Cost Forecast</h3>
        <div style={{display:'flex',gap:'.5rem',alignItems:'center'}}>
          <select value={method} onChange={e=>setMethod(e.target.value)} style={sel}>
            <option value="ensemble">Ensemble</option><option value="linear">Linear</option><option value="ema">EMA</option>
          </select>
          <select value={days} onChange={e=>setDays(+e.target.value)} style={sel}>
            <option value="7">7 days</option><option value="14">14 days</option><option value="30">30 days</option><option value="90">90 days</option>
          </select>
          <button className="btn sm" onClick={load}>Refresh</button>
        </div>
      </div>
      {loading ? <div className="loading">Loading forecast…</div>
       : forecast && forecast.data_points > 1 ? <div style={{padding:'1rem'}}>
        <div className="grid g4" style={{marginBottom:'1.5rem'}}>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>TREND</div><div style={{fontSize:'1.4rem',fontWeight:700,color:trendColor(forecast)}}>{forecast.trend} {forecast.trend_pct>0?'↑':'↓'}{Math.abs(forecast.trend_pct).toFixed(1)}%</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>PREDICTED ({days}d)</div><div style={{fontSize:'1.4rem',fontWeight:700,fontFamily:'var(--mono)',color:'var(--accent)'}}>${forecast.total_predicted.toFixed(2)}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>DAILY AVG</div><div style={{fontSize:'1.4rem',fontWeight:700,fontFamily:'var(--mono)'}}>${forecast.daily_average.toFixed(2)}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>CONFIDENCE</div><div style={{fontSize:'1.4rem',fontWeight:700}}>{(forecast.confidence*100).toFixed(0)}%</div></div>
        </div>
        {forecast.forecasts.length > 0 && <div style={{height:220,marginBottom:'1rem'}}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={forecast.forecasts}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)"/>
              <XAxis dataKey="date" tick={{fontSize:10,fill:'var(--text-3)'}} tickFormatter={d=>d.slice(5)}/>
              <YAxis tick={{fontSize:10,fill:'var(--text-3)'}} tickFormatter={v=>`$${v.toFixed(2)}`}/>
              <Tooltip contentStyle={{background:'var(--bg-2)',border:'1px solid var(--border)',borderRadius:6,fontSize:'.8rem'}} formatter={v=>[`$${v.toFixed(4)}`,'Predicted']}/>
              <Bar dataKey="predicted_cost" radius={[3,3,0,0]}>
                {forecast.forecasts.map((_,i)=><Cell key={i} fill={i%2===0?'var(--accent)':'#ff7a56'}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>}
      </div>
      : <div style={{padding:'2.5rem',textAlign:'center',color:'var(--text-3)'}}>
        <div style={{fontSize:'2.5rem',marginBottom:'.5rem'}}>🔮</div>
        <div style={{fontSize:'.9rem'}}>Need at least 2 days of trace data to forecast.</div>
        <div style={{fontSize:'.8rem',marginTop:'.3rem',opacity:.7}}>Send traces via the SDK or Gateway to build forecast data.</div>
      </div>}
    </div>

    <div className="card" style={{marginTop:'1rem'}}>
      <div className="card-header">
        <h3>⏰ Budget Exhaustion</h3>
        <div style={{display:'flex',gap:'.5rem',alignItems:'center'}}>
          <span style={{fontSize:'.8rem',color:'var(--text-3)'}}>Budget: $</span>
          <input type="number" value={budget} onChange={e=>setBudget(+e.target.value)} style={{...sel,width:'80px'}}/>
          <button className="btn sm" onClick={load}>Calculate</button>
        </div>
      </div>
      {exhaustion && exhaustion.days_remaining != null ? <div style={{padding:'1rem'}}>
        <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:'1rem'}}>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>EXHAUSTION DATE</div><div style={{fontSize:'1.2rem',fontWeight:700,color:exhaustion.days_remaining<7?'var(--red)':exhaustion.days_remaining<30?'var(--amber)':'var(--green)'}}>{exhaustion.exhaustion_date}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>DAYS REMAINING</div><div style={{fontSize:'1.4rem',fontWeight:700}}>{exhaustion.days_remaining}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>BURN RATE</div><div style={{fontSize:'1.2rem',fontWeight:700,fontFamily:'var(--mono)'}}>${exhaustion.daily_burn_rate.toFixed(2)}/day</div></div>
        </div>
      </div>
      : <div style={{padding:'1.5rem',textAlign:'center',color:'var(--text-3)',fontSize:'.85rem'}}>{exhaustion?.message||'Budget not projected to be exhausted'}</div>}
    </div>
  </div>;
}


/* ═══════════════════════════════════════════════════════════════════════════
 * OPTIMIZER VIEW
 * ═══════════════════════════════════════════════════════════════════════════*/
function OptimizerView({project}){
  const [report,setReport]=useState(null);
  const [analytics,setAnalytics]=useState(null);
  const [loading,setLoading]=useState(false);

  async function load(){
    setLoading(true);
    try{
      const p=project||'default';
      const [r,a]=await Promise.all([_api(`/api/optimizer/${p}`),_api(`/api/analytics/${p}/summary`)]);
      setReport(r); setAnalytics(a);
    }catch(e){console.error(e)}
    setLoading(false);
  }
  useEffect(()=>{load()},[project]);

  const prioColor=p=>p==='high'?'var(--red)':p==='medium'?'var(--amber)':'var(--text-3)';
  const prioBg=p=>p==='high'?'var(--red-bg)':p==='medium'?'rgba(251,191,36,.08)':'transparent';

  return <div>
    <div className="card">
      <div className="card-header"><h3>⚡ Cost Optimization</h3><button className="btn sm" onClick={load}>Analyze</button></div>
      {loading ? <div className="loading">Analyzing traces…</div>
       : report ? <div style={{padding:'1rem'}}>
        <div className="grid g4" style={{marginBottom:'1.5rem'}}>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>EFFICIENCY</div><div style={{fontSize:'1.8rem',fontWeight:700,color:report.efficiency_score>80?'var(--green)':report.efficiency_score>50?'var(--amber)':'var(--red)'}}>{report.efficiency_score.toFixed(0)}<span style={{fontSize:'.8rem'}}>/100</span></div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>TOTAL SPENT</div><div style={{fontSize:'1.4rem',fontWeight:700,fontFamily:'var(--mono)'}}>${report.total_cost.toFixed(2)}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>POTENTIAL SAVINGS</div><div style={{fontSize:'1.4rem',fontWeight:700,fontFamily:'var(--mono)',color:'var(--green)'}}>${report.potential_savings_usd.toFixed(2)}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>SAVINGS %</div><div style={{fontSize:'1.4rem',fontWeight:700,color:'var(--green)'}}>{report.potential_savings_pct.toFixed(0)}%</div></div>
        </div>
        <h4 style={{marginBottom:'.8rem',fontSize:'.9rem'}}>💡 Recommendations ({report.recommendations.length})</h4>
        {report.recommendations.map((r,i)=>
          <div key={i} className="card" style={{padding:'.8rem',marginBottom:'.5rem',borderLeft:'3px solid '+prioColor(r.priority),background:prioBg(r.priority)}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
              <div>
                <span style={{fontSize:'.65rem',textTransform:'uppercase',fontWeight:700,color:prioColor(r.priority),marginRight:'.5rem'}}>{r.priority}</span>
                <span style={{fontSize:'.7rem',background:'var(--bg-2)',padding:'.15rem .4rem',borderRadius:'3px',fontFamily:'var(--mono)'}}>{r.type}</span>
              </div>
              {r.estimated_savings>0 && <span style={{fontFamily:'var(--mono)',color:'var(--green)',fontSize:'.85rem',fontWeight:600}}>Save ~${r.estimated_savings.toFixed(2)}</span>}
            </div>
            <div style={{fontSize:'.83rem',marginTop:'.4rem',color:'var(--text-2)'}}>{r.message}</div>
          </div>
        )}
      </div>
      : <div style={{padding:'2.5rem',textAlign:'center',color:'var(--text-3)'}}>
        <div style={{fontSize:'2.5rem',marginBottom:'.5rem'}}>⚡</div>
        <div>No traces to analyze. Send traces via the SDK or Gateway.</div>
      </div>}
    </div>

    {analytics && <div className="card" style={{marginTop:'1rem'}}>
      <div className="card-header"><h3>📊 Usage Summary</h3></div>
      <div style={{padding:'1rem'}}><table><tbody>
        <tr><td style={{color:'var(--text-3)'}}>Total Calls</td><td style={{fontFamily:'var(--mono)',fontWeight:600}}>{analytics.total_calls}</td></tr>
        <tr><td style={{color:'var(--text-3)'}}>Total Cost</td><td style={{fontFamily:'var(--mono)',fontWeight:600}}>${analytics.total_cost.toFixed(4)}</td></tr>
        <tr><td style={{color:'var(--text-3)'}}>Total Tokens</td><td style={{fontFamily:'var(--mono)',fontWeight:600}}>{(analytics.total_tokens||0).toLocaleString()}</td></tr>
        <tr><td style={{color:'var(--text-3)'}}>Unique Models</td><td style={{fontWeight:600}}>{analytics.unique_models}</td></tr>
        <tr><td style={{color:'var(--text-3)'}}>Error Rate</td><td style={{fontFamily:'var(--mono)',fontWeight:600,color:analytics.error_rate>0.05?'var(--red)':'var(--text-1)'}}>{(analytics.error_rate*100).toFixed(1)}%</td></tr>
        <tr><td style={{color:'var(--text-3)'}}>Avg Cost/Call</td><td style={{fontFamily:'var(--mono)',fontWeight:600}}>${analytics.avg_cost_per_call.toFixed(6)}</td></tr>
      </tbody></table></div>
    </div>}
  </div>;
}


/* ═══════════════════════════════════════════════════════════════════════════
 * ESTIMATOR VIEW
 * ═══════════════════════════════════════════════════════════════════════════*/
function EstimatorView(){
  const registry = AgentCost.MODEL_REGISTRY;
  const providers = AgentCost.getProviders();
  const tierColors = AgentCost.TIER_COLORS;
  const providerColors = AgentCost.PROVIDER_COLORS;

  const [model,setModel]=useState('claude-sonnet-4-6');
  const [prompt,setPrompt]=useState('');
  const [taskType,setTaskType]=useState('default');
  const [estimate,setEstimate]=useState(null);
  const [comparison,setComparison]=useState(null);
  const [loading,setLoading]=useState(false);
  const [showPricing,setShowPricing]=useState(false);

  const tasks=['default','chat','code','summary','analysis','creative','classification','translation'];

  async function doEstimate(){
    if(!prompt)return; setLoading(true);
    try{
      const [e,c]=await Promise.all([
        _api('/api/estimate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,prompt,task_type:taskType})}),
        _api(`/api/estimate/compare?prompt=${encodeURIComponent(prompt)}&task_type=${taskType}`)
      ]);
      setEstimate(e); setComparison(c);
    }catch(e){console.error(e)}
    setLoading(false);
  }

  const sel={width:'100%',padding:'.4rem',borderRadius:'var(--radius-sm)',border:'1px solid var(--border)',background:'var(--bg-2)',color:'var(--text-1)',fontSize:'.82rem'};

  return <div>
    {/* Estimator Input */}
    <div className="card">
      <div className="card-header"><h3>🧮 Cost Estimator</h3>
        <button className="btn sm" onClick={()=>setShowPricing(!showPricing)} style={{opacity:.8}}>{showPricing?'Hide':'Show'} Pricing Table</button>
      </div>
      <div style={{padding:'1rem'}}>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr auto',gap:'.8rem',marginBottom:'1rem',alignItems:'end'}}>
          <div>
            <label style={{fontSize:'.75rem',color:'var(--text-3)',display:'block',marginBottom:'.3rem'}}>Model</label>
            <select value={model} onChange={e=>setModel(e.target.value)} style={sel}>
              {Object.entries(providers).filter(([p])=>p!=='Local').map(([prov,models])=>
                <optgroup key={prov} label={prov}>
                  {models.map(m=><option key={m.id} value={m.id}>{m.label} — ${m.input}/${m.output}</option>)}
                </optgroup>
              )}
              <optgroup label="Local (Free)">
                {(providers['Local']||[]).slice(0,2).map(m=><option key={m.id} value={m.id}>{m.label} — Free</option>)}
              </optgroup>
            </select>
          </div>
          <div>
            <label style={{fontSize:'.75rem',color:'var(--text-3)',display:'block',marginBottom:'.3rem'}}>Task Type</label>
            <select value={taskType} onChange={e=>setTaskType(e.target.value)} style={sel}>
              {tasks.map(t=><option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <button className="btn" onClick={doEstimate} disabled={loading||!prompt} style={{height:'34px'}}>Estimate</button>
        </div>
        <textarea value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="Enter your prompt here to estimate cost before sending…"
          style={{width:'100%',minHeight:'90px',padding:'.6rem',borderRadius:'var(--radius-sm)',border:'1px solid var(--border)',background:'var(--bg-1)',color:'var(--text-1)',fontSize:'.85rem',fontFamily:'var(--mono)',resize:'vertical',boxSizing:'border-box'}}/>
      </div>
    </div>

    {/* Estimate Result */}
    {estimate && <div className="card" style={{marginTop:'1rem'}}>
      <div className="card-header"><h3>💰 {estimate.model}</h3></div>
      <div style={{padding:'1rem'}}>
        <div className="grid g4" style={{marginBottom:'1rem'}}>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>EST. COST</div><div style={{fontSize:'1.4rem',fontWeight:700,fontFamily:'var(--mono)',color:'var(--accent)'}}>${estimate.estimated_cost.toFixed(6)}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>INPUT TOKENS</div><div style={{fontSize:'1.2rem',fontWeight:700,fontFamily:'var(--mono)'}}>{estimate.estimated_input_tokens}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>OUTPUT TOKENS</div><div style={{fontSize:'1.2rem',fontWeight:700,fontFamily:'var(--mono)'}}>{estimate.estimated_output_tokens}</div></div>
          <div className="card" style={{padding:'.8rem',textAlign:'center'}}><div style={{fontSize:'.7rem',color:'var(--text-3)'}}>CONFIDENCE</div><div style={{fontSize:'1.2rem',fontWeight:700}}>{estimate.confidence}</div></div>
        </div>
        <div style={{fontSize:'.8rem',color:'var(--text-3)'}}>
          Input ${estimate.cost_breakdown.input.toFixed(6)} + Output ${estimate.cost_breakdown.output.toFixed(6)} · {estimate.pricing_source} · Task: {estimate.task_type}
        </div>
      </div>
    </div>}

    {/* Model Comparison */}
    {comparison && <div className="card" style={{marginTop:'1rem'}}>
      <div className="card-header"><h3>📊 Model Comparison</h3></div>
      <div style={{padding:'1rem'}}>
        <table><thead><tr><th>Model</th><th>Est. Cost</th><th>Input Tok</th><th>Output Tok</th><th>Source</th></tr></thead>
        <tbody>{comparison.map((c,i)=>{
          const meta = registry.find(m=>m.id===c.model);
          return <tr key={i} style={c.model===model?{background:'var(--bg-2)'}:{}}>
            <td style={{fontWeight:c.model===model?700:400}}>
              {c.model}{c.model===model?' ✓':''}
              {meta && <span style={{fontSize:'.65rem',marginLeft:'.4rem',color:providerColors[meta.provider]||'var(--text-3)'}}>{meta.provider}</span>}
            </td>
            <td style={{fontFamily:'var(--mono)',color:c.estimated_cost===0?'var(--green)':'var(--text-1)'}}>${c.estimated_cost.toFixed(6)}</td>
            <td style={{fontFamily:'var(--mono)'}}>{c.estimated_input_tokens}</td>
            <td style={{fontFamily:'var(--mono)'}}>{c.estimated_output_tokens}</td>
            <td><span style={{fontSize:'.65rem',background:c.pricing_source==='free'?'var(--green)':c.pricing_source==='known'?'var(--accent)':'var(--amber)',color:'#fff',padding:'.1rem .3rem',borderRadius:'3px'}}>{c.pricing_source}</span></td>
          </tr>;
        })}</tbody></table>
      </div>
    </div>}

    {/* Full Pricing Table (toggleable) */}
    {showPricing && <div className="card" style={{marginTop:'1rem'}}>
      <div className="card-header"><h3>💲 Full Model Pricing Reference</h3><span style={{fontSize:'.75rem',color:'var(--text-3)'}}>Updated Feb 2026 · per 1M tokens</span></div>
      <div style={{padding:'1rem'}}>
        <table>
          <thead><tr><th>Model</th><th>Provider</th><th>Input $/M</th><th>Output $/M</th><th>Tier</th><th>Context</th></tr></thead>
          <tbody>{registry.filter(m=>m.tier!=='free').map((m,i)=>
            <tr key={i}>
              <td style={{fontWeight:500}}>{m.label}</td>
              <td><span style={{color:providerColors[m.provider],fontSize:'.8rem'}}>{m.provider}</span></td>
              <td style={{fontFamily:'var(--mono)'}}>${m.input.toFixed(2)}</td>
              <td style={{fontFamily:'var(--mono)'}}>${m.output.toFixed(2)}</td>
              <td><span style={{fontSize:'.65rem',background:tierColors[m.tier]||'var(--text-3)',color:'#fff',padding:'.1rem .35rem',borderRadius:'3px'}}>{m.tier}</span></td>
              <td style={{fontFamily:'var(--mono)',fontSize:'.8rem'}}>{m.context >= 1000 ? (m.context/1000).toFixed(0)+'M' : m.context+'K'}</td>
            </tr>
          )}</tbody>
        </table>
        <div style={{marginTop:'.8rem',fontSize:'.75rem',color:'var(--text-3)'}}>
          Local models (Llama 3, Mistral, Mixtral, Qwen2) are free when self-hosted via Ollama.
        </div>
      </div>
    </div>}
  </div>;
}
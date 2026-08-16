/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import Link from "next/link";
import React from "react";
import { useEffect, useState } from "react";
import { CandlestickChart } from "./candlestick-chart";
import type { Bar } from "../lib/market";
import styles from "./research-lab.module.css";
import aiStyles from "./ai-research.module.css";

type Hypothesis = { id: string; status: string; parser_source: string; source_prompt: string; definition: Record<string, any>; version: number };
type ResearchRun = { id: string; reused: boolean; result: { mode: string; timeframe: string; occurrence_count: number; sample_count: number; summary: Record<string, number>; warning: string }; samples: Sample[] };
type Sample = { timestamp: string; direction: string; move?: number; outcome_move?: number | null; context: Bar[] };
type AIUsage = { enabled:boolean; provider:string; fast_model:string; health:string; request_count:number; cache_hit_count:number; cost_usd:number|string; monthly_budget_usd:number };
type AIExplanation = { result?:{explanation?:string;limitations?:string[];follow_up_questions?:string[]};route_status?:string;cached?:boolean;detail?:string };
type RuleValidation = {ready:boolean;status:"READY_TO_CONFIRM"|"NEEDS_RULE_COMPLETION";issues:string[];supported_primitives:string[]};
type ResearchRule = {id:string;canonical_name:string;display_name:string;rule_type:string;definition:Record<string, any>;version:number;status:string;fingerprint:string;validation?:RuleValidation};

const orderBlockQuestion = "Cari bullish order block M5 ketika trend H1 bullish untuk target $3 dan $5.";
const priceQuestion = "Apa pola yang muncul jika ada kenaikan/penurunan 500 broker points pada candle M15?";
const fomcQuestion = "Ketika ada news FOMC, apa yang biasanya terjadi pada XAUUSD?";

export function ResearchLab() {
  const [question, setQuestion] = useState(orderBlockQuestion);
  const [hypothesis, setHypothesis] = useState<Hypothesis | null>(null);
  const [message, setMessage] = useState("");
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [sampleIndex, setSampleIndex] = useState(0);
  const [aiUsage, setAiUsage] = useState<AIUsage | null>(null);
  const [aiExplanation, setAiExplanation] = useState<AIExplanation | null>(null);
  const [aiTier, setAiTier] = useState<"FAST"|"REASONING">("FAST");
  const [ruleDrafts, setRuleDrafts] = useState<ResearchRule[]>([]);
  const [ruleFlowState, setRuleFlowState] = useState<"IDLE"|"DRAFTING_WITH_AI"|"AI_DRAFT_AVAILABLE"|"AI_DRAFT_FAILED">("IDLE");
  const definition = hypothesis?.definition ?? {};
  const typed = definition.definition ?? {};
  const canRun = hypothesis?.status === "READY_FOR_RESEARCH" && definition.execution_eligibility === "ELIGIBLE";

  async function loadAiUsage(){const response=await fetch("/api/v1/ai/usage",{cache:"no-store"});if(response.ok)setAiUsage(await response.json());}
  useEffect(()=>{void loadAiUsage();},[]);

  function setTyped(key: string, value: any) {
    setHypothesis((current) => current ? { ...current, definition: { ...current.definition, definition: { ...current.definition.definition, [key]: value } } } : current);
  }

  async function build() {
    const response = await fetch("/api/v1/hypotheses/draft", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ prompt: question }) });
    const body = await response.json();
    setHypothesis(response.ok ? body : null);
    setRun(null);
    setRuleDrafts([]);
    if(response.ok&&body.definition?.research_mode==="PATTERN_COMPARISON"){
      const compiled=await fetch("/api/v1/research-contracts/compile",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({hypothesis_id:body.id})});const contract=await compiled.json();
      setRuleDrafts(contract.rules??[]);setRuleFlowState(compiled.ok?"AI_DRAFT_AVAILABLE":"AI_DRAFT_FAILED");
      setMessage(contract.status==="READY_TO_CONFIRM"?"ARKANA telah menyusun proposal penelitian yang siap Anda konfirmasi.":contract.issues?.join(" ")??contract.detail??"Definisi pola belum dapat disusun.");
    }else setMessage(response.ok ? "Interpretation created. Review its fields and availability before saving." : body.detail ?? "Could not create draft.");
  }

  async function buildWithAi(){
    const response=await fetch("/api/v1/ai/draft",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({prompt:question,tier:aiTier})}); const body=await response.json();
    setHypothesis(response.ok?body:null); setRun(null); setAiExplanation(null); setMessage(response.ok?"AI-assisted draft created. Review, edit, and save it before any research can run.":body.detail??"AI assistance is unavailable; deterministic research remains available."); void loadAiUsage();
  }

  async function save() {
    if (!hypothesis) return;
    const response = await fetch(`/api/v1/hypotheses/${hypothesis.id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ definition: hypothesis.definition }) });
    const body = await response.json();
    setHypothesis(response.ok ? body : hypothesis);
    setRun(null);
    setMessage(response.ok ? "Interpretation saved and eligibility reassessed. No research computation has run yet." : body.detail ?? "Could not save draft.");
  }

  async function execute() {
    if (!hypothesis) return;
    const response = await fetch("/api/v1/research-runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ hypothesis_id: hypothesis.id }) });
    const body = await response.json();
    if (response.ok) {
      setRun(body);
      setSampleIndex(0);
      setMessage(body.reused ? "The identical registered hypothesis and dataset were already executed; its reproducible result was reused." : "Historical descriptive scan completed. Inspect the supporting candle samples below.");
    } else setMessage(body.detail ?? "Could not execute research.");
  }

  async function explainWithAi(){if(!run)return;const response=await fetch(`/api/v1/ai/explanations/research-runs/${run.id}`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({tier:aiTier})});const body=await response.json();setAiExplanation(response.ok?body:{detail:body.detail??"AI explanation unavailable"});void loadAiUsage();}
  async function draftRulesWithAi(){if(!hypothesis)return;setRuleFlowState("DRAFTING_WITH_AI");const response=await fetch("/api/v1/ai/rule-drafts",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({hypothesis_id:hypothesis.id,tier:aiTier})});const body=await response.json();setRuleDrafts(response.ok?body.rules:[]);setRuleFlowState(response.ok?"AI_DRAFT_AVAILABLE":"AI_DRAFT_FAILED");setMessage(response.ok?"Draft definisi tersedia. Periksa parameter, edit bila perlu, lalu konfirmasi setiap definisi sebelum riset dapat dijalankan.":body.detail??"AI belum dapat membuat draft definisi.");void loadAiUsage();}
  function setAmbiguity(ruleId:string,resolution:string){setRuleDrafts(current=>current.map(rule=>rule.id===ruleId?{...rule,definition:{...rule.definition,owner_review:{...rule.definition.owner_review,ambiguity_resolution:resolution}}}:rule));}
  function setRuleParameter(ruleId:string,name:string,value:string){setRuleDrafts(current=>current.map(rule=>{if(rule.id!==ruleId)return rule;return {...rule,definition:{...rule.definition,parameters:(rule.definition.parameters??[]).map((parameter:any)=>parameter.name===name?{...parameter,proposed_value:parameter.type==="integer"||parameter.type==="number"?Number(value):value}:parameter)}};}));}
  function setRuleDefinition(ruleId:string,raw:string){try{const definition=JSON.parse(raw);setRuleDrafts(current=>current.map(rule=>rule.id===ruleId?{...rule,definition}:rule));}catch{/* keep the last valid draft while owner is typing */}}
  async function saveRule(rule:ResearchRule){const response=await fetch(`/api/v1/research-rules/${rule.id}`,{method:"PUT",headers:{"content-type":"application/json"},body:JSON.stringify({...rule,definition:rule.definition})});const body=await response.json();if(!response.ok){setMessage(body.detail??"Perubahan definisi tidak dapat disimpan.");return;}setRuleDrafts(current=>current.map(item=>item.id===rule.id?body:item));setMessage(body.validation?.ready?"Definisi siap dikonfirmasi.":"Definisi disimpan. Lengkapi item yang masih diperlukan.");}
  async function confirmRule(rule:ResearchRule){if(rule.definition.owner_review?.ambiguities?.length&&!rule.definition.owner_review?.ambiguity_resolution){setMessage("Pilih arti definisi yang akan diuji sebelum mengonfirmasi.");return;}const saved=await fetch(`/api/v1/research-rules/${rule.id}`,{method:"PUT",headers:{"content-type":"application/json"},body:JSON.stringify({...rule,definition:rule.definition})});const candidate=await saved.json();if(!saved.ok){setMessage(candidate.detail??"Perubahan definisi tidak dapat disimpan.");return;}const response=await fetch(`/api/v1/research-rules/${candidate.id}/confirm`,{method:"POST"});const body=await response.json();if(response.ok){setRuleDrafts(current=>current.map(item=>item.id===candidate.id?body:item)); if(hypothesis){const refresh=await fetch(`/api/v1/hypotheses/${hypothesis.id}`,{method:"PUT",headers:{"content-type":"application/json"},body:JSON.stringify({definition:hypothesis.definition})});if(refresh.ok)setHypothesis(await refresh.json());} setMessage(`${candidate.display_name} dikonfirmasi sebagai definisi research. Ini bukan strategy atau persetujuan trading.`);}else setMessage(body.detail??"Definisi belum siap dikonfirmasi.");}
  async function confirmAndRun(){if(!hypothesis)return;const response=await fetch("/api/v1/research-contracts/confirm-run",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({hypothesis_id:hypothesis.id,rule_ids:ruleDrafts.map(rule=>rule.id)})});const body=await response.json();if(response.ok){setRun(body);setSampleIndex(0);setMessage("Kontrak riset dikonfirmasi dan historical research selesai dijalankan.");}else setMessage(body.detail??"Kontrak riset tidak dapat dikonfirmasi.");}

  const selectedSample = run?.samples[sampleIndex];
  return <div className={styles.page}>
    <header className={styles.header}>
      <div><Link href="/" className={styles.back}>← Market &amp; Data</Link><p className={styles.eyebrow}>RESEARCH LAB · SPRINT 03</p><h1>Turn a question into inspectable historical research.</h1><p className={styles.lead}>ARKANA executes only a saved interpretation that is eligible against registered historical data. It does not create a signal, backtest, or trade instruction.</p></div>
      <span className={styles.badge}>RESEARCH ONLY</span>
    </header>
    <main className={styles.content}>
      <section className={styles.questionCard}>
        <div className={styles.cardTitle}><div><p className={styles.eyebrow}>STEP 1</p><h2>What do you want to investigate?</h2></div></div>
        <textarea aria-label="Research question" className={styles.question} value={question} onChange={(event) => setQuestion(event.target.value)} />
        <div className={styles.questionFooter}><div className={styles.examples}>Examples: <button onClick={() => setQuestion(priceQuestion)}>Price event</button><button onClick={() => setQuestion(orderBlockQuestion)}>Pattern</button><button onClick={() => setQuestion(fomcQuestion)}>FOMC event</button></div><div className={styles.actions}><button className={styles.secondary} onClick={buildWithAi}>Bantu merumuskan (AI)</button><button className={styles.primary} onClick={build}>Build interpretation →</button></div></div>
      </section>
      <section className={aiStyles.usage}><div><strong>AI Research Assistant</strong><p>{aiUsage?.enabled?`ON · ${aiUsage.provider} · ${aiUsage.fast_model} · ${aiUsage.health}`:"OFF · AI bersifat opsional. Rute pertanyaan yang sudah dikenal tetap deterministik."}</p></div><label>Mode AI<select value={aiTier} onChange={(event)=>setAiTier(event.target.value as "FAST"|"REASONING")}><option value="FAST">Hemat</option><option value="REASONING">Lanjutan (escalation)</option></select></label><span>{aiUsage?`${aiUsage.request_count} request · ${aiUsage.cache_hit_count} cache hit · biaya ${aiUsage.cost_usd}`:"Memuat status…"}</span></section>
      {message && <p className={styles.notice}>{message}</p>}
      {hypothesis && <section className={styles.draftCard}>
        <div className={styles.draftHead}><div><p className={styles.eyebrow}>STEP 2 · ARKANA&apos;S INTERPRETATION</p><h2>{definition.research_mode.replaceAll("_", " ")}</h2><p>Status: {hypothesis.status} · Version {hypothesis.version}</p></div><span className={styles.badge}>{hypothesis.status}</span></div>
        <div className={styles.summary}><span>Original question</span><strong>{hypothesis.source_prompt}</strong><span>Instrument</span><strong>{definition.instrument}</strong></div>
        <div className={styles.formGrid}>
          {definition.research_mode === "PATTERN_COMPARISON" && <><label>Timeframe<select value={typed.timeframe ?? "M15"} onChange={(event) => setTyped("timeframe", event.target.value)}>{["M1", "M5", "M15", "M30", "H1", "H4"].map((value) => <option key={value}>{value}</option>)}</select></label><label>Pengukuran<strong>Jumlah kejadian historis pada seluruh data terdaftar</strong></label></>}
          {definition.research_mode === "PATTERN_TO_OUTCOME" && <><label>Pattern<input value={typed.pattern ?? ""} onChange={(event) => setTyped("pattern", event.target.value)} /></label><label>Pattern timeframe<select value={typed.pattern_timeframe ?? "M5"} onChange={(event) => setTyped("pattern_timeframe", event.target.value)}>{["M1", "M5", "M15", "M30", "H1", "H4"].map((value) => <option key={value}>{value}</option>)}</select></label><label className={styles.wide}>Deterministic pattern definition<textarea value={typed.deterministic_pattern_definition ?? ""} onChange={(event) => setTyped("deterministic_pattern_definition", event.target.value)} /></label></>}
          {definition.research_mode === "PRICE_EVENT_TO_PATTERN" && <><label>Timeframe<select value={typed.timeframe ?? "M15"} onChange={(event) => setTyped("timeframe", event.target.value)}>{["M1", "M5", "M15", "M30", "H1", "H4"].map((value) => <option key={value}>{value}</option>)}</select></label><label>Movement threshold<input type="number" step="any" value={typed.movement_threshold ?? ""} onChange={(event) => setTyped("movement_threshold", event.target.valueAsNumber)} /></label><label>Movement unit<select value={typed.movement_unit ?? "BROKER_POINTS"} onChange={(event) => setTyped("movement_unit", event.target.value)}><option value="BROKER_POINTS">Broker points (needs normalization)</option><option value="PRICE">Explicit XAUUSD price units</option></select></label><label>Broker normalization<input value={typed.broker_normalization_state ?? ""} onChange={(event) => setTyped("broker_normalization_state", event.target.value)} /></label></>}
          {definition.research_mode === "EXTERNAL_EVENT_TO_MARKET" && <><label>External event<input value={typed.external_event_type ?? ""} onChange={(event) => setTyped("external_event_type", event.target.value)} /></label><label>Event source<input value={typed.event_source ?? ""} onChange={(event) => setTyped("event_source", event.target.value)} /></label><label>Pre-event window<input value={typed.pre_event_window ?? ""} onChange={(event) => setTyped("pre_event_window", event.target.value)} /></label></>}
        </div>
        {definition.research_mode === "PATTERN_COMPARISON" && <section className={styles.ruleArea}><div><strong>Definisi pola</strong><p>ARKANA memahami pertanyaan Anda, tetapi konsep berikut belum memiliki definisi deterministik untuk dihitung.</p></div><div className={styles.ruleNames}>{(typed.unresolved_concepts ?? []).map((concept:string)=><span key={concept}>{concept.replaceAll("_"," ")}: Perlu definisi</span>)}</div>{ruleFlowState!=="IDLE"&&<span className={styles.badge}>{ruleFlowState}</span>}{(typed.unresolved_concepts ?? []).length>0&&<button className={styles.secondary} disabled={ruleFlowState==="DRAFTING_WITH_AI"} onClick={draftRulesWithAi}>{ruleFlowState==="DRAFTING_WITH_AI"?"Menyusun draft…":"Bantu definisikan dengan AI"}</button>}{ruleDrafts.map(rule=><article className={styles.ruleCard} key={rule.id}><div><strong>{rule.display_name} · v{rule.version}</strong><p>{rule.definition.owner_review?.plain_language_definition ?? "Draft deterministic rule. Review technical detail before confirming."}</p>{rule.validation && <div className={rule.validation.ready?styles.notice:styles.warning}><strong>{rule.validation.ready?"Siap dikonfirmasi":"Belum siap digunakan"}</strong>{rule.validation.issues.map(issue=><span key={issue}>{issue}</span>)}</div>}<div className={styles.parameterGrid}>{(rule.definition.parameters??[]).map((parameter:any)=><label key={parameter.name}>{parameter.meaning??parameter.name}<input aria-label={`${rule.display_name} ${parameter.name}`} disabled={parameter.editable===false||rule.status!=="DRAFT"} type={parameter.type==="integer"||parameter.type==="number"?"number":"text"} value={parameter.proposed_value} onChange={(event)=>setRuleParameter(rule.id,parameter.name,event.target.value)}/><small>{parameter.unit??""}</small></label>)}</div>{rule.definition.owner_review?.ambiguities?.length>0&&<label className={styles.ambiguity}>Pilih arti yang akan diuji<select value={rule.definition.owner_review?.ambiguity_resolution??""} onChange={(event)=>setAmbiguity(rule.id,event.target.value)}><option value="">Pilih definisi…</option>{rule.definition.owner_review.ambiguities.map((option:string)=><option key={option} value={option}>{option}</option>)}</select></label>}</div><details><summary>Detail analisis teknis</summary><textarea aria-label={`${rule.display_name} technical definition`} disabled={rule.status!=="DRAFT"} value={JSON.stringify(rule.definition,null,2)} onChange={(event)=>setRuleDefinition(rule.id,event.target.value)}/></details><div className={styles.actions}><span className={styles.badge}>{rule.status}</span><button className={styles.secondary} disabled={rule.status!=="DRAFT"} onClick={()=>saveRule(rule)}>Simpan & periksa</button><button className={styles.primary} disabled={rule.status!=="DRAFT"||!rule.validation?.ready} onClick={()=>confirmRule(rule)}>Gunakan definisi ini</button></div></article>)}</section>}
        <div className={styles.warning}><strong>Availability assessment · {definition.execution_eligibility}</strong>{definition.data_requirements.map((item: any) => <span key={item.name}>{item.name}: {item.availability}</span>)}{definition.analytical_capability_requirements?.map((item: any) => <span key={item.id}>{item.id}: {item.available ? "AVAILABLE" : "NOT SUPPORTED"}</span>)}</div>
        <div className={styles.saveBar}><span>{definition.research_mode==="PATTERN_COMPARISON"&&ruleDrafts.length?"Konfirmasi ini menyimpan versi definisi yang immutable lalu menjalankan riset historis.":"Save after editing to refresh eligibility. A run becomes available only for READY FOR RESEARCH / ELIGIBLE."}</span><div className={styles.actions}><button className={styles.secondary} onClick={save}>Save interpretation</button>{definition.research_mode==="PATTERN_COMPARISON"&&ruleDrafts.length?<button className={styles.primary} disabled={!ruleDrafts.every(rule=>rule.validation?.ready)} onClick={confirmAndRun}>Konfirmasi & Jalankan Research</button>:<button className={styles.primary} disabled={!canRun} onClick={execute}>Run eligible research</button>}</div></div>
      </section>}
      {run && <section className={styles.resultsCard}><div className={styles.draftHead}><div><p className={styles.eyebrow}>STEP 3 · HISTORICAL RESULT</p><h2>{run.result.occurrence_count} matching occurrences</h2><p>{run.result.timeframe} · {run.result.sample_count} stored samples · run {run.id.slice(0, 8)}</p></div><div className={styles.actions}><button className={styles.secondary} onClick={explainWithAi}>Jelaskan hasil ini (AI)</button><span className={styles.badge}>COMPLETED</span></div></div><p className={styles.resultWarning}>{run.result.warning}</p>{aiExplanation&&<section className={aiStyles.explanation}><strong>Penjelasan AI · {aiExplanation.route_status??"UNAVAILABLE"}</strong>{aiExplanation.detail?<p>{aiExplanation.detail}</p>:<><p>{aiExplanation.result?.explanation}</p><p><strong>Batasan:</strong> {aiExplanation.result?.limitations?.join(" ")}</p><p><strong>Pertanyaan lanjutan:</strong> {aiExplanation.result?.follow_up_questions?.join(" · ")}</p></>}</section>}<div className={styles.summaryMetrics}>{Object.entries(run.result.summary).map(([label, value]) => <span key={label}><strong>{value}</strong>{label.replaceAll("_", " ")}</span>)}</div>{run.samples.length > 0 ? <div className={styles.sampleArea}><div className={styles.sampleList}>{run.samples.map((sample, index) => <button key={`${sample.timestamp}-${index}`} className={index === sampleIndex ? styles.sampleActive : styles.sampleButton} onClick={() => setSampleIndex(index)}><strong>#{index + 1} · {sample.direction}</strong><span>{sample.timestamp}</span><span>{sample.move !== undefined ? `Move ${sample.move.toFixed(3)}` : sample.outcome_move === null ? "Outcome unavailable" : `Next move ${sample.outcome_move?.toFixed(3)}`}</span></button>)}</div><div className={styles.chartPanel}><p className={styles.eyebrow}>VISUAL VALIDATION · SAMPLE #{sampleIndex + 1}</p><CandlestickChart bars={selectedSample?.context ?? []} /><p>Showing the matching candle with up to two preceding and two following registered bars. Timestamp: {selectedSample?.timestamp}.</p></div></div> : <p className={styles.empty}>No occurrences met the saved definition in this registered dataset. This is a result, not an error.</p>}</section>}
    </main>
  </div>;
}

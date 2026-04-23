import { CheckCircle2, AlertTriangle, AlertCircle, MessageSquare, ChevronDown, BookOpen, GitMerge, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { cn } from '../lib/utils';
import type { PipelineState } from '../App';

export default function PipelineStages({ pipeline }: { pipeline: PipelineState }) {
  const { status, query, sprint1Data, sprint2Data, sprint3Data, sprint4Data } = pipeline;

  return (
    <div className="flex-1 w-full max-w-4xl mx-auto overflow-y-auto px-4 py-8 space-y-6 scroll-smooth">
      {/* Query Header */}
      <h2 className="text-2xl font-medium text-white mb-8">{query}</h2>

      {status === 'starting' && (
        <div className="flex items-center gap-3 text-primary animate-pulse">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Starting debate pipeline...</span>
        </div>
      )}

      {/* SPRINT 1: Proponent Answer & Claims & Graph */}
      {sprint1Data && (
        <>
          <PipelineCard 
            title="Proponent Answer" 
            icon={<MessageSquare className="w-5 h-5 text-gray-400" />}
          >
            <p className="text-gray-300 leading-relaxed text-sm">
              {sprint1Data.proponent_answer}
            </p>
          </PipelineCard>

          <PipelineCard 
            title="Atomic Claims" 
            icon={<GitMerge className="w-5 h-5 text-gray-400" />}
          >
            <ul className="space-y-3">
              {sprint1Data.claims.map((c: any) => (
                <ClaimItem key={c.id} id={c.id} text={c.text} />
              ))}
            </ul>
          </PipelineCard>

          <PipelineCard 
            title="Dependency Graph" 
            icon={<GitMerge className="w-5 h-5 text-gray-400" />}
          >
            <div className="bg-[#141414] rounded-lg p-4 font-mono text-sm text-gray-300 border border-[#2A2A2A]">
              {sprint1Data.dependency_graph.map((edge: any) => (
                <div key={edge.parent} className="mb-4 last:mb-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-primary font-bold">{edge.parent}</span>
                    {edge.children?.length > 0 && <span className="text-gray-500">depends on</span>}
                  </div>
                  {edge.children?.length > 0 && (
                    <div className="pl-6 border-l-2 border-[#2A2A2A] space-y-2">
                      {edge.children.map((child: string) => (
                        <div key={child} className="flex items-center gap-2">
                          <span className="text-gray-400 font-bold">{child}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </PipelineCard>
        </>
      )}

      {status === 'sprint1' && (
        <div className="flex items-center gap-3 text-yellow-500 animate-pulse">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Adversarial debate in progress...</span>
        </div>
      )}

      {/* SPRINT 2: Debate Log */}
      {sprint2Data && sprint2Data.debate_rounds && (
        <PipelineCard 
          title="Debate Log" 
          icon={<MessageSquare className="w-5 h-5 text-gray-400" />}
        >
          <div className="space-y-4">
            {sprint2Data.debate_rounds.map((round: any, idx: number) => (
              <DebateRound 
                key={idx}
                round={idx + 1} 
                skeptic={round.skeptic_argument}
                proponent={round.proponent_rebuttal}
              />
            ))}
          </div>
        </PipelineCard>
      )}

      {status === 'sprint2' && (
        <div className="flex items-center gap-3 text-blue-500 animate-pulse">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Evidence retrieval & verification in progress...</span>
        </div>
      )}

      {/* SPRINT 3: Evidence & Verdicts */}
      {sprint3Data && (
        <>
          <PipelineCard 
            title="Retrieval Log & Evidence" 
            icon={<BookOpen className="w-5 h-5 text-gray-400" />}
          >
            <div className="space-y-3">
              {sprint3Data.retrieval_log.map((log: any, idx: number) => (
                <div key={idx} className="mb-4">
                  <h4 className="text-sm font-semibold text-gray-300 mb-2">Claim {log.claim_id}</h4>
                  {log.results.map((res: any, rIdx: number) => (
                    <EvidenceCard 
                      key={rIdx}
                      claimId={log.claim_id} 
                      source={res.url || 'Search'} 
                      tier="Evidence"
                      status="green"
                      text={res.snippet || res.content}
                    />
                  ))}
                </div>
              ))}
            </div>
          </PipelineCard>

          <PipelineCard 
            title="Moderator Verdicts" 
            icon={<CheckCircle2 className="w-5 h-5 text-gray-400" />}
          >
            <div className="space-y-2">
              {sprint3Data.verdicts.map((v: any, idx: number) => {
                let statusColor: 'green' | 'yellow' | 'red' = 'yellow';
                if (v.status === 'CORRECT') statusColor = 'green';
                if (v.status === 'INCORRECT') statusColor = 'red';
                
                return (
                  <VerdictItem 
                    key={idx} 
                    id={v.claim_id} 
                    status={statusColor} 
                    verdict={`[${v.status}] ${v.reasoning}`} 
                  />
                );
              })}
            </div>
          </PipelineCard>
        </>
      )}

      {status === 'sprint3' && (
        <div className="flex items-center gap-3 text-purple-500 animate-pulse">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Synthesizing final transparency report...</span>
        </div>
      )}

      {/* SPRINT 4: Final Synthesized Answer */}
      {sprint4Data && sprint4Data.synthesis && (
        <div className="mt-8 bg-[#1A1A1A] border-l-4 border-primary rounded-r-2xl p-6 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-r from-primary/5 to-transparent pointer-events-none" />
          <h3 className="text-sm font-semibold text-primary uppercase tracking-wider mb-2">Final Synthesized Answer</h3>
          <p className="text-gray-200 text-sm leading-relaxed relative z-10 whitespace-pre-wrap">
            {sprint4Data.synthesis.revised_answer}
          </p>
        </div>
      )}
      
      {pipeline.error && (
        <div className="p-4 bg-red-500/10 border border-red-500/50 rounded-xl text-red-400 text-sm">
          Error: {pipeline.error}
        </div>
      )}
    </div>
  );
}

function PipelineCard({ title, icon, children }: { title: string, icon: React.ReactNode, children: React.ReactNode }) {
  return (
    <div className="bg-[#1A1A1A] border border-[#2A2A2A] rounded-2xl overflow-hidden shadow-sm">
      <div className="px-5 py-4 border-b border-[#2A2A2A] flex items-center gap-3 bg-[#141414]">
        {icon}
        <h3 className="text-white font-medium">{title}</h3>
      </div>
      <div className="p-5">
        {children}
      </div>
    </div>
  );
}

function ClaimItem({ id, text }: { id: string, text: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="bg-[#2A2A2A] text-gray-300 text-xs font-bold px-2 py-1 rounded mt-0.5">{id}</span>
      <p className="text-sm text-gray-300">{text}</p>
    </div>
  );
}

function DebateRound({ round, skeptic, proponent }: { round: number, skeptic: string, proponent: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-[#2A2A2A] rounded-xl overflow-hidden">
      <button 
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 bg-[#141414] flex items-center justify-between hover:bg-[#1A1A1A] transition-colors"
      >
        <span className="text-sm font-medium text-gray-200">Round {round}</span>
        <ChevronDown className={cn("w-4 h-4 text-gray-500 transition-transform", expanded && "rotate-180")} />
      </button>
      {expanded && (
        <div className="p-4 space-y-4 bg-[#1A1A1A]">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-red-400 uppercase tracking-wider">Skeptic</span>
            <p className="text-sm text-gray-300 pl-3 border-l-2 border-red-500/30 whitespace-pre-wrap">{skeptic}</p>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-blue-400 uppercase tracking-wider">Proponent</span>
            <p className="text-sm text-gray-300 pl-3 border-l-2 border-blue-500/30 whitespace-pre-wrap">{proponent}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function EvidenceCard({ claimId, source, tier, status, text }: { claimId: string, source: string, tier: string, status: 'green'|'yellow'|'red', text: string }) {
  return (
    <div className="bg-[#141414] rounded-xl p-4 border border-[#2A2A2A] mt-2">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className="bg-[#2A2A2A] text-gray-300 text-xs font-bold px-2 py-0.5 rounded flex-shrink-0">{claimId}</span>
          <span className="text-xs font-medium text-gray-400 truncate max-w-[200px]" title={source}>{source}</span>
        </div>
        <span className="text-xs font-medium text-gray-500 bg-[#2A2A2A] px-2 py-0.5 rounded-full flex-shrink-0">{tier}</span>
      </div>
      <div className="flex items-start gap-3">
        {status === 'green' && <CheckCircle2 className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />}
        {status === 'yellow' && <AlertCircle className="w-4 h-4 text-yellow-500 mt-0.5 flex-shrink-0" />}
        {status === 'red' && <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />}
        <p className="text-sm text-gray-300 line-clamp-3">{text}</p>
      </div>
    </div>
  );
}

function VerdictItem({ id, status, verdict }: { id: string, status: 'green'|'yellow'|'red', verdict: string }) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-[#141414] border border-[#2A2A2A]">
      <span className={cn(
        "text-xs font-bold px-2 py-1 rounded mt-0.5 flex-shrink-0",
        status === 'green' ? "bg-green-500/20 text-green-400" :
        status === 'yellow' ? "bg-yellow-500/20 text-yellow-400" :
        "bg-red-500/20 text-red-400"
      )}>
        {id}
      </span>
      <p className="text-sm text-gray-300 mt-0.5 whitespace-pre-wrap">{verdict}</p>
    </div>
  );
}

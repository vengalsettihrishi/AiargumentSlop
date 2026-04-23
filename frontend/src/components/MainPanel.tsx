import { MessageSquare, GitMerge, FileCheck } from 'lucide-react';
import { cn } from '../lib/utils';

export default function MainPanel() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 max-w-4xl mx-auto w-full">
      <div className="w-12 h-12 bg-[#1A1A1A] rounded-2xl flex items-center justify-center mb-8 border border-[#2A2A2A] shadow-lg">
        <MessageSquare className="w-6 h-6 text-primary" />
      </div>
      
      <h1 className="text-4xl md:text-5xl font-medium text-white text-center tracking-tight mb-4">
        Enter a claim or question to<br/>initiate structured debate
      </h1>
      
      <p className="text-gray-400 text-center max-w-lg mb-12 text-sm md:text-base">
        This system evaluates responses through multi-agent debate, claim verification, and evidence retrieval.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full mb-12">
        <FeatureCard 
          icon={<MessageSquare className="w-5 h-5 text-primary" />}
          title="Multi-Agent Debate"
          description="Claims are challenged across multiple rounds to ensure robustness."
        />
        <FeatureCard 
          icon={<GitMerge className="w-5 h-5 text-primary" />}
          title="Claim Graph Analysis"
          description="Arguments are decomposed into atomic claims with dependency tracking."
        />
        <FeatureCard 
          icon={<FileCheck className="w-5 h-5 text-primary" />}
          title="Evidence & Credibility"
          description="All claims are verified using tiered source credibility scoring."
        />
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-6 text-sm">
        <button className="text-primary border-b-2 border-primary pb-1 font-medium">All</button>
        <button className="text-gray-400 hover:text-gray-200 pb-1 font-medium transition-colors">Debate</button>
        <button className="text-gray-400 hover:text-gray-200 pb-1 font-medium transition-colors">Evidence</button>
        <button className="text-gray-400 hover:text-gray-200 pb-1 font-medium transition-colors">Verdict</button>
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description }: { icon: React.ReactNode, title: string, description: string }) {
  return (
    <div className="bg-[#141414] border border-[#2A2A2A] p-6 rounded-2xl hover:border-[#3A3A3A] transition-colors flex flex-col items-center text-center group">
      <div className="mb-4 p-3 bg-[#1A1A1A] rounded-xl group-hover:bg-[#2A2A2A] transition-colors">
        {icon}
      </div>
      <h3 className="text-white font-medium mb-2">{title}</h3>
      <p className="text-gray-400 text-xs leading-relaxed">{description}</p>
    </div>
  );
}

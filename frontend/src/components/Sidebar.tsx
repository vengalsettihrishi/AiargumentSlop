import { MessageSquare, Folder, Plus, SlidersHorizontal, ChevronDown, CheckCircle2, AlertCircle, AlertTriangle } from 'lucide-react';
import { cn } from '../lib/utils';

export default function Sidebar() {
  return (
    <div className="w-[300px] h-screen bg-[#141414] border-r border-[#2A2A2A] p-4 flex flex-col hidden md:flex">
      {/* Header */}
      <div className="flex items-center justify-between mb-8 px-2">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-[#2A2A2A] rounded-lg flex items-center justify-center">
            <MessageSquare className="w-4 h-4 text-gray-300" />
          </div>
          <span className="font-medium text-white">Debate System</span>
        </div>
        <button className="text-gray-400 hover:text-white">
          <SlidersHorizontal className="w-4 h-4" />
        </button>
      </div>

      {/* Search mock */}
      <div className="bg-[#1A1A1A] rounded-lg px-3 py-2 flex items-center gap-2 mb-6 border border-[#2A2A2A]">
        <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <span className="text-sm text-gray-500">Search debates...</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        <SidebarSection title="Active Debates">
          <SidebarItem title="UBI Economic Impact" status="yellow" active />
          <SidebarItem title="Nuclear Fusion Feasibility" status="green" />
        </SidebarSection>

        <SidebarSection title="Completed Analyses">
          <SidebarItem title="Carbon Tax Efficacy" status="green" />
          <SidebarItem title="AI Copyright Law" status="green" />
          <SidebarItem title="Remote Work Productivity" status="green" />
        </SidebarSection>

        <SidebarSection title="High Conflict Cases">
          <SidebarItem title="Autonomous Weapons" status="red" />
          <SidebarItem title="Social Media Regulation" status="red" />
        </SidebarSection>
      </div>

      {/* Footer CTA */}
      <div className="pt-4 mt-auto">
        <button className="w-full bg-primary hover:bg-primaryHover text-black font-medium py-3 px-4 rounded-xl flex items-center justify-between transition-colors">
          <span>Start New Debate</span>
          <div className="bg-white/20 p-1 rounded-md">
            <Plus className="w-4 h-4" />
          </div>
        </button>
      </div>
    </div>
  );
}

function SidebarSection({ title, children }: { title: string, children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <div className="flex items-center justify-between px-2 mb-2">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{title}</span>
        <button className="text-gray-500 hover:text-gray-300">
          <ChevronDown className="w-3 h-3" />
        </button>
      </div>
      <div className="space-y-1">
        {children}
      </div>
    </div>
  );
}

function SidebarItem({ title, status, active }: { title: string, status: 'green' | 'yellow' | 'red', active?: boolean }) {
  return (
    <button
      className={cn(
        "w-full text-left px-3 py-2.5 rounded-lg flex items-center justify-between group transition-colors",
        active ? "bg-[#2A2A2A]" : "hover:bg-[#1A1A1A]"
      )}
    >
      <div className="flex items-center gap-3 overflow-hidden">
        {status === 'green' && <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />}
        {status === 'yellow' && <AlertCircle className="w-4 h-4 text-yellow-500 flex-shrink-0" />}
        {status === 'red' && <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />}
        <span className={cn(
          "text-sm truncate",
          active ? "text-white font-medium" : "text-gray-400 group-hover:text-gray-200"
        )}>
          {title}
        </span>
      </div>
      <div className="w-5 h-5 rounded-md hover:bg-[#3A3A3A] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
        <span className="text-gray-400 text-xs tracking-widest leading-none">...</span>
      </div>
    </button>
  );
}

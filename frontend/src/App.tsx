import { useState } from 'react';
import Sidebar from './components/Sidebar';
import MainPanel from './components/MainPanel';
import InputField from './components/InputField';
import PipelineStages from './components/PipelineStages';
import { fetchDebateStream } from './lib/api';

export type PipelineState = {
  status: 'idle' | 'starting' | 'sprint1' | 'sprint2' | 'sprint3' | 'sprint4' | 'complete' | 'error';
  query: string | null;
  sprint1Data: any | null;
  sprint2Data: any | null;
  sprint3Data: any | null;
  sprint4Data: any | null;
  error: string | null;
};

function App() {
  const [pipeline, setPipeline] = useState<PipelineState>({
    status: 'idle',
    query: null,
    sprint1Data: null,
    sprint2Data: null,
    sprint3Data: null,
    sprint4Data: null,
    error: null,
  });

  const handleStartDebate = async (query: string) => {
    setPipeline({
      status: 'starting',
      query,
      sprint1Data: null,
      sprint2Data: null,
      sprint3Data: null,
      sprint4Data: null,
      error: null,
    });

    try {
      for await (const msg of fetchDebateStream(query)) {
        console.log("Received event:", msg.event);
        if (msg.event === 'status') {
          // just connecting
        } else if (msg.event === 'sprint1') {
          setPipeline(prev => ({ ...prev, status: 'sprint1', sprint1Data: msg.data }));
        } else if (msg.event === 'sprint2') {
          setPipeline(prev => ({ ...prev, status: 'sprint2', sprint2Data: msg.data }));
        } else if (msg.event === 'sprint3') {
          setPipeline(prev => ({ ...prev, status: 'sprint3', sprint3Data: msg.data }));
        } else if (msg.event === 'sprint4') {
          setPipeline(prev => ({ ...prev, status: 'sprint4', sprint4Data: msg.data, status: 'complete' }));
        } else if (msg.event === 'error') {
          setPipeline(prev => ({ ...prev, status: 'error', error: msg.data.error }));
        }
      }
    } catch (err: any) {
      setPipeline(prev => ({ ...prev, status: 'error', error: err.message }));
    }
  };

  return (
    <div className="flex h-screen w-full bg-background overflow-hidden font-sans text-gray-200">
      <Sidebar />

      <div className="flex-1 relative flex flex-col min-w-0 bg-[#0A0A0A]">
        <div className="absolute top-0 right-0 w-full h-full bg-radial-glow pointer-events-none" />

        <div className="flex-1 flex flex-col relative z-10 overflow-hidden">
          {pipeline.status === 'idle' ? (
            <MainPanel />
          ) : (
            <PipelineStages pipeline={pipeline} />
          )}
          
          <div className="w-full bg-gradient-to-t from-[#0A0A0A] via-[#0A0A0A] to-transparent pt-8">
            <InputField onSubmit={handleStartDebate} disabled={pipeline.status !== 'idle' && pipeline.status !== 'complete' && pipeline.status !== 'error'} />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;

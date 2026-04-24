'use client';
import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { useState, useEffect } from 'react';
import { getJobStatus, getToken } from '@/lib/api';
import WaitlistForm from '@/components/WaitlistForm';
import Navbar from '@/components/Navbar';
import SoundwaveLoader from '@/components/SoundwaveLoader';

interface ClipResult {
  id: string;
  url?: string;
  status: string;
  error?: string;
}

function ResultContent() {
  const searchParams = useSearchParams();
  const jobIdsParam = searchParams?.get('jobIds') || '';
  const jobIds = jobIdsParam ? jobIdsParam.split(',') : [];

  const [clips, setClips] = useState<ClipResult[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (jobIds.length === 0) {
      setLoading(false);
      return;
    }

    let isPolling = true;

    const fetchResults = async () => {
      let anyPending = false;
      const updatedClips = await Promise.all(
        jobIds.map(async (id) => {
          try {
            const res = await getJobStatus(id);
            if (res.success && res.data) {
               const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api';
               const apiHost = apiBase.replace(/\/api$/, '');
               if (res.data.status === 'completed' && res.data.downloadUrl) {
                  const token = getToken();
                  return { id, status: 'completed', url: `${apiHost}${res.data.downloadUrl}${token ? `?token=${token}` : ''}` };
               } else if (res.data.status === 'failed') {
                  return { id, status: 'failed', error: res.data.errorMessage || 'Clip generation failed' };
               } else {
                  anyPending = true;
                  return { id, status: res.data.status };
               }
            } else {
               return { id, status: 'failed', error: 'Failed to fetch status' };
            }
          } catch {
             return { id, status: 'failed', error: 'Network error' };
          }
        })
      );

      if (isPolling) {
         setClips(updatedClips);
         if (anyPending) {
            setTimeout(fetchResults, 2000);
         } else {
            setLoading(false);
         }
      }
    };

    fetchResults();

    return () => {
      isPolling = false;
    };
  }, [jobIdsParam]); // Relying entirely on param change keeps lifecycle safe

  return (
    <div className="min-h-screen bg-background text-text">
      <Navbar backHref="/creator-tools/video-chopper" backLabel="← Back" />

      <div className="max-w-6xl mx-auto py-12 sm:py-16 px-4 sm:px-6 text-center cp-fade-in">
        <div className="cp-slide-up" style={{ animationDelay: '0.1s' }}>
          <h1 className="text-3xl sm:text-4xl font-bold mb-3 sm:mb-4 text-white">Your Clips are Ready.</h1>
          <p className="text-muted mb-8 sm:mb-10 text-sm sm:text-base">Download your finalized high-quality clips below.</p>
        </div>

        {clips.length === 0 && loading ? (
          <div className="bg-card border border-border p-8 sm:p-10 rounded-xl mb-10 sm:mb-12 cp-slide-up" style={{ animationDelay: '0.15s' }}>
            <div className="mx-auto mb-6 w-12 flex items-center justify-center">
              <SoundwaveLoader />
            </div>
            <div className="text-muted text-sm">Finalizing your clips…</div>
          </div>
        ) : jobIds.length === 0 ? (
          <div className="bg-card border border-red-500/20 p-8 sm:p-10 rounded-xl mb-10 sm:mb-12 cp-slide-up" style={{ animationDelay: '0.15s' }}>
            <p className="text-red-400">No job IDs provided</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-10 sm:mb-12 cp-slide-up" style={{ animationDelay: '0.15s' }}>
             {clips.map((clip, i) => (
                <div key={clip.id} className="bg-card border border-border p-4 sm:p-6 rounded-xl flex flex-col h-full items-center">
                    <h3 className="text-lg font-bold mb-4 text-white w-full text-left border-b border-white/10 pb-2">Clip {i + 1}</h3>
                    {clip.status === 'completed' && clip.url ? (
                        <>
                           <video 
                             src={clip.url} 
                             controls 
                             className="w-full h-auto max-h-[350px] object-contain bg-black mb-6 rounded-lg shadow-lg flex-1 ring-1 ring-white/10" 
                           />
                           <a 
                             href={clip.url} 
                             download={`ClipPods_Export_${i+1}.mp4`} 
                             className="w-full text-center bg-white text-black px-6 py-3 rounded-lg tracking-wide font-semibold transition-all duration-200 hover:bg-gray-200 mt-auto shadow-md"
                           >
                             Download Clip
                           </a>
                        </>
                    ) : clip.status === 'failed' ? (
                        <div className="w-full flex-1 flex flex-col items-center justify-center border border-red-500/20 bg-red-500/5 rounded-lg mb-6 p-6">
                           <svg className="w-8 h-8 text-red-500 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                           <p className="text-red-400 text-sm font-medium">{clip.error}</p>
                        </div>
                    ) : (
                        <div className="w-full flex-1 flex flex-col items-center justify-center border border-white/5 bg-white/5 rounded-lg mb-6 p-6">
                           <div className="w-10 mb-4 opacity-70"><SoundwaveLoader /></div>
                           <p className="text-muted text-sm font-medium tracking-wide">Processing chunk...</p>
                        </div>
                    )}
                </div>
             ))}
          </div>
        )}

        <div className="mt-16 sm:mt-20 pt-8 sm:pt-10 border-t border-border cp-slide-up" style={{ animationDelay: '0.3s' }}>
          <h2 className="text-xl sm:text-2xl font-bold mb-3 sm:mb-4">You&apos;ll Love ClipPods AI Clipper</h2>
          <p className="text-sm text-muted mb-6 max-w-lg mx-auto">
            Skip the manual chop. Our AI smart clipper detects highlights and packages shorts automatically.
          </p>
          <div className="max-w-md mx-auto">
            <WaitlistForm />
          </div>
        </div>
      </div>
    </div>
  );
}

// Wrap in Suspense because useSearchParams requires it in Next.js 14+
export default function ResultPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-col items-center justify-center min-h-screen bg-background">
        <div className="cp-spinner mb-4">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" strokeOpacity="0.15"/>
            <path d="M12 2a10 10 0 0 1 10 10" />
          </svg>
        </div>
        <div className="text-muted text-sm">Loading result…</div>
      </div>
    }>
      <ResultContent />
    </Suspense>
  );
}

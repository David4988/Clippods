'use client';
import { Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useState, useRef, useCallback, useEffect } from 'react';
import TimelineEditor from '@/components/TimelineEditor';
import Navbar from '@/components/Navbar';
import SoundwaveLoader from '@/components/SoundwaveLoader';
import AuthModal from '@/components/AuthModal';
import { createClipJob, getJobStatus, getToken, getVideoInfo } from '@/lib/api';

function EditorContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const videoId = searchParams?.get('videoId') || '';

  const [duration, setDuration] = useState(0);
  const [videoCapHeight, setVideoCapHeight] = useState(1080);
  const [segments, setSegments] = useState([{ id: '1', start: 0, end: 10 }]);
  const [quality, setQuality] = useState('720p');
  const [ratio, setRatio] = useState('original');
  const [format, setFormat] = useState('video');
  const [mode, setMode] = useState('accurate');

  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [suggestions, setSuggestions] = useState<any[]>([]);

  useEffect(() => {
    if (videoId) {
      getVideoInfo(videoId).then(res => {
        if (res.success && res.data?.suggestions) {
            setSuggestions(res.data.suggestions);
        }
      });
    }
  }, [videoId]);

  const videoRef = useRef<HTMLVideoElement>(null);

  const pollJob = useCallback(async (jobIds: string[]) => {
    const interval = setInterval(async () => {
      try {
        let totalProgress = 0;
        let allCompleted = true;
        let anyFailed = false;
        let failMessage = '';

        for (const id of jobIds) {
          const res = await getJobStatus(id);
          if (res.success && res.data) {
            totalProgress += res.data.progress;
            if (res.data.status === 'failed') {
              anyFailed = true;
              failMessage = res.data.errorMessage || 'Unknown segment error';
            }
            if (res.data.status !== 'completed' && res.data.status !== 'failed') {
              allCompleted = false;
            }
          }
        }

        const avgProgress = Math.floor(totalProgress / jobIds.length);
        setProgress(avgProgress);
        
        if (avgProgress < 30) setStatusText('Extracting segments...');
        else if (avgProgress < 60) setStatusText('Encoding media tracks...');
        else if (avgProgress < 99) setStatusText('Finalizing Output...');

        if (anyFailed) {
            clearInterval(interval);
            alert('Processing failed: ' + failMessage);
            setIsProcessing(false);
        } else if (allCompleted) {
            clearInterval(interval);
            setStatusText('Complete!');
            setTimeout(() => {
              router.push(`/creator-tools/video-chopper/result?jobIds=${jobIds.join(',')}`);
            }, 600);
        }
      } catch {
        // Keep polling on transient errors
      }
    }, 2000);
  }, [router]);

  const handleChop = async () => {
    if (!getToken()) {
      setShowAuthModal(true);
      return;
    }
    if (!videoId) {
      alert('No video loaded');
      return;
    }

    // Validate segments
    for (const seg of segments) {
        if (seg.end <= seg.start) {
            alert('A trim segment has an invalid length (end time must be after start time).');
            return;
        }
    }

    setIsProcessing(true);
    setProgress(0);
    setStatusText('Creating clip jobs...');
    try {
      const res = await createClipJob({ 
        videoId, 
        segments,
        quality,
        ratio,
        format,
        mode 
      });
      if (res.success && res.data?.jobIds) {
        pollJob(res.data.jobIds);
      } else {
        alert(res.message || 'Failed to create clips');
        setIsProcessing(false);
      }
    } catch {
      alert('Error creating clips');
      setIsProcessing(false);
    }
  };

  const addSegment = () => {
      if (segments.length >= 3) return;
      const last = segments[segments.length - 1];
      const newStart = Math.min(last.end + 5, duration - 10);
      const newEnd = Math.min(newStart + 10, duration);
      setSegments([...segments, { id: Math.random().toString(36).substr(2, 6), start: newStart, end: newEnd }]);
  };

  const removeSegment = (id: string) => {
      if (segments.length <= 1) return;
      setSegments(segments.filter(s => s.id !== id));
  };

  const updateSeg = (id: string, field: 'start' | 'end', val: number) => {
      setSegments(segments.map(s => {
          if (s.id !== id) return s;
          const updated = { ...s, [field]: val };
          if (field === 'start' && updated.start >= updated.end) updated.start = Math.max(0, updated.end - 1);
          if (field === 'end' && updated.end <= updated.start) updated.end = Math.min(duration, updated.start + 1);
          return updated;
      }));
  };

  return (
    <div className="min-h-screen bg-background text-text">
      <Navbar backHref="/creator-tools/video-chopper" backLabel="← Back" />

      <div className="max-w-5xl mx-auto py-8 sm:py-10 px-4 sm:px-6 cp-fade-in flex flex-col md:flex-row gap-6">
        
        {/* Left Side: Viewer & Timeline */}
        <div className="flex-1 w-full cp-slide-up" style={{ animationDelay: '0.1s' }}>
            <h1 className="text-2xl sm:text-3xl font-bold mb-2">Configure Final Clip</h1>
            <p className="text-muted text-sm mb-6 sm:mb-8">Assemble your viral clip manually.</p>

            <div className="bg-card border border-border p-2 sm:p-3 rounded-xl mb-5 sm:mb-6 cp-slide-up h-[300px] sm:h-[400px] w-full flex items-center justify-center bg-black" style={{ animationDelay: '0.15s' }}>
            <video
                ref={videoRef}
                src={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api'}/output/stream/${videoId}`}
                controls
                className="w-full h-full rounded-lg object-contain bg-black"
                onLoadedMetadata={() => {
                if (videoRef.current) {
                    const dur = videoRef.current.duration;
                    const vH = videoRef.current.videoHeight;
                    setDuration(dur);
                    setVideoCapHeight(vH);
                    
                    const safeInitialEnd = Math.min(10, dur);
                    if (segments.length === 1 && segments[0].end === 10) {
                       setSegments([{ id: segments[0].id, start: 0, end: safeInitialEnd }]);
                    }
                    
                    if (vH < 720) setQuality('480p');
                }
                }}
            />
            </div>

            {/* Suggested Highlights Overlay */}
            {suggestions.length > 0 && (
                <div className="bg-surface border border-blue-500/20 bg-blue-500/5 p-4 sm:p-5 rounded-xl mb-5 sm:mb-6 cp-slide-up shadow-sm" style={{ animationDelay: '0.2s' }}>
                    <div className="flex items-center gap-2 mb-3">
                        <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        <span className="font-semibold text-sm text-blue-100">Smart Highlights Detected</span>
                    </div>
                    <div className="flex gap-3 overflow-x-auto pb-2 shrink-0 cp-scrollbar-hide">
                        {suggestions.map((sug, i) => (
                            <button 
                                key={i} 
                                onClick={() => {
                                    setSegments([{ id: Math.random().toString(36).substr(2, 6), start: sug.startTime, end: sug.endTime }]);
                                    if(videoRef.current) {
                                        videoRef.current.currentTime = sug.startTime;
                                        videoRef.current.play();
                                    }
                                }}
                                className="flex flex-col text-left shrink-0 min-w-[150px] bg-[#111] hover:bg-[#1a1a1a] border border-blue-500/30 hover:border-blue-400 p-3 rounded-lg transition-all"
                            >
                                <span className="text-xs font-bold text-white mb-1.5">{sug.label}</span>
                                <span className="text-[10px] uppercase tracking-wider text-blue-400/80 mb-2 font-semibold">
                                    {sug.confidence ? `${Math.round(sug.confidence * 100)}% Confidence` : 'Auto-detected'}
                                </span>
                                <span className="text-xs text-muted font-mono">{new Date(sug.startTime * 1000).toISOString().substr(14, 5)} - {new Date(sug.endTime * 1000).toISOString().substr(14, 5)}</span>
                            </button>
                        ))}
                    </div>
                </div>
            )}
            
            <div className="bg-surface border border-border p-4 sm:p-6 rounded-xl mb-5 sm:mb-6 cp-slide-up shadow-sm" style={{ animationDelay: '0.25s' }}>
                <div className="flex justify-between items-center mb-4">
                    <span className="font-semibold text-sm">Trim Sequences ({segments.length}/3)</span>
                </div>
                
                <div className="flex flex-col gap-4">
                    {segments.map((seg, idx) => (
                        <div key={seg.id} className="relative bg-[#111]/60 border border-white/10 p-4 rounded-xl">
                            {segments.length > 1 && (
                                <button onClick={() => removeSegment(seg.id)} className="absolute -top-2 -right-2 w-[22px] h-[22px] bg-red-500/90 hover:bg-red-500 rounded-full text-white text-[10px] font-bold flex items-center justify-center shadow-lg transition-colors">×</button>
                            )}
                            <div className="flex justify-between items-center mb-3">
                                <span className="text-[11px] uppercase tracking-wider text-muted font-bold">Clip Segment {idx + 1}</span>
                                <button onClick={() => { if(videoRef.current){ videoRef.current.currentTime = seg.start; videoRef.current.play(); } }} className="text-[11px] text-blue-400 hover:text-blue-300">▶ Preview</button>
                            </div>
                            <TimelineEditor
                                duration={duration}
                                startTime={seg.start}
                                endTime={seg.end}
                                onStartChange={(v) => updateSeg(seg.id, 'start', v)}
                                onEndChange={(v) => updateSeg(seg.id, 'end', v)}
                            />
                        </div>
                    ))}
                </div>

                {segments.length < 3 && (
                    <button onClick={addSegment} className="mt-4 w-full py-2.5 border border-dashed border-white/20 rounded-lg text-sm text-muted hover:border-white/50 hover:text-white transition-all flex items-center justify-center gap-2">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>
                        Add sequence
                    </button>
                )}
            </div>
        </div>

        {/* Right Side: Options & Actions */}
        <div className="w-full md:w-[320px] cp-slide-up" style={{ animationDelay: '0.2s' }}>
            <div className="bg-surface border border-border p-5 rounded-xl mb-4 shadow-sm sticky top-[100px]">
                <h3 className="text-sm font-semibold mb-4 pb-2 border-b border-border">Export Settings</h3>
                
                <div className="flex flex-col gap-4">
                    <div>
                        <label className="block text-xs text-muted mb-1.5 font-medium">Export Format</label>
                        <select value={format} onChange={e => setFormat(e.target.value)} className="bg-[#111] border border-border p-2.5 rounded-lg text-white w-full outline-none focus:border-white/40 transition-colors text-sm">
                            <option value="video">Optimized Video (.mp4)</option>
                            <option value="audio">Audio Only (.m4a)</option>
                        </select>
                    </div>

                    {format === 'video' && (
                        <>
                            <div>
                                <label className="block text-xs text-muted mb-1.5 font-medium flex justify-between">
                                    Quality 
                                    <span className="text-[10px] text-blue-400">Source: {videoCapHeight}p</span>
                                </label>
                                <select value={quality} onChange={e => setQuality(e.target.value)} className="bg-[#111] border border-border p-2.5 rounded-lg text-white w-full outline-none focus:border-white/40 transition-colors text-sm">
                                    <option value="240p">240p Low</option>
                                    <option value="360p">360p Standard</option>
                                    {videoCapHeight >= 480 && <option value="480p">480p SD</option>}
                                    {videoCapHeight >= 720 && <option value="720p">720p HD</option>}
                                    {videoCapHeight >= 1080 && <option value="1080p">1080p FHD</option>}
                                    {videoCapHeight >= 2160 && <option value="4K">4K Ultra</option>}
                                </select>
                            </div>

                            <div>
                                <label className="block text-xs text-muted mb-1.5 font-medium">Aspect Ratio</label>
                                <select value={ratio} onChange={e => setRatio(e.target.value)} className="bg-[#111] border border-border p-2.5 rounded-lg text-white w-full outline-none focus:border-white/40 transition-colors text-sm">
                                    <option value="original">Original (No crop)</option>
                                    <option value="1:1">1:1 Square (Instagram)</option>
                                    <option value="9:16">9:16 Vertical (Shorts/Reels)</option>
                                    <option value="16:9">16:9 Landscape (YouTube)</option>
                                    <option value="4:5">4:5 Portrait</option>
                                </select>
                            </div>
                        </>
                    )}
                </div>

                <div className="mt-8">
                    {isProcessing ? (
                        <div className="bg-[#111] border border-border p-5 rounded-xl text-center shadow-lg">
                            <div className="mx-auto mb-4 w-10 flex items-center justify-center">
                                <SoundwaveLoader />
                            </div>
                            <div className="text-white text-sm font-semibold mb-1">{statusText || 'Processing...'}</div>
                            <div className="text-muted text-xs mb-3">{progress}% remaining stable sync</div>
                            <div className="w-full bg-black rounded-full h-1.5 border border-border overflow-hidden">
                                <div className="bg-blue-500 h-full rounded-full transition-all duration-300 ease-out" style={{ width: `${progress}%` }} />
                            </div>
                        </div>
                    ) : (
                        <button
                            onClick={handleChop}
                            disabled={!videoId || duration === 0}
                            className="w-full bg-white text-black py-3 rounded-lg font-bold text-sm transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed cp-btn-hover cp-cta-glow shadow-md hover:bg-gray-100"
                        >
                            Generate Clip Now
                        </button>
                    )}
                </div>
            </div>
        </div>
      </div>

      {showAuthModal && (
        <AuthModal 
          onClose={() => setShowAuthModal(false)} 
          onSuccess={() => {
            setShowAuthModal(false);
            handleChop();
          }} 
        />
      )}
    </div>
  );
}

// Wrap in Suspense because useSearchParams requires it in Next.js 14+
export default function EditorPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-col items-center justify-center min-h-screen bg-background">
        <div className="cp-spinner mb-4">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" strokeOpacity="0.15"/>
            <path d="M12 2a10 10 0 0 1 10 10" />
          </svg>
        </div>
        <div className="text-muted text-sm">Loading editor elements…</div>
      </div>
    }>
      <EditorContent />
    </Suspense>
  );
}

// Force recompile to clear SWC cache
'use client';

import { useMemo } from 'react';

export default function HowItWorksAnimation() {
  // Generate consistent waveform heights on mount
  const waveHeights = useMemo(() => {
    const heights: number[] = [];
    for (let i = 0; i < 50; i++) {
      // Use deterministic pseudo-random based on index
      const seed = Math.sin(i * 127.1 + 311.7) * 43758.5453;
      heights.push(20 + (seed - Math.floor(seed)) * 70);
    }
    return heights;
  }, []);

  return (
    <>
      {/* Inject animation styles as raw CSS scoped under #hiw-anim */}
      <style dangerouslySetInnerHTML={{ __html: `
        /* ═══════════════════════════════════════════════════
           HIW Animation — 16s Premium Workflow Loop
           Scoped under #hiw-anim to avoid conflicts
           ═══════════════════════════════════════════════════ */

        #hiw-anim {
          perspective: 1200px;
        }

        /* ─── STAGE 1: Video Playback ─── */
        #hiw-anim .hiw-progress-fill {
          animation: hiwProgress 16s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes hiwProgress {
          0%   { width: 0%; opacity: 1; }
          16%  { width: 100%; opacity: 1; }
          18%, 48% { width: 100%; opacity: 0; }
          49%  { width: 0%; opacity: 1; }
          85%  { width: 100%; opacity: 1; }
          88%, 100% { width: 100%; opacity: 0; }
        }

        #hiw-anim .hiw-play-icon {
          animation: hiwPlayIcon 16s ease-in-out infinite;
        }
        @keyframes hiwPlayIcon {
          0%, 14% { opacity: 1; transform: scale(1); }
          18%, 88% { opacity: 0; transform: scale(0.7); }
          92%, 100% { opacity: 1; transform: scale(1); }
        }

        #hiw-anim .hiw-video-shimmer {
          animation: hiwShimmer 16s ease-in-out infinite;
        }
        @keyframes hiwShimmer {
          0%   { background-position: -200% 0; }
          20%  { background-position: 200% 0; }
          100% { background-position: 200% 0; }
        }

        /* ─── STAGE 2: Overlay & Waveform Morph ─── */
        #hiw-anim .hiw-overlay-system {
          animation: hiwSystemFade 16s ease-in-out infinite;
        }
        @keyframes hiwSystemFade {
          0%, 15% { opacity: 0; visibility: hidden; }
          18%, 88% { opacity: 1; visibility: visible; }
          92%, 100% { opacity: 0; visibility: hidden; }
        }

        #hiw-anim .hiw-waveform-overlay {
          animation: hiwBackdropSoft 16s ease-in-out infinite;
        }
        @keyframes hiwBackdropSoft {
          0%, 42% { opacity: 0.95; }
          50%, 86% { opacity: 0.45; backdrop-filter: blur(6px); }
          92%, 100% { opacity: 0; }
        }

        #hiw-anim .hiw-inactive-bars {
          animation: hiwInactiveFade 16s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes hiwInactiveFade {
          0%, 40% { opacity: 1; filter: blur(0px); transform: scaleY(1); }
          48%, 86% { opacity: 0; filter: blur(4px); transform: scaleY(0.8); }
          92%, 100% { opacity: 1; filter: blur(0px); transform: scaleY(1); }
        }

        /* ─── STAGE 3 & 4: Highlight Boxes Stack ─── */
        #hiw-anim .hiw-hl-box {
          position: absolute;
          overflow: hidden;
        }

        #hiw-anim .hiw-hl-1 { animation: hiwMove1 16s cubic-bezier(0.4, 0, 0.2, 1) infinite; }
        #hiw-anim .hiw-hl-2 { animation: hiwMove2 16s cubic-bezier(0.4, 0, 0.2, 1) infinite; }
        #hiw-anim .hiw-hl-3 { animation: hiwMove3 16s cubic-bezier(0.4, 0, 0.2, 1) infinite; }

        @keyframes hiwMove1 {
          0%, 25% { opacity: 0; left: 27.05%; top: 50%; transform: translate(-50%, -50%) scale(0.9); width: 14%; height: 50px; border-radius: 8px; border: 1px solid rgba(59,130,246,0); background: transparent; }
          29%, 42% { opacity: 1; left: 27.05%; top: 50%; transform: translate(-50%, -50%) scale(1); width: 14%; height: 60px; border-radius: 10px; border: 1px solid rgba(59,130,246,0.7); background: rgba(59,130,246,0.12); box-shadow: 0 0 15px rgba(59,130,246,0.2), inset 0 0 10px rgba(59,130,246,0.1); }
          50%, 86% { opacity: 1; left: 50%; top: 25%; transform: translate(-50%, -50%) scale(1.03); width: 68%; height: 64px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.12); background: rgba(15,15,15,0.95); box-shadow: 0 20px 40px rgba(0,0,0,0.6); backdrop-filter: blur(12px); }
          90%, 100% { opacity: 0; left: 50%; top: 25%; transform: translate(-50%, -50%) scale(0.95); width: 68%; height: 64px; border-radius: 12px; }
        }

        @keyframes hiwMove2 {
          0%, 26% { opacity: 0; left: 50.85%; top: 50%; transform: translate(-50%, -50%) scale(0.9); width: 14%; height: 50px; border-radius: 8px; border: 1px solid rgba(59,130,246,0); background: transparent; }
          30%, 42% { opacity: 1; left: 50.85%; top: 50%; transform: translate(-50%, -50%) scale(1); width: 14%; height: 60px; border-radius: 10px; border: 1px solid rgba(59,130,246,0.7); background: rgba(59,130,246,0.12); box-shadow: 0 0 15px rgba(59,130,246,0.2), inset 0 0 10px rgba(59,130,246,0.1); }
          51%, 86% { opacity: 1; left: 50%; top: 50%; transform: translate(-50%, -50%) scale(1.03); width: 68%; height: 64px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.12); background: rgba(15,15,15,0.95); box-shadow: 0 20px 40px rgba(0,0,0,0.6); backdrop-filter: blur(12px); }
          91%, 100% { opacity: 0; left: 50%; top: 50%; transform: translate(-50%, -50%) scale(0.95); width: 68%; height: 64px; border-radius: 12px; }
        }

        @keyframes hiwMove3 {
          0%, 27% { opacity: 0; left: 74.65%; top: 50%; transform: translate(-50%, -50%) scale(0.9); width: 14%; height: 50px; border-radius: 8px; border: 1px solid rgba(59,130,246,0); background: transparent; }
          31%, 42% { opacity: 1; left: 74.65%; top: 50%; transform: translate(-50%, -50%) scale(1); width: 14%; height: 60px; border-radius: 10px; border: 1px solid rgba(59,130,246,0.7); background: rgba(59,130,246,0.12); box-shadow: 0 0 15px rgba(59,130,246,0.2), inset 0 0 10px rgba(59,130,246,0.1); }
          52%, 86% { opacity: 1; left: 50%; top: 75%; transform: translate(-50%, -50%) scale(1.03); width: 68%; height: 64px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.12); background: rgba(15,15,15,0.95); box-shadow: 0 20px 40px rgba(0,0,0,0.6); backdrop-filter: blur(12px); }
          92%, 100% { opacity: 0; left: 50%; top: 75%; transform: translate(-50%, -50%) scale(0.95); width: 68%; height: 64px; border-radius: 12px; }
        }

        /* ─── STAGE 5: Crossfade Inside Boxes ─── */
        #hiw-anim .hiw-hl-state-1 {
          animation: hiwFadeOutState1 16s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes hiwFadeOutState1 {
          0%, 43%  { opacity: 1; transform: scale(1); }
          47%, 100% { opacity: 0; transform: scale(0.8); }
        }

        #hiw-anim .hiw-hl-state-2 {
          animation: hiwFadeInState2 16s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes hiwFadeInState2 {
          0%, 46%  { opacity: 0; transform: translateY(8px) scale(0.95); }
          52%, 86% { opacity: 1; transform: translateY(0) scale(1); }
          90%, 100% { opacity: 0; transform: translateY(-8px) scale(0.95); }
        }

        #hiw-anim .hiw-clip-progress {
          animation: hiwClipProgress 16s ease-out infinite;
          transform-origin: left;
        }
        @keyframes hiwClipProgress {
          0%, 53%  { transform: scaleX(0); }
          82%, 86% { transform: scaleX(1); }
          90%, 100% { transform: scaleX(0); }
        }

        /* ─── STAGE 6: Player Card Float ─── */
        #hiw-anim .hiw-player {
          animation: hiwPlayer 16s cubic-bezier(0.4, 0, 0.2, 1) infinite;
          transform-style: preserve-3d;
        }
        @keyframes hiwPlayer {
          0%, 15%   { transform: translateY(0) scale(1); }
          22%, 86%  { transform: translateY(-8px) scale(1.01); box-shadow: 0 40px 80px rgba(0,0,0,0.6); }
          92%, 100% { transform: translateY(0) scale(1); }
        }
      `}} />

      <div id="hiw-anim" className="w-full max-w-3xl mx-auto my-12">
        {/* ════════════════════════════════════════════
            Main Video Player Card
            ════════════════════════════════════════════ */}
        <div 
          className="hiw-player relative w-full rounded-2xl overflow-hidden border border-white/10"
          style={{ background: '#0a0a0a', boxShadow: '0 20px 50px rgba(0,0,0,0.4)' }}
        >
          {/* Video Surface */}
          <div className="relative w-full" style={{ aspectRatio: '16/9' }}>
            <div className="absolute inset-0" style={{ background: 'linear-gradient(135deg, #111 0%, #0a0a0a 50%, #111 100%)' }} />
            <div className="hiw-video-shimmer absolute inset-0 opacity-30" style={{ background: 'linear-gradient(90deg, transparent 30%, rgba(255,255,255,0.03) 50%, transparent 70%)', backgroundSize: '200% 100%' }} />
            
            <div className="hiw-play-icon absolute inset-0 flex items-center justify-center z-10">
              <div className="flex items-center justify-center rounded-full" style={{ width: 56, height: 56, background: 'rgba(255,255,255,0.08)', backdropFilter: 'blur(12px)', border: '1px solid rgba(255,255,255,0.1)', boxShadow: '0 0 30px rgba(255,255,255,0.05)' }}>
                <svg width="20" height="24" viewBox="0 0 20 24" fill="white"><polygon points="0,0 20,12 0,24" /></svg>
              </div>
            </div>

            {/* ═══ Overlay System ═══ */}
            <div className="hiw-overlay-system absolute inset-0 z-20">
              {/* Backdrop */}
              <div className="hiw-waveform-overlay absolute inset-0" style={{ background: 'rgba(5,5,5,1)', backdropFilter: 'blur(20px)' }} />

              {/* Inactive Bars */}
              <div className="hiw-inactive-bars absolute inset-0">
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[85%] h-[80px]">
                  {waveHeights.map((h, i) => {
                    const isHL = (i >= 8 && i <= 14) || (i >= 22 && i <= 28) || (i >= 36 && i <= 42);
                    if (isHL) return null;
                    return (
                      <div key={i} className="absolute bottom-1/2 translate-y-1/2 rounded-[1.5px] bg-white/15"
                           style={{ left: `${(i/50)*100}%`, width: '1.2%', height: `${h * 0.6}px` }} />
                    );
                  })}
                </div>
              </div>

              {/* Highlight Boxes */}
              {[
                { startIdx: 8,  boxIdx: 1 },
                { startIdx: 22, boxIdx: 2 },
                { startIdx: 36, boxIdx: 3 }
              ].map(({ startIdx, boxIdx }) => (
                <div key={boxIdx} className={`hiw-hl-box hiw-hl-${boxIdx}`}>
                  {/* State 1: Active Waveform Segment */}
                  <div className="hiw-hl-state-1 absolute inset-0 flex items-center justify-between px-3">
                    {waveHeights.slice(startIdx, startIdx + 7).map((h, i) => (
                      <div key={i} className="rounded-[1.5px] bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]"
                           style={{ width: '10%', height: `${h * 0.6}px` }} />
                    ))}
                  </div>
                  
                  {/* State 2: Extracted Clip Card */}
                  <div className="hiw-hl-state-2 absolute inset-0 flex items-center gap-4 px-4 w-full">
                    <div className="flex items-center justify-center rounded-lg flex-shrink-0 bg-white/5 border border-white/10"
                         style={{ width: 44, height: 44 }}>
                      <svg width="12" height="14" viewBox="0 0 14 16" fill="rgba(255,255,255,0.8)"><polygon points="0,0 14,8 0,16" /></svg>
                    </div>
                    <div className="flex-1 flex flex-col gap-2">
                      <div className="h-2 w-1/2 bg-white/20 rounded" />
                      <div className="relative h-1 w-full bg-white/10 rounded overflow-hidden">
                        <div className="hiw-clip-progress absolute top-0 left-0 bottom-0 bg-blue-500 rounded" style={{ width: '100%' }} />
                      </div>
                    </div>
                    <span className="text-[10px] font-bold tracking-widest text-[#999] font-mono">
                      {`CLIP 0${boxIdx}`}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Progress Bar Area */}
          <div className="flex items-center gap-3 px-5 z-30 relative" style={{ height: 44, background: '#060606', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
            <span className="text-[11px] text-[#555] font-mono">0:00</span>
            <div className="flex-1 relative h-[5px] bg-white/5 rounded overflow-hidden">
              <div className="hiw-progress-fill absolute top-0 left-0 bottom-0 bg-white rounded shadow-[0_0_8px_rgba(255,255,255,0.4)]" />
            </div>
            <span className="text-[11px] text-[#555] font-mono">58:42</span>
          </div>
        </div>
      </div>
    </>
  );
}

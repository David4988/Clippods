'use client';

import { useState, useEffect } from 'react';
import { uploadVideo, importYouTube, getToken } from '@/lib/api';
import { validateYoutubeUrl } from '@/lib/validators';
import { useRouter } from 'next/navigation';
import Navbar from '@/components/Navbar';
import SoundwaveLoader from '@/components/SoundwaveLoader';

export default function VideoChopperPage() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [processingStep, setProcessingStep] = useState('');
  const [showOverlay, setShowOverlay] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const router = useRouter();

  // Allow public access to chop tools until generation

  const processFile = async (file: File) => {
    setLoading(true);
    setShowOverlay(true);
    setProcessingStep('Uploading file...');
    try {
      const res = await uploadVideo(file);
      if (res.success && res.data) {
        setProcessingStep('Upload complete!');
        setTimeout(() => {
          router.push(`/creator-tools/video-chopper/editor?videoId=${res.data!.videoId}`);
        }, 800);
      } else {
        alert('Upload failed: ' + (res.message || 'Unknown error'));
        resetState();
      }
    } catch (err) {
      alert('Upload Error — check your connection and try again.');
      resetState();
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const handleYoutube = async () => {
    if (!url.trim()) {
      alert('Please paste a YouTube URL');
      return;
    }
    if (!validateYoutubeUrl(url)) {
      alert('Invalid YouTube URL — please use a valid youtube.com or youtu.be link');
      return;
    }
    setLoading(true);
    setShowOverlay(true);

    const steps = [
      'Connecting to YouTube...',
      'Downloading video...',
      'Processing import...',
      'Preparing editor...',
    ];
    let stepIdx = 0;
    setProcessingStep(steps[0]);

    const stepInterval = setInterval(() => {
      stepIdx++;
      if (stepIdx < steps.length) {
        setProcessingStep(steps[stepIdx]);
      }
    }, 2000);

    try {
      const res = await importYouTube(url);
      clearInterval(stepInterval);
      if (res.success && res.data) {
        setProcessingStep('Import complete!');
        setTimeout(() => {
          router.push(`/creator-tools/video-chopper/editor?videoId=${res.data!.videoId}`);
        }, 800);
      } else {
        alert('Import failed: ' + (res.message || 'Unknown error'));
        resetState();
      }
    } catch (err) {
      clearInterval(stepInterval);
      alert('Import Error — check your connection and try again.');
      resetState();
    }
  };

  function resetState() {
    setLoading(false);
    setShowOverlay(false);
    setProcessingStep('');
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = () => setDragActive(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      processFile(file);
    }
  };

  if (pageLoading) return null;

  return (
    <div className="min-h-screen bg-background text-text">
      <Navbar backHref="/creator-tools" backLabel="← Creator Tools" />

      <main className="max-w-[800px] mx-auto px-4 sm:px-6 pt-12 sm:pt-16 pb-24 sm:pb-32 cp-fade-in">
        {/* Header */}
        <div className="mb-10 sm:mb-12 cp-slide-up" style={{ animationDelay: '0.1s' }}>
          <h1 className="text-2xl sm:text-[32px] font-extrabold tracking-tight mb-2">Upload Podcast</h1>
          <p className="text-muted text-[14px] sm:text-[15px]">Upload a video or audio file, or paste a link. ClipPods will find the highlights.</p>
        </div>

        {/* Drag & Drop Zone */}
        <div
          onClick={() => document.getElementById('file-upload')?.click()}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`border border-dashed rounded-2xl py-12 sm:py-16 px-6 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-300 group cp-slide-up cp-hover-lift ${
            dragActive
              ? 'border-white bg-white/5 shadow-[0_8px_32px_rgba(255,255,255,0.06)]'
              : 'border-white/15 hover:border-white/40 hover:bg-[#0a0a0a]'
          }`}
          style={{ animationDelay: '0.2s' }}
        >
          <input
            type="file"
            id="file-upload"
            className="hidden"
            accept="video/mp4,audio/mp3,audio/wav,video/webm"
            onChange={handleUpload}
          />
          <div className="w-14 h-14 rounded-full bg-white/5 border border-white/10 text-white flex items-center justify-center mb-5 transition-transform duration-300 group-hover:-translate-y-1 group-hover:border-white/20">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          </div>
          <h3 className="text-base sm:text-lg font-bold mb-2">Drop a file here or click to browse</h3>
          <p className="text-xs sm:text-sm text-[#555]">MP4, MP3, WAV, WebM — any length</p>
        </div>

        {/* Divider */}
        <div className="flex items-center my-6 sm:my-8 text-xs text-[#555] cp-slide-up" style={{ animationDelay: '0.3s' }}>
          <div className="flex-1 border-b border-border"></div>
          <span className="px-4">or</span>
          <div className="flex-1 border-b border-border"></div>
        </div>

        {/* URL Input Row */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4 cp-slide-up" style={{ animationDelay: '0.35s' }}>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleYoutube()}
            placeholder="Paste a YouTube or podcast URL..."
            className="flex-1 h-12 bg-card border border-border rounded-lg px-4 text-white outline-none focus:border-white/50 transition-all duration-200 text-sm sm:text-base"
          />
          <button
            onClick={handleYoutube}
            disabled={loading}
            className="h-12 px-7 bg-white text-black font-semibold rounded-lg transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap cp-btn-hover"
          >
            Process
          </button>
        </div>

        {/* Options */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 mt-4 cp-slide-up" style={{ animationDelay: '0.4s' }}>
          <select className="bg-card border border-border rounded-lg px-4 py-3 text-white text-sm outline-none focus:border-white/40 transition-colors cursor-pointer flex-1 sm:flex-none sm:max-w-[250px]">
            <option>Auto-detect language</option>
            <option>Tamil</option>
            <option>Hindi</option>
          </select>
          <select className="bg-card border border-border rounded-lg px-4 py-3 text-white text-sm outline-none focus:border-white/40 transition-colors cursor-pointer flex-1 sm:flex-none sm:max-w-[200px]">
            <option value="60">60s Clips (Standard)</option>
            <option value="30">30s Clips (Fast)</option>
          </select>
        </div>
      </main>

      {/* ═══════════════════ PROCESSING OVERLAY ═══════════════════ */}
      {showOverlay && (
        <div className="fixed inset-0 bg-[rgba(0,0,0,0.88)] backdrop-blur-xl z-[10000] flex items-center justify-center p-6">
          <div className="bg-card border border-border rounded-3xl p-10 sm:p-12 max-w-[420px] w-full text-center flex flex-col items-center shadow-2xl cp-fade-in">
            {/* Spinner */}
            <div className="mb-6 w-12 flex justify-center">
              <SoundwaveLoader />
            </div>
            <h3 className="text-lg sm:text-xl font-bold mb-2">{processingStep}</h3>
            <p className="text-sm text-muted">Please do not close this window.</p>
          </div>
        </div>
      )}
    </div>
  );
}

'use client';

import Navbar from '@/components/Navbar';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { getToken } from '@/lib/api';
import { useRouter } from 'next/navigation';

export default function CreatorToolsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  return (
    <div className="min-h-screen bg-background text-text flex flex-col">
      <Navbar showLinks={true} />
      
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 py-12 sm:py-16 cp-fade-in">
        <div className="cp-slide-up" style={{ animationDelay: '0.1s' }}>
          <h1 className="text-3xl sm:text-4xl font-bold mb-3 sm:mb-4">Creator Tools</h1>
          <p className="text-muted mb-8 sm:mb-12 text-sm sm:text-base">Access the ClipPods AI suite and workflow tools securely.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 sm:gap-8">
          <Link href="/creator-tools/video-chopper" passHref>
            <div className="bg-card border border-border hover:border-white/30 transition-all duration-300 rounded-xl p-6 sm:p-8 cursor-pointer h-full flex flex-col relative group cp-hover-lift cp-slide-up" style={{ animationDelay: '0.15s' }}>
              <div className="bg-white/10 text-white text-[10px] sm:text-xs font-bold px-3 py-1 rounded-full mb-5 sm:mb-6 uppercase w-fit tracking-wider">LIVE</div>
              <h3 className="text-xl sm:text-2xl font-bold mb-2 sm:mb-3 group-hover:text-white text-gray-200 transition-colors duration-200">Video Chopper</h3>
              <p className="text-muted text-sm">Manually cut and trim long-form content securely.</p>
              <div className="mt-auto pt-6">
                <span className="text-sm text-white/50 group-hover:text-white transition-colors duration-200">Open Tool →</span>
              </div>
            </div>
          </Link>
          
          <div className="bg-card border border-border/50 rounded-xl p-6 sm:p-8 h-full flex flex-col relative opacity-60 cp-slide-up" style={{ animationDelay: '0.2s' }}>
            <div className="bg-blue-600/20 text-blue-400 border border-blue-500/30 text-[10px] sm:text-xs font-bold px-3 py-1 rounded-full mb-5 sm:mb-6 uppercase w-fit tracking-wider shadow-[0_0_15px_rgba(59,130,246,0.2)]">COMING SOON</div>
            <h3 className="text-xl sm:text-2xl font-bold mb-2 sm:mb-3 text-gray-400">AI Video Clipper</h3>
            <p className="text-muted text-sm">Auto-detect viral highlights and semantic segments with Native Indian NLP modeling.</p>
            <div className="mt-auto pt-6">
              <span className="text-sm text-white/30">Coming Soon</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

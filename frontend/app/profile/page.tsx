'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getToken, logout } from '@/lib/api';
import Navbar from '@/components/Navbar';
import SoundwaveLoader from '@/components/SoundwaveLoader';

interface UserProfile {
  id: number;
  workspaceName: string;
  email: string;
  createdAt: string;
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push('/');
      return;
    }

    const API_BASE = 'http://localhost:4000/api';

    fetch(`${API_BASE}/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setProfile(data.data);
        } else {
          logout();
          router.push('/');
        }
      })
      .catch((err) => {
        console.error('Failed to load profile', err);
        logout();
        router.push('/');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [router]);

  const handleLogout = () => {
    logout();
    window.location.href = '/';
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <SoundwaveLoader />
      </div>
    );
  }

  if (!profile) return null;

  return (
    <div className="min-h-screen bg-background text-text flex flex-col">
      <Navbar showLinks={true} />
      
      <main className="flex-1 flex flex-col items-center justify-center py-16 sm:py-20 px-4 sm:px-6 cp-fade-in">
        <div className="w-full max-w-md bg-card border border-border rounded-2xl p-6 sm:p-8 flex flex-col relative overflow-hidden cp-slide-up" style={{ animationDelay: '0.1s' }}>
          <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-white/20 via-white/60 to-white/20"></div>

          <div className="flex items-center gap-4 mb-6 sm:mb-8">
            <div className="w-14 h-14 sm:w-16 sm:h-16 bg-white/5 border border-border rounded-full flex items-center justify-center text-xl sm:text-2xl font-bold text-white">
              {profile.workspaceName.charAt(0).toUpperCase()}
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-bold text-white">{profile.workspaceName}</h1>
              <p className="text-muted text-sm">{profile.email}</p>
            </div>
          </div>

          <div className="space-y-3 sm:space-y-4 mb-6 sm:mb-8">
            <div className="bg-white/[0.03] p-4 rounded-xl border border-white/[0.06]">
              <span className="block text-[10px] sm:text-xs uppercase tracking-wider text-muted mb-1">Account Role</span>
              <span className="text-white font-medium text-sm">Workspace Admin</span>
            </div>
            <div className="bg-white/[0.03] p-4 rounded-xl border border-white/[0.06]">
              <span className="block text-[10px] sm:text-xs uppercase tracking-wider text-muted mb-1">Member Since</span>
              <span className="text-white font-medium text-sm">{new Date(profile.createdAt).toLocaleDateString()}</span>
            </div>
          </div>

          <div className="mt-auto flex flex-col gap-3">
             <a href="/creator-tools" className="block w-full text-center bg-white text-black py-2.5 sm:py-3 rounded-xl font-semibold transition-all duration-200 cp-btn-hover text-sm">
              Access Creator Tools
            </a>
            <button onClick={handleLogout} className="w-full bg-white/[0.03] text-red-400 border border-red-500/20 hover:bg-red-500/10 py-2.5 sm:py-3 rounded-xl transition-all duration-200 font-medium text-sm">
              Log Out
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

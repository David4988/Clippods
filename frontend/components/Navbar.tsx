'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { setToken, logout, getCurrentUserApi } from '@/lib/api';
import { auth } from '@/lib/firebase';
import { onAuthStateChanged } from 'firebase/auth';

interface NavbarProps {
  backHref?: string;
  backLabel?: string;
  showLinks?: boolean;
}

export default function Navbar({ backHref, backLabel, showLinks = true }: NavbarProps) {
  const pathname = usePathname();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [userData, setUserData] = useState({ workspaceName: '', email: '', displayName: '' });

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      if (user) {
        // Enforce Firebase as sole auth state
        const freshToken = await user.getIdToken();
        setToken(freshToken);
        setIsLoggedIn(true);
        // Map user data for Avatar
        const profileRes = await getCurrentUserApi();
        if (profileRes.success && profileRes.data) {
          setUserData({
            workspaceName: profileRes.data.workspaceName || '',
            displayName: user.displayName || '',
            email: profileRes.data.email || user.email || ''
          });
        }
      } else {
        // Reset strictly to empty on Firebase explicit absence
        logout();
        setIsLoggedIn(false);
        setUserData({ workspaceName: '', email: '', displayName: '' });
      }
    });

    return () => unsubscribe();
  }, []);

  // Close menus on route change
  useEffect(() => {
    setMobileOpen(false);
    setShowProfileMenu(false);
  }, [pathname]);

  const handleLogout = () => {
    logout();
    setIsLoggedIn(false);
    setShowProfileMenu(false);
    window.location.href = '/';
  };

  const toggleMobile = () => setMobileOpen(!mobileOpen);

  const navLinkClass = (targetPath: string, isPrefix = false) => {
    const active = isPrefix
      ? pathname?.startsWith(targetPath)
      : pathname === targetPath;
    return `text-sm transition-colors duration-200 ${active ? 'text-white font-medium' : 'text-[#888] hover:text-white'}`;
  };

  const avatarSource = userData.workspaceName || userData.displayName || userData.email || '?';
  const initialText = avatarSource.charAt(0).toUpperCase();

  return (
    <nav className="border-b border-border bg-[rgba(0,0,0,0.85)] backdrop-blur-xl px-4 sm:px-6 py-3.5 flex items-center justify-between sticky top-0 z-50">
      <div className="flex items-center gap-6 sm:gap-8">
        <Link href="/" className="font-bold text-xl tracking-tight flex items-center gap-0.5">
          <span className="text-white">Clip</span><span className="text-blue-500">Pods</span>
        </Link>
        
        {showLinks && (
          <div className="hidden md:flex items-center gap-5">
            <Link href="/" className={navLinkClass('/')}>Home</Link>
            <Link href="/#how-it-works" className="text-sm text-[#888] hover:text-white transition-colors duration-200">How It Works</Link>
            <Link href="/#features" className="text-sm text-[#888] hover:text-white transition-colors duration-200">Features</Link>
            <Link href="/creator-tools" className={navLinkClass('/creator-tools', true)}>Creator Tools</Link>
            <Link href="/#pricing" className="text-sm text-[#888] hover:text-white transition-colors duration-200">Pricing</Link>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3 sm:gap-4">
        {backHref && backLabel ? (
          <Link href={backHref} className="text-sm text-[#888] hover:text-white transition-colors duration-200">
            {backLabel}
          </Link>
        ) : (
          isLoggedIn ? (
            <div className="relative hidden sm:inline-flex items-center">
              <button 
                onClick={() => setShowProfileMenu(!showProfileMenu)} 
                className="w-9 h-9 rounded-full bg-white text-black flex items-center justify-center font-bold text-sm tracking-widest hover:scale-105 transition-transform border border-border outline-none focus:ring-2 focus:ring-white/20"
                aria-label="User Avatar"
              >
                {initialText}
              </button>
              
              {showProfileMenu && (
                <div className="absolute right-0 top-[120%] w-60 bg-[#111] border border-border rounded-xl shadow-2xl py-2 flex flex-col z-[100] cp-fade-in origin-top-right">
                  <div className="px-4 py-3 border-b border-white/10 mb-1 leading-snug">
                    <div className="text-sm text-white font-medium truncate mb-0.5">{userData.workspaceName || userData.displayName || 'Creator'}</div>
                    <div className="text-xs text-gray-500 truncate">{userData.email || 'user@example.com'}</div>
                  </div>
                  <Link href="/creator-tools" className="px-4 py-2 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-left w-full flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                    Creator Tools
                  </Link>
                  <Link href="/profile" className="px-4 py-2 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-left w-full flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="7" r="4"/><path d="M5.4 20h13.2a8 8 0 00-13.2 0z"/></svg>
                    Account Settings
                  </Link>
                  <button onClick={handleLogout} className="px-4 py-2 text-sm text-red-500 hover:text-red-400 hover:bg-white/5 transition-colors text-left w-full flex items-center gap-2 mt-1 border-t border-white/5 pt-3">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                    Log out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button onClick={() => {
              if (pathname === '/') {
                document.getElementById('login-modal')?.classList.add('active');
                document.body.style.overflow = 'hidden';
              } else {
                window.location.href = '/#login';
              }
            }} className="hidden sm:inline-flex items-center text-sm font-medium py-2 px-5 rounded-full bg-white text-black hover:bg-gray-200 transition-all duration-200 shadow-[0_0_15px_rgba(255,255,255,0.1)]">
              Login
            </button>
          )
        )}

        {/* Mobile hamburger */}
        <button
          onClick={toggleMobile}
          className="md:hidden flex flex-col gap-[5px] p-1.5"
          aria-label="Toggle menu"
        >
          <span className={`block w-5 h-[1.5px] bg-white transition-all duration-300 ${mobileOpen ? 'rotate-45 translate-y-[6.5px]' : ''}`}></span>
          <span className={`block w-5 h-[1.5px] bg-white transition-all duration-300 ${mobileOpen ? 'opacity-0' : ''}`}></span>
          <span className={`block w-5 h-[1.5px] bg-white transition-all duration-300 ${mobileOpen ? '-rotate-45 -translate-y-[6.5px]' : ''}`}></span>
        </button>
      </div>

      {/* Mobile dropdown menu */}
      {mobileOpen && (
        <div className="absolute top-full left-0 right-0 bg-[rgba(0,0,0,0.95)] backdrop-blur-xl border-b border-border md:hidden cp-fade-in z-50">
          <div className="flex flex-col py-4 px-6 gap-1">
            {showLinks && (
              <>
                <Link href="/" onClick={() => setMobileOpen(false)} className="py-2.5 text-sm text-[#888] hover:text-white transition-colors">Home</Link>
                <Link href="/#how-it-works" onClick={() => setMobileOpen(false)} className="py-2.5 text-sm text-[#888] hover:text-white transition-colors">How It Works</Link>
                <Link href="/#features" onClick={() => setMobileOpen(false)} className="py-2.5 text-sm text-[#888] hover:text-white transition-colors">Features</Link>
                <Link href="/creator-tools" onClick={() => setMobileOpen(false)} className="py-2.5 text-sm text-[#888] hover:text-white transition-colors">Creator Tools</Link>
                <Link href="/#pricing" onClick={() => setMobileOpen(false)} className="py-2.5 text-sm text-[#888] hover:text-white transition-colors">Pricing</Link>
              </>
            )}
            <div className="border-t border-border mt-2 pt-3 flex flex-col gap-1">
              {isLoggedIn ? (
                <>
                  <div className="py-2 mb-2 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-white text-black flex items-center justify-center font-bold text-xs">{initialText}</div>
                    <div className="flex flex-col leading-snug">
                      <span className="text-white text-sm font-medium truncate max-w-[200px]">{userData.workspaceName || userData.displayName || 'Creator'}</span>
                      <span className="text-gray-500 text-xs mt-0.5 truncate max-w-[200px]">{userData.email || 'user@example.com'}</span>
                    </div>
                  </div>
                  <Link href="/profile" onClick={() => setMobileOpen(false)} className="py-2.5 text-sm text-gray-300 hover:text-white flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="7" r="4"/><path d="M5.4 20h13.2a8 8 0 00-13.2 0z"/></svg> Account Settings
                  </Link>
                  <button onClick={handleLogout} className="py-2.5 text-sm text-left text-red-400 hover:text-red-300 transition-colors flex items-center gap-2">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg> Logout
                  </button>
                </>
              ) : (
                <button onClick={() => {
                  setMobileOpen(false);
                  if (pathname === '/') {
                    document.getElementById('login-modal')?.classList.add('active');
                    document.body.style.overflow = 'hidden';
                  } else {
                    window.location.href = '/#login';
                  }
                }} className="py-2.5 text-sm text-white font-medium text-left">Login</button>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}

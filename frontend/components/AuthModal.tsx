'use client';

import { useState, FormEvent } from 'react';
import { loginApi, signupApi, setToken, signInWithGoogleApi } from '@/lib/api';

export default function AuthModal({ onClose, onSuccess }: { onClose: () => void, onSuccess: () => void }) {
  const [authMode, setAuthMode] = useState<'signup'|'login'>('signup');
  const [authWorkspaceName, setAuthWorkspaceName] = useState('');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authConfirm, setAuthConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleGoogleSignIn = async () => {
    setLoading(true); setError('');
    const payload = await signInWithGoogleApi();
    if (payload.success && payload.data?.token) {
      setToken(payload.data.token);
      onSuccess();
    } else {
      setError(payload.message || 'Google Sign-In failed');
    }
    setLoading(false);
  };

  const submitAuth = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    
    if (authMode === 'signup' && authPassword !== authConfirm) {
      setError('Passwords do not match');
      setLoading(false);
      return;
    }

    try {
      const payload = authMode === 'signup' 
        ? await signupApi(authEmail, authPassword, authWorkspaceName) 
        : await loginApi(authEmail, authPassword);
      
      if (payload.success && payload.data?.token) {
        setToken(payload.data.token);
        onSuccess();
      } else {
        setError(payload.message || 'Authentication failed');
      }
    } catch {
      setError('Network error');
    }
    setLoading(false);
  };

  const [showPassword, setShowPassword] = useState(false);
  const isSignup = authMode === 'signup';

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[20000] flex items-center justify-center p-4 sm:p-6 transition-all">
      <div className="relative w-full max-w-[900px] h-[85vh] sm:h-auto sm:min-h-[500px] bg-[#0a0a0a] rounded-3xl overflow-hidden flex flex-col md:flex-row shadow-[0_0_80px_rgba(37,99,235,0.15)] ring-1 ring-white/10">
        
        {/* PHYSICAL SLIDING BACKGROUND LAYER */}
        <div className={`absolute top-0 left-0 w-full md:w-1/2 h-1/2 md:h-full bg-[#2563eb] z-0 transition-transform duration-[800ms] ease-[cubic-bezier(0.8,0,0.2,1)] ${isSignup ? 'translate-y-full md:translate-y-0 md:translate-x-full' : 'translate-y-0 md:translate-x-0'}`}>
          {/* Subtle Glow on the Slider */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-white/20 blur-[80px] rounded-full mix-blend-overlay"></div>
        </div>

        {/* Close Button overlay */}
        <button onClick={onClose} className="absolute right-4 top-4 text-white/50 hover:text-white z-50 transition-colors bg-white/10 p-2 rounded-full backdrop-blur-md border border-white/20" aria-label="Close">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>

        {/* LEFT PANEL / MARKETING */}
        <div className="flex-1 relative z-10 flex flex-col justify-center p-8 sm:p-14 overflow-hidden">
            <div className="relative z-10 flex flex-col items-start text-white">
                <div className="flex items-center gap-3 mb-6 sm:mb-10">
                   <div className="w-10 h-10 rounded-xl bg-white text-black flex items-center justify-center font-bold text-xl shadow-lg ring-4 ring-white/10">C</div>
                   <span className="text-xl font-bold tracking-tight">ClipPods</span>
                </div>
                
                <h2 className="text-2xl sm:text-4xl font-bold mb-3 sm:mb-4 tracking-tight leading-tight">
                   India’s first AI viral clip generator.
                </h2>
                <p className={`text-sm sm:text-base leading-relaxed max-w-sm transition-colors duration-[800ms] ${isSignup ? 'text-gray-400' : 'text-blue-100'}`}>
                   Join thousands of creators turning long podcasts into highly optimized shorts and visual gold in seconds. Fully optimized for English, Hindi, and Tamil creators.
                </p>
                
                <div className="mt-8 sm:mt-12 flex items-center gap-3 opacity-80">
                   <div className="flex -space-x-2 drop-shadow-md">
                     <div className="w-6 h-6 sm:w-7 sm:h-7 rounded-full bg-gray-600 border-2 border-[#111]"></div>
                     <div className="w-6 h-6 sm:w-7 sm:h-7 rounded-full bg-gray-400 border-2 border-[#111]"></div>
                     <div className="w-6 h-6 sm:w-7 sm:h-7 rounded-full bg-gray-300 border-2 border-[#111]"></div>
                   </div>
                   <span className="text-[10px] sm:text-xs font-semibold uppercase tracking-widest text-white/80">Premium Access</span>
                </div>
            </div>
        </div>

        {/* RIGHT PANEL / FORM */}
        <div className="flex-1 relative z-10 flex flex-col justify-center p-6 sm:p-12 border-t md:border-t-0 md:border-l border-white/5">
            <div className="max-w-[340px] mx-auto w-full relative z-10 text-white">
                <h3 className="text-xl sm:text-2xl font-bold mb-1.5 sm:mb-2 tracking-tight">{isSignup ? 'Create your account' : 'Welcome back'}</h3>
                <p className={`text-xs sm:text-sm mb-6 transition-colors duration-[800ms] ${isSignup ? 'text-blue-100' : 'text-gray-400'}`}>
                   {isSignup ? 'Sign up to generate unlimited clips.' : 'Log in to continue clipping.'}
                </p>
                
                {/* OAUTH BUTTON */}
                <button 
                  type="button" 
                  onClick={handleGoogleSignIn}
                  disabled={loading}
                  className={`w-full py-3 rounded-xl font-semibold flex items-center justify-center gap-3 transition-colors duration-500 disabled:opacity-50 mb-5 shadow-lg active:scale-[0.98]
                    ${isSignup ? 'bg-white text-[#2563eb] hover:bg-gray-100 ring-2 ring-white/50' : 'bg-white text-black hover:bg-gray-200 ring-2 ring-white/10'}`}
                >
                  <svg width="20" height="20" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                  <span className="text-sm">Continue with Google</span>
                </button>

                <div className="flex items-center gap-4 mb-5">
                  <div className="h-px bg-white/20 flex-1"></div>
                  <span className={`text-[10px] font-bold tracking-widest uppercase transition-colors duration-[800ms] ${isSignup ? 'text-blue-100' : 'text-gray-500'}`}>OR EMAIL</span>
                  <div className="h-px bg-white/20 flex-1"></div>
                </div>

                {/* FORM */}
                <form onSubmit={submitAuth} className="flex flex-col gap-3">
                  {isSignup && (
                    <div>
                      <input type="text" value={authWorkspaceName} onChange={e=>setAuthWorkspaceName(e.target.value)} className={`w-full bg-black/40 border rounded-xl p-2.5 sm:p-3 text-white outline-none focus:bg-white/10 transition-all text-sm font-medium backdrop-blur-md shadow-inner ${isSignup ? 'border-white/30 placeholder-white/60 focus:border-white focus:ring-2 focus:ring-white/30' : 'border-white/10 placeholder-gray-500 focus:border-white/40'}`} placeholder="My Studio Space" required />
                    </div>
                  )}
                  <div>
                    <input type="email" value={authEmail} onChange={e=>setAuthEmail(e.target.value)} className={`w-full bg-black/40 border rounded-xl p-2.5 sm:p-3 text-white outline-none focus:bg-white/10 transition-all text-sm font-medium backdrop-blur-md shadow-inner ${isSignup ? 'border-white/30 placeholder-white/60 focus:border-white focus:ring-2 focus:ring-white/30' : 'border-white/10 placeholder-gray-500 focus:border-white/40'}`} placeholder="you@example.com" required />
                  </div>
                  
                  <div className={`grid gap-3 ${isSignup ? 'grid-cols-2' : 'grid-cols-1'}`}>
                      <div className="relative">
                        <input type={showPassword ? 'text' : 'password'} value={authPassword} onChange={e=>setAuthPassword(e.target.value)} className={`w-full bg-black/40 border rounded-xl p-2.5 sm:p-3 text-white outline-none focus:bg-white/10 transition-all text-sm font-medium backdrop-blur-md shadow-inner pr-9 ${isSignup ? 'border-white/30 placeholder-white/60 focus:border-white focus:ring-2 focus:ring-white/30' : 'border-white/10 placeholder-gray-500 focus:border-white/40 focus:ring-2 focus:ring-gray-400/30'}`} placeholder="Password" required minLength={8} />
                        <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white transition-colors focus:outline-none" aria-label="Toggle password visibility">
                           <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              {showPassword ? (
                                <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>
                              ) : (
                                <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></>
                              )}
                           </svg>
                        </button>
                      </div>
                      
                      {isSignup && (
                         <div className="relative">
                           <input type={showPassword ? 'text' : 'password'} value={authConfirm} onChange={e=>setAuthConfirm(e.target.value)} className={`w-full bg-black/40 border rounded-xl p-2.5 sm:p-3 text-white outline-none focus:bg-white/10 transition-all text-sm font-medium backdrop-blur-md shadow-inner pr-9 ${isSignup ? 'border-white/30 placeholder-white/60 focus:border-white focus:ring-2 focus:ring-white/30' : 'border-white/10 placeholder-gray-500 focus:border-white/40'}`} placeholder="Confirm" required minLength={8} />
                         </div>
                      )}
                  </div>

                  {error && <div className="text-red-400 bg-black/40 border border-red-400/30 rounded-lg p-2.5 mt-1 text-xs font-medium text-center shadow-md backdrop-blur-md">{error}</div>}
                  
                  <button type="submit" disabled={loading} className={`mt-1 sm:mt-2 w-full font-bold py-3.5 rounded-xl transition-all duration-300 disabled:opacity-50 text-sm shadow-xl active:scale-[0.98]
                    ${isSignup ? 'bg-[#0a0a0a] text-white hover:bg-black ring-1 ring-white/10' : 'bg-white text-black hover:bg-gray-200'}
                  `}>
                    {loading ? 'Please wait...' : (isSignup ? 'Create Account' : 'Secure Log In')}
                  </button>
                </form>

                <p className={`text-xs sm:text-sm text-center mt-5 sm:mt-6 transition-colors duration-[800ms] ${isSignup ? 'text-blue-100' : 'text-gray-400'}`}>
                  <span>{isSignup ? 'Already have an account?' : "Don't have an account?"}</span>{' '}
                  <button type="button" onClick={() => setAuthMode(isSignup ? 'login' : 'signup')} className="font-semibold text-white hover:underline focus:outline-none">
                    {isSignup ? 'Log In' : 'Sign Up'}
                  </button>
                </p>
            </div>

        </div>
      </div>
    </div>
  );
}

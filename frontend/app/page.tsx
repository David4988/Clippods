'use client';
import Script from 'next/script';
import { useState, useRef, FormEvent } from 'react';
import Navbar from '@/components/Navbar';
import HowItWorksAnimation from '@/components/HowItWorksAnimation';
import { loginApi, signupApi, setToken, signInWithGoogleApi } from '@/lib/api';

export default function LandingPage() {
  const [authWorkspaceName, setAuthWorkspaceName] = useState('');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authConfirm, setAuthConfirm] = useState('');
  const [authMode, setAuthMode] = useState<'signup'|'login'>('signup');
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const handleGoogleSignIn = async () => {
    setAuthLoading(true); setAuthError('');
    const payload = await signInWithGoogleApi();
    if (payload.success && payload.data?.token) {
      setToken(payload.data.token);
      window.location.href = '/profile';
    } else {
      setAuthError(payload.message || 'Google Sign-In failed');
    }
    setAuthLoading(false);
  };

  const submitAuth = async (e: FormEvent) => {
    e.preventDefault();
    setAuthLoading(true); setAuthError('');
    if (authMode === 'signup' && authPassword !== authConfirm) {
      setAuthError('Passwords do not match');
      setAuthLoading(false);
      return;
    }

    try {
      const payload = authMode === 'signup' 
        ? await signupApi(authEmail, authPassword, authWorkspaceName) 
        : await loginApi(authEmail, authPassword);
      
      if (payload.success) {
        setToken(payload.data.token);
        window.location.href = '/profile';
      } else {
        setAuthError(payload.message || 'Authentication failed');
      }
    } catch {
      setAuthError('Network error');
    }
    setAuthLoading(false);
  };

  return (
    <>
      {/* Landing-specific CSS */}
      <link rel="stylesheet" href="/landing/styles.css" />

      {/* ═══════════════════ LOADER ═══════════════════ */}
      <div id="page-loader" className="loader-overlay">
        <div className="loader-content">
          <div className="loader-waveform" id="loader-waveform">
            <div className="lw-bar" style={{'--d':'0.00s','--h':'12px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.06s','--h':'22px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.12s','--h':'34px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.18s','--h':'26px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.24s','--h':'46px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.30s','--h':'36px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.36s','--h':'54px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.42s','--h':'30px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.48s','--h':'50px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.54s','--h':'58px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.60s','--h':'42px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.66s','--h':'62px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.72s','--h':'60px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.78s','--h':'44px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.84s','--h':'52px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.90s','--h':'28px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'0.96s','--h':'48px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'1.02s','--h':'38px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'1.08s','--h':'50px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'1.14s','--h':'24px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'1.20s','--h':'34px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'1.26s','--h':'18px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'1.32s','--h':'26px'} as React.CSSProperties}></div>
            <div className="lw-bar" style={{'--d':'1.38s','--h':'10px'} as React.CSSProperties}></div>
          </div>
          <div className="loader-brand">ClipPods</div>
          <p className="loader-tagline">Preparing your experience</p>
        </div>
      </div>

      {/* ═══════════════════ NAVBAR ═══════════════════ */}
      <Navbar showLinks={true} />

      {/* ═══════════════════ HERO ═══════════════════ */}
      <header id="hero" className="hero section">
        <canvas id="hero-grid" className="hero-grid-canvas"></canvas>
        <div className="hero-glow"></div>

        <div className="container hero-container">
          <div className="hero-badge anim-item" data-anim="fade-up" data-delay="0">
            <span className="badge-dot"></span>
            <span>Now supporting Tamil &amp; Hindi</span>
            <span className="badge-arrow">&rarr;</span>
          </div>

          <h1 className="hero-title anim-item" data-anim="split-text" data-delay="1">
            Turn long podcasts into<br />
            <span className="hero-accent">high-impact AI clips</span>
          </h1>

          <p className="hero-sub anim-item" data-anim="fade-up" data-delay="3">
            India&#39;s first AI viral clip generator for Tamil &amp; Hindi creators.<br />
            Join the waitlist for early access.
          </p>

          <div className="hero-actions anim-item" data-anim="fade-up" data-delay="4">
            <a href="#pricing" className="btn btn-primary magnetic" id="hero-cta-trial">
              <span className="btn-text">Join the AI Waitlist</span>
              <span className="btn-shimmer"></span>
            </a>
            <a href="/creator-tools" className="btn btn-outline magnetic" id="hero-cta-demo">
              <span className="btn-text">Try Video Chopper</span>
            </a>
          </div>

          <div className="hero-stats anim-item" data-anim="fade-up" data-delay="5">
            <div className="stat">
              <span className="stat-num" data-count="10" data-suffix="x">0x</span>
              <span className="stat-label">Faster than manual</span>
            </div>
            <div className="stat-divider"></div>
            <div className="stat">
              <span className="stat-num" data-count="2" data-suffix="">0</span>
              <span className="stat-label">Languages supported</span>
            </div>
            <div className="stat-divider"></div>
            <div className="stat">
              <span className="stat-num" data-count="98" data-suffix="%">0%</span>
              <span className="stat-label">Highlight accuracy</span>
            </div>
          </div>
          
        </div>
      </header>

      {/* Removed tools section as per AI Clipper requirement */}

      {/* ═══════════════════ BRAND MARQUEE ═══════════════════ */}
      <section className="marquee-section" id="marquee-section">
        <div className="marquee-track">
          <div className="marquee-content" id="marquee-content">
            {['AI-Powered','Tamil Support','Hindi Support','Smart Clipping','No Manual Editing','Fast Processing','Highlight Detection','Semantic Segments'].map((item, idx) => (
              <span key={`m1-${idx}`}>
                <span className="marquee-item">{item}</span>
                <span className="marquee-dot" style={{display:'inline-block',marginLeft:48}}></span>
              </span>
            ))}
            {['AI-Powered','Tamil Support','Hindi Support','Smart Clipping','No Manual Editing','Fast Processing','Highlight Detection','Semantic Segments'].map((item, idx) => (
              <span key={`m2-${idx}`}>
                <span className="marquee-item">{item}</span>
                <span className="marquee-dot" style={{display:'inline-block',marginLeft:48}}></span>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════ HOW IT WORKS ═══════════════════ */}
      <section id="how-it-works" className="section">
        <div className="container">
          <div className="section-header anim-item" data-anim="fade-up">
            <span className="section-tag">How It Works</span>
            <h2 className="section-title">Three steps. Zero effort.</h2>
            <p className="section-sub">From raw podcast to polished clips in minutes.</p>
          </div>

          {/* Podcast Waveform Visualizer */}
          <div className="anim-item" data-anim="fade-up" data-delay="1">
            <HowItWorksAnimation />
          </div>

          <div className="steps-flow">
            <div className="steps-connector">
              <div className="connector-line" id="connector-line"></div>
            </div>
            <div className="steps-grid">
              <div className="step-card anim-item flex-1" data-anim="fade-up" data-delay="0">
                <div className="step-num-ring">
                  <svg viewBox="0 0 100 100" className="step-ring-svg"><circle cx="50" cy="50" r="46" className="ring-bg" /><circle cx="50" cy="50" r="46" className="ring-fill" /></svg>
                  <span className="step-num-text">01</span>
                </div>
                <div className="step-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                </div>
                <h3 className="step-title">Upload or paste video</h3>
                <p className="step-desc">Drop your podcast video or paste a YouTube link.</p>
              </div>

              <div className="step-card anim-item flex-1" data-anim="fade-up" data-delay="2">
                <div className="step-num-ring">
                  <svg viewBox="0 0 100 100" className="step-ring-svg"><circle cx="50" cy="50" r="46" className="ring-bg" /><circle cx="50" cy="50" r="46" className="ring-fill" /></svg>
                  <span className="step-num-text">02</span>
                </div>
                <div className="step-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                </div>
                <h3 className="step-title">AI detects highlights (future)</h3>
                <p className="step-desc">Our AI will detect the best viral moments.</p>
              </div>

              <div className="step-card anim-item flex-1" data-anim="fade-up" data-delay="4">
                <div className="step-num-ring">
                  <svg viewBox="0 0 100 100" className="step-ring-svg"><circle cx="50" cy="50" r="46" className="ring-bg" /><circle cx="50" cy="50" r="46" className="ring-fill" /></svg>
                  <span className="step-num-text">03</span>
                </div>
                <div className="step-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                </div>
                <h3 className="step-title">Generate clips</h3>
                <p className="step-desc">Auto-frame, trim, or let the AI do it for you.</p>
              </div>

              <div className="step-card anim-item flex-1" data-anim="fade-up" data-delay="6">
                <div className="step-num-ring">
                  <svg viewBox="0 0 100 100" className="step-ring-svg"><circle cx="50" cy="50" r="46" className="ring-bg" /><circle cx="50" cy="50" r="46" className="ring-fill" /></svg>
                  <span className="step-num-text">04</span>
                </div>
                <div className="step-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                </div>
                <h3 className="step-title">Download & share</h3>
                <p className="step-desc">Get clean clips ready for TikTok, Shorts, and Reels.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════ FEATURES ═══════════════════ */}
      <section id="features" className="section">
        <div className="container">
          <div className="section-header anim-item" data-anim="fade-up">
            <span className="section-tag">Features</span>
            <h2 className="section-title">Everything you need to clip smarter</h2>
            <p className="section-sub">Built specifically for regional language podcast creators.</p>
          </div>
          <div className="features-grid">
            {[
              { id: 'feature-highlight', icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>, title: 'AI Highlight Detection', desc: 'Automatically identifies the most engaging moments using advanced speech and context analysis.', tags: ['Machine Learning', 'NLP'] },
              { id: 'feature-lang', icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>, title: 'Tamil & Hindi Support', desc: 'Native language understanding. No English-only bias — built for regional creators.', tags: ['தமிழ்', 'हिन्दी'] },
              { id: 'feature-fast', icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>, title: 'Fast Processing', desc: 'Get your clips in minutes, not hours. Optimized pipeline handles heavy files efficiently.', tags: ['Parallel', 'GPU'] },
              { id: 'feature-export', icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>, title: 'Clean Clip Export', desc: 'Download high-quality clips ready for Instagram Reels, YouTube Shorts, or any social platform.', tags: ['MP4', 'HD'] },
              { id: 'feature-noedit', icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M9 12l2 2 4-4"/></svg>, title: 'No Manual Editing', desc: 'Skip the timeline scrubbing. ClipPods does the heavy lifting so you can focus on creating.', tags: ['Zero-Touch', 'Auto'] },
              { id: 'feature-segment', icon: <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>, title: 'Smart Segmentation', desc: 'AI segments your podcast into logical topics and themes for contextually accurate clips.', tags: ['Semantic', 'Context'] },
            ].map((f, i) => (
              <div key={f.id} className="feature-card anim-item" data-anim="fade-up" data-delay={String(i)} id={f.id}>
                <div className="feature-icon-wrap">
                  <div className="feature-icon">{f.icon}</div>
                  <div className="feature-icon-glow"></div>
                </div>
                <h3 className="feature-title">{f.title}</h3>
                <p className="feature-desc">{f.desc}</p>
                <div className="feature-tag-row">
                  {f.tags.map(t => <span key={t} className="feature-micro-tag">{t}</span>)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════ INFOGRAPHIC METRICS ═══════════════════ */}
      <section className="metrics-section section">
        <div className="container">
          <div className="metrics-grid">
            <div className="metric-card anim-item" data-anim="fade-up" data-delay="0">
              <div className="metric-bar-wrap"><div className="metric-bar" data-width="95"></div></div>
              <div className="metric-info">
                <span className="metric-value" data-count="95" data-suffix="%">0%</span>
                <span className="metric-label">Time Saved vs Manual Editing</span>
              </div>
            </div>
            <div className="metric-card anim-item" data-anim="fade-up" data-delay="1">
              <div className="metric-bar-wrap"><div className="metric-bar" data-width="88"></div></div>
              <div className="metric-info">
                <span className="metric-value" data-count="88" data-suffix="%">0%</span>
                <span className="metric-label">Creator Satisfaction Rate</span>
              </div>
            </div>
            <div className="metric-card anim-item" data-anim="fade-up" data-delay="2">
              <div className="metric-bar-wrap"><div className="metric-bar" data-width="75"></div></div>
              <div className="metric-info">
                <span className="metric-value" data-count="3" data-suffix="min">0min</span>
                <span className="metric-label">Average Processing Time</span>
              </div>
            </div>
            <div className="metric-card anim-item" data-anim="fade-up" data-delay="3">
              <div className="metric-bar-wrap"><div className="metric-bar" data-width="70"></div></div>
              <div className="metric-info">
                <span className="metric-value" data-count="500" data-suffix="+">0+</span>
                <span className="metric-label">Clips Generated This Month</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Duplicate features section removed — features already displayed above */}

      {/* ═══════════════════ DEMO ═══════════════════ */}
      <section id="demo" className="section">
        <div className="container">
          <div className="section-header anim-item" data-anim="fade-up">
            <span className="section-tag">Demo</span>
            <h2 className="section-title">See ClipPods in action</h2>
            <p className="section-sub">Watch how a 2-hour podcast becomes 10 viral clips.</p>
          </div>
          <div className="demo-player anim-item" data-anim="scale-in">
            <div className="demo-frame" id="demo-video-frame">
              <div className="demo-placeholder" id="demo-placeholder-overlay">
                <div className="demo-play-ring">
                  <svg viewBox="0 0 100 100" className="play-ring-svg">
                    <circle cx="50" cy="50" r="46" />
                  </svg>
                  <div className="demo-play-btn" id="demo-play-btn">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21 6 3"/></svg>
                  </div>
                </div>
                <div className="demo-overlay-text">
                  <span className="demo-label">ClipPods Demo</span>
                  <span className="demo-sublabel">Click to play</span>
                </div>
              </div>
              <div className="demo-ui-mockup">
                <div className="mockup-header">
                  <div className="mockup-dots"><span></span><span></span><span></span></div>
                  <div className="mockup-url">app.clippods.com</div>
                </div>
                <div className="mockup-body">
                  <div className="mockup-sidebar">
                    <div className="mockup-sidebar-item active"></div>
                    <div className="mockup-sidebar-item"></div>
                    <div className="mockup-sidebar-item"></div>
                  </div>
                  <div className="mockup-content">
                    <div className="mockup-waveform">
                      {[20,45,70,95,85,90,40,55,30,65,80,75,35,50,25,60,42,38,88,92,45,30,55,48].map((h, i) => (
                        <div key={i} className={`wave-bar${[3,4,5,10,11,18,19].includes(i) ? ' highlight' : ''}`} style={{height: h+'%'}}></div>
                      ))}
                    </div>
                    <div className="mockup-scanline" id="mockup-scanline"></div>
                    <div className="mockup-clips">
                      {[{delay:'0s',status:'Ready',statusClass:''},{delay:'0.3s',status:'Processing',statusClass:' processing'},{delay:'0.6s',status:'Ready',statusClass:''}].map((c, i) => (
                        <div key={i} className="mockup-clip clip-anim" style={{'--clip-delay': c.delay} as React.CSSProperties}>
                          <div className="clip-thumb"></div>
                          <div className="clip-info"><div className="clip-title-bar"></div><div className="clip-time-bar"></div></div>
                          <div className={`clip-status${c.statusClass}`}>{c.status}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════ PRICING ═══════════════════ */}
      <section id="pricing" className="section">
        <div className="container">
          <div className="section-header anim-item" data-anim="fade-up">
            <span className="section-tag">Waitlist</span>
            <h2 className="section-title">Secure Early Access</h2>
            <p className="section-sub">ClipPods AI Clipper is launching soon. Secure your place.</p>
          </div>
          <div className="pricing-grid">
            {/* Creator Waitlist */}
            <div className="pricing-card featured anim-item" data-anim="fade-up" data-delay="1" id="pricing-creator" style={{margin: '0 auto', gridColumn: '1 / -1', maxWidth: '500px'}}>
              <div className="pricing-badge">Upcoming AI</div>
              <div className="pricing-glow"></div>
              <div className="pricing-header">
                <h3 className="pricing-plan">Video Clipper (Pro)</h3>
                <p className="pricing-desc">The Ultimate AI Clip Generator</p>
              </div>
              <div className="pricing-price">
                <span className="price-amount">₹499</span>
                <span className="price-crossed">/month</span>
              </div>
              <ul className="pricing-features">
                {['Auto viral moment detection','Tamil & Hindi support','Auto-framing & captions'].map(f => (
                  <li key={f}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5"/></svg>
                    {f}
                  </li>
                ))}
              </ul>
              <a href="#feedback" className="btn btn-accent pricing-btn magnetic">
                <span className="btn-text">Join Premium Waitlist</span>
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════ FEEDBACK ═══════════════════ */}
      <section id="feedback" className="section">
        <div className="container">
          <div className="section-header anim-item" data-anim="fade-up">
            <span className="section-tag">Feedback</span>
            <h2 className="section-title">We&#39;d love to hear from you</h2>
            <p className="section-sub">Help us build the best clipping tool for creators.</p>
          </div>
          <form className="feedback-form anim-item" data-anim="fade-up" id="feedback-form">
            <div className="form-group">
              <label htmlFor="feedback-email" className="form-label">Email</label>
              <input type="email" id="feedback-email" className="form-input" placeholder="you@example.com" required />
            </div>
            <div className="form-group">
              <label htmlFor="feedback-message" className="form-label">Message</label>
              <textarea id="feedback-message" className="form-textarea" rows={5} placeholder="Tell us what you think..." required></textarea>
            </div>
            <button type="submit" className="btn btn-primary form-submit magnetic" id="feedback-submit">
              <span className="btn-text">Send Feedback</span>
              <span className="btn-shimmer"></span>
            </button>
            <div className="form-success" id="form-success">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5"/></svg>
              Thank you! We&#39;ll get back to you soon.
            </div>
          </form>
        </div>
      </section>

      {/* ═══════════════════ FOOTER ═══════════════════ */}
      <footer id="footer" className="footer">
        <div className="container">
          <div className="footer-inner">
            <div className="footer-brand">
              <a href="#" className="nav-brand">
                <span className="brand-clip">Clip</span><span className="brand-pods">Pods</span>
              </a>
              <p className="footer-tagline">AI-powered podcast clipping<br />for regional creators.</p>
              <div className="footer-socials">
                <a href="#" aria-label="Twitter" className="social-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z"/></svg>
                </a>
                <a href="#" aria-label="GitHub" className="social-icon">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
                </a>
              </div>
            </div>
            <div className="footer-links">
              <div className="footer-col">
                <h4 className="footer-col-title">Product</h4>
                <ul>
                  <li><a href="#features">Features</a></li>
                  <li><a href="#pricing">Pricing</a></li>
                  <li><a href="#demo">Demo</a></li>
                </ul>
              </div>
              <div className="footer-col">
                <h4 className="footer-col-title">Company</h4>
                <ul>
                  <li><a href="#feedback">Contact</a></li>
                  <li><a href="#">Privacy</a></li>
                  <li><a href="#">Terms</a></li>
                </ul>
              </div>
            </div>
          </div>
          <div className="footer-bottom">
            <p>&copy; 2026 ClipPods. All rights reserved.</p>
          </div>
        </div>
      </footer>

      {/* ═══════════════════ LOGIN MODAL ═══════════════════ */}
      <div className="signup-overlay flex items-center justify-center p-4 sm:p-6 transition-all z-[20000]" id="login-modal" onClick={(e) => { if(e.target === e.currentTarget) document.getElementById('login-modal')?.classList.remove('active'); document.body.style.overflow=''; }}>
        <div className="relative w-full max-w-[900px] h-[85vh] sm:h-auto sm:min-h-[500px] bg-[#0a0a0a] rounded-3xl overflow-hidden flex flex-col md:flex-row shadow-[0_0_80px_rgba(37,99,235,0.15)] ring-1 ring-white/10" style={{ margin: 'auto' }}>
          
          <div className={`absolute top-0 left-0 w-full md:w-1/2 h-1/2 md:h-full bg-[#2563eb] z-0 transition-transform duration-[800ms] ease-[cubic-bezier(0.8,0,0.2,1)] ${authMode === 'signup' ? 'translate-y-full md:translate-y-0 md:translate-x-full' : 'translate-y-0 md:translate-x-0'}`}>
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-white/20 blur-[80px] rounded-full mix-blend-overlay"></div>
          </div>

          <button className="absolute right-4 top-4 text-white/50 hover:text-white z-50 transition-colors bg-white/10 p-2 rounded-full backdrop-blur-md border border-white/20 cursor-pointer" aria-label="Close modal" onClick={(e) => { e.preventDefault(); document.getElementById('login-modal')?.classList.remove('active'); document.body.style.overflow=''; }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>

          <div className="flex-1 relative z-10 flex flex-col justify-center p-8 sm:p-14 overflow-hidden text-left">
              <div className="relative z-10 flex flex-col items-start text-white">
                  <div className="flex items-center gap-3 mb-6 sm:mb-10">
                     <div className="w-10 h-10 rounded-xl bg-white text-black flex items-center justify-center font-bold text-xl shadow-lg ring-4 ring-white/10">C</div>
                     <span className="text-xl font-bold tracking-tight">ClipPods</span>
                  </div>
                  <h2 className="text-2xl sm:text-4xl font-bold mb-3 sm:mb-4 tracking-tight leading-tight m-0" style={{ color: 'white' }}>
                     India’s first AI viral clip generator.
                  </h2>
                  <p className={`text-sm sm:text-base leading-relaxed max-w-sm transition-colors duration-[800ms] m-0 ${authMode === 'signup' ? 'text-gray-400' : 'text-blue-100'}`}>
                     Join thousands of creators turning long podcasts into highly optimized shorts and visual gold in seconds. Fully optimized for English, Hindi, and Tamil creators.
                  </p>
              </div>
          </div>

          <div className="flex-1 relative z-10 flex flex-col justify-center p-6 sm:p-12 border-t md:border-t-0 md:border-l border-white/5 text-left">
              <div className="max-w-[340px] mx-auto w-full relative z-10 text-white">
                  <h3 className="text-xl sm:text-2xl font-bold mb-1.5 sm:mb-2 tracking-tight text-white m-0">{authMode === 'signup' ? 'Create your account' : 'Welcome back'}</h3>
                  <p className={`text-xs sm:text-sm mb-6 transition-colors duration-[800ms] m-0 ${authMode === 'signup' ? 'text-blue-100' : 'text-gray-400'}`}>
                     {authMode === 'signup' ? 'Sign up to generate unlimited clips.' : 'Log in to continue clipping.'}
                  </p>
                  
                  <button type="button" onClick={handleGoogleSignIn} disabled={authLoading} className={`w-full py-3 rounded-xl font-semibold flex items-center justify-center gap-3 transition-colors duration-500 disabled:opacity-50 mb-5 shadow-lg cursor-pointer border-none active:scale-[0.98] ${authMode === 'signup' ? 'bg-white text-[#2563eb] hover:bg-gray-100 ring-2 ring-white/50' : 'bg-white text-black hover:bg-gray-200 ring-2 ring-white/10'}`}>
                    <svg width="20" height="20" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                    <span className="text-sm">Continue with Google</span>
                  </button>

                  <form onSubmit={submitAuth} className="flex flex-col gap-3 m-0 p-0 text-left">
                    {authMode === 'signup' && (
                      <div className="flex flex-col text-left">
                        <input type="text" value={authWorkspaceName} onChange={e=>setAuthWorkspaceName(e.target.value)} className={`w-full bg-black/40 border rounded-xl p-2.5 sm:p-3 text-white outline-none focus:bg-white/10 transition-all text-sm font-medium backdrop-blur-md shadow-inner m-0 ${authMode === 'signup' ? 'border-white/30 placeholder-white/60 focus:border-white focus:ring-2 focus:ring-white/30' : 'border-white/10 placeholder-gray-500 focus:border-white/40'}`} placeholder="My Studio Space" required />
                      </div>
                    )}
                    <div className="flex flex-col text-left">
                      <input type="email" value={authEmail} onChange={e=>setAuthEmail(e.target.value)} className={`w-full bg-black/40 border rounded-xl p-2.5 sm:p-3 text-white outline-none focus:bg-white/10 transition-all text-sm font-medium backdrop-blur-md shadow-inner m-0 ${authMode === 'signup' ? 'border-white/30 placeholder-white/60 focus:border-white focus:ring-2 focus:ring-white/30' : 'border-white/10 placeholder-gray-500 focus:border-white/40'}`} placeholder="you@example.com" required />
                    </div>
                    <div className={`grid gap-3 ${authMode === 'signup' ? 'grid-cols-2' : 'grid-cols-1'}`}>
                        <div className="relative">
                          <input type={showPassword ? 'text' : 'password'} value={authPassword} onChange={e=>setAuthPassword(e.target.value)} className={`w-full bg-black/40 border rounded-xl p-2.5 sm:p-3 text-white outline-none focus:bg-white/10 transition-all text-sm font-medium backdrop-blur-md shadow-inner pr-9 m-0 ${authMode === 'signup' ? 'border-white/30 placeholder-white/60 focus:border-white focus:ring-2 focus:ring-white/30' : 'border-white/10 placeholder-gray-500 focus:border-white/40 focus:ring-2 focus:ring-gray-400/30'}`} placeholder="Password" required minLength={8} />
                          <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white transition-colors focus:outline-none cursor-pointer bg-transparent border-none p-0 m-0" aria-label="Toggle password visibility">
                             <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                {showPassword ? (
                                  <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>
                                ) : (
                                  <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></>
                                )}
                             </svg>
                          </button>
                        </div>
                        {authMode === 'signup' && (
                           <div className="relative">
                             <input type={showPassword ? 'text' : 'password'} value={authConfirm} onChange={e=>setAuthConfirm(e.target.value)} className={`w-full bg-black/40 border rounded-xl p-2.5 sm:p-3 text-white outline-none focus:bg-white/10 transition-all text-sm font-medium backdrop-blur-md shadow-inner pr-9 m-0 ${authMode === 'signup' ? 'border-white/30 placeholder-white/60 focus:border-white focus:ring-2 focus:ring-white/30' : 'border-white/10 placeholder-gray-500 focus:border-white/40'}`} placeholder="Confirm" required minLength={8} />
                           </div>
                        )}
                    </div>
                    {authError && <div className="text-red-400 bg-black/40 border border-red-400/30 rounded-lg p-2.5 mt-1 text-xs font-medium text-center shadow-md backdrop-blur-md">{authError}</div>}
                    <button type="submit" disabled={authLoading} className={`mt-1 sm:mt-2 w-full font-bold py-3.5 rounded-xl transition-all duration-300 disabled:opacity-50 text-sm shadow-xl active:scale-[0.98] cursor-pointer border-none ${authMode === 'signup' ? 'bg-[#0a0a0a] text-white hover:bg-black ring-1 ring-white/10' : 'bg-white text-black hover:bg-gray-200'}`}>
                      {authLoading ? 'Please wait...' : (authMode === 'signup' ? 'Create Account' : 'Secure Log In')}
                    </button>
                  </form>

                  <p className={`text-xs sm:text-sm text-center mt-5 sm:mt-6 transition-colors duration-[800ms] m-0 ${authMode === 'signup' ? 'text-blue-100' : 'text-gray-400'}`}>
                    <span>{authMode === 'signup' ? 'Already have an account?' : "Don't have an account?"}</span>{' '}
                    <button type="button" onClick={() => setAuthMode(authMode === 'signup' ? 'login' : 'signup')} className="font-semibold text-white hover:underline focus:outline-none bg-transparent border-none cursor-pointer p-0 m-0 shadow-none">
                      {authMode === 'signup' ? 'Log In' : 'Sign Up'}
                    </button>
                  </p>
              </div>
          </div>
        </div>
      </div>

      {/* Free Trial Modal Removed */}

      {/* Landing page JS — loaded after DOM */}
      <Script src="/landing/app.js" strategy="lazyOnload" />
    </>
  )
}

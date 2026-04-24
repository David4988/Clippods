/* ═══════════════════════════════════════════════════
   ClipPods — Premium Application Logic
   Cursor glow, parallax grid, animated counters,
   text reveals, scroll animations, magnetic buttons,
   metric bars, connector line, waveform, form handling
   ═══════════════════════════════════════════════════ */

(function () {
  'use strict';

  // ═══════════════════ PAGE LOADER ═══════════════════
  var loader = document.getElementById('page-loader');
  var loaderDone = false;

  function hideLoader() {
    if (loaderDone) return;
    loaderDone = true;
    if (loader) {
      loader.classList.add('hidden');
    }
    document.body.style.overflow = '';
    requestAnimationFrame(function () {
      initAllAnimations();
    });
  }

  document.body.style.overflow = 'hidden';
  window.addEventListener('load', function () {
    setTimeout(hideLoader, 1600);
  });
  setTimeout(hideLoader, 3500); // Fallback

  // ═══════════════════ HERO DOT GRID ═══════════════════
  var gridCanvas = document.getElementById('hero-grid');
  if (gridCanvas) {
    var ctx = gridCanvas.getContext('2d');
    var gridW, gridH;

    function resizeGrid() {
      var hero = document.getElementById('hero');
      if (!hero) return;
      gridW = hero.offsetWidth;
      gridH = hero.offsetHeight;
      gridCanvas.width = gridW * window.devicePixelRatio;
      gridCanvas.height = gridH * window.devicePixelRatio;
      gridCanvas.style.width = gridW + 'px';
      gridCanvas.style.height = gridH + 'px';
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
      drawGrid();
    }

    function drawGrid() {
      ctx.clearRect(0, 0, gridW, gridH);
      var spacing = 40;
      var dotSize = 1;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.08)';

      for (var x = spacing; x < gridW; x += spacing) {
        for (var y = spacing; y < gridH; y += spacing) {
          var distFromCenter = Math.sqrt(
            Math.pow((x - gridW / 2) / (gridW / 2), 2) +
            Math.pow((y - gridH / 2) / (gridH / 2), 2)
          );
          var alpha = Math.max(0, 1 - distFromCenter * 0.8);
          ctx.globalAlpha = alpha * 0.5;
          ctx.beginPath();
          ctx.arc(x, y, dotSize, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;
    }

    var mouseGridX = 0, mouseGridY = 0;
    document.addEventListener('mousemove', function (e) {
      var hero = document.getElementById('hero');
      if (!hero) return;
      var rect = hero.getBoundingClientRect();
      mouseGridX = e.clientX - rect.left;
      mouseGridY = e.clientY - rect.top;
    });

    function drawGridActive() {
      ctx.clearRect(0, 0, gridW, gridH);
      var spacing = 40;
      var dotSize = 1;

      for (var x = spacing; x < gridW; x += spacing) {
        for (var y = spacing; y < gridH; y += spacing) {
          var dx = x - mouseGridX;
          var dy = y - mouseGridY;
          var dist = Math.sqrt(dx * dx + dy * dy);
          var proximity = Math.max(0, 1 - dist / 250);
          var baseAlpha = 0.06;
          var brightAlpha = 0.35;
          var alpha = baseAlpha + (brightAlpha - baseAlpha) * proximity;

          if (proximity > 0.1) {
            ctx.fillStyle = 'rgba(255, 255, 255, ' + (alpha * proximity) + ')';
          } else {
            ctx.fillStyle = 'rgba(255, 255, 255, ' + alpha + ')';
          }

          ctx.beginPath();
          ctx.arc(x, y, dotSize + proximity * 1.2, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      requestAnimationFrame(drawGridActive);
    }

    window.addEventListener('resize', resizeGrid);
    resizeGrid();

    if (window.matchMedia('(hover: hover)').matches) {
      requestAnimationFrame(drawGridActive);
    }
  }

  // ═══════════════════ NAVBAR ═══════════════════
  var navbar = document.getElementById('navbar');

  function handleNavScroll() {
    if (!navbar) return;
    if (window.scrollY > 40) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  }
  window.addEventListener('scroll', handleNavScroll, { passive: true });

  // Mobile toggle
  var navToggle = document.getElementById('nav-toggle');
  var navLinks = document.getElementById('nav-links');
  if (navToggle && navLinks) {
    navToggle.addEventListener('click', function () {
      navLinks.classList.toggle('open');
    });
    navLinks.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        navLinks.classList.remove('open');
      });
    });
  }

  // Smooth scroll
  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
      var targetId = this.getAttribute('href');
      if (targetId === '#') return;
      var target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        var navH = navbar ? navbar.offsetHeight : 72;
        var pos = target.getBoundingClientRect().top + window.scrollY - navH - 20;
        window.scrollTo({ top: pos, behavior: 'smooth' });
      }
    });
  });

  // ═══════════════════ HERO TEXT REVEAL ═══════════════════
  function wrapWordsForReveal() {
    var heroTitle = document.querySelector('.hero-title');
    if (!heroTitle || heroTitle.dataset.wrapped) return;
    heroTitle.dataset.wrapped = 'true';

    var fragment = document.createDocumentFragment();
    var nodes = Array.from(heroTitle.childNodes);

    nodes.forEach(function (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        var words = node.textContent.split(/(\s+)/);
        words.forEach(function (w) {
          if (w.match(/^\s+$/)) {
            fragment.appendChild(document.createTextNode(w));
          } else if (w.length > 0) {
            var span = document.createElement('span');
            span.className = 'word';
            var inner = document.createElement('span');
            inner.className = 'word-inner';
            inner.textContent = w;
            span.appendChild(inner);
            fragment.appendChild(span);
          }
        });
      } else if (node.tagName === 'BR') {
        fragment.appendChild(node.cloneNode());
      } else {
        var words = node.textContent.split(/(\s+)/);
        words.forEach(function (w) {
          if (w.match(/^\s+$/)) {
            fragment.appendChild(document.createTextNode(w));
          } else if (w.length > 0) {
            var wrapper = node.cloneNode(false);
            var span = document.createElement('span');
            span.className = 'word';
            var inner = document.createElement('span');
            inner.className = 'word-inner';
            inner.textContent = w;
            span.appendChild(inner);
            wrapper.appendChild(span);
            fragment.appendChild(wrapper);
          }
        });
      }
    });

    heroTitle.innerHTML = '';
    heroTitle.appendChild(fragment);
  }

  // ═══════════════════ ANIMATED COUNTERS ═══════════════════
  function animateCounter(el) {
    var target = parseInt(el.getAttribute('data-count'), 10);
    var suffix = el.getAttribute('data-suffix') || '';
    var duration = 1500;
    var start = 0;
    var startTime = null;

    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = Math.round(start + (target - start) * eased);
      el.textContent = current + suffix;
      if (progress < 1) {
        requestAnimationFrame(step);
      }
    }

    requestAnimationFrame(step);
  }

  // ═══════════════════ METRIC BARS ═══════════════════
  function animateMetricBar(card) {
    var bar = card.querySelector('.metric-bar');
    if (bar && !bar.classList.contains('animated')) {
      bar.classList.add('animated');
      bar.style.width = bar.getAttribute('data-width') + '%';
    }
    var value = card.querySelector('.metric-value');
    if (value && !value.dataset.counted) {
      value.dataset.counted = 'true';
      animateCounter(value);
    }
  }

  // ═══════════════════ CONNECTOR LINE ═══════════════════
  function animateConnector() {
    var line = document.getElementById('connector-line');
    if (line && !line.classList.contains('animated')) {
      line.classList.add('animated');
    }
  }

  // ═══════════════════ FEATURE CARD TILT ═══════════════════
  if (window.matchMedia('(hover: hover)').matches) {
    document.querySelectorAll('.feature-card').forEach(function (card) {
      card.addEventListener('mouseenter', function () {
        card.classList.add('tilting');
      });

      card.addEventListener('mousemove', function (e) {
        var rect = card.getBoundingClientRect();
        var x = (e.clientX - rect.left) / rect.width;
        var y = (e.clientY - rect.top) / rect.height;
        var tiltX = (y - 0.5) * 6;
        var tiltY = (x - 0.5) * -6;
        card.style.transform = 'perspective(600px) rotateX(' + tiltX + 'deg) rotateY(' + tiltY + 'deg) translateY(-2px)';
      });

      card.addEventListener('mouseleave', function () {
        card.classList.remove('tilting');
        card.style.transform = '';
      });
    });
  }

  // ═══════════════════ SCROLL ANIMATIONS ═══════════════════
  function initAllAnimations() {
    wrapWordsForReveal();

    var animItems = document.querySelectorAll('.anim-item');

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var el = entry.target;
          var delay = parseInt(el.getAttribute('data-delay') || '0', 10);

          setTimeout(function () {
            el.classList.add('visible');

            if (el.classList.contains('hero-title') || el.querySelector('.hero-title')) {
              var title = el.classList.contains('hero-title') ? el : el.querySelector('.hero-title');
              if (title) {
                setTimeout(function () { title.classList.add('revealed'); }, 100);
              }
            }

            el.querySelectorAll('[data-count]').forEach(function (counter) {
              if (!counter.dataset.counted) {
                counter.dataset.counted = 'true';
                animateCounter(counter);
              }
            });
            if (el.hasAttribute('data-count') && !el.dataset.counted) {
              el.dataset.counted = 'true';
              animateCounter(el);
            }

            if (el.classList.contains('metric-card')) {
              animateMetricBar(el);
            }

            if (el.classList.contains('step-card')) {
              animateConnector();
            }

          }, delay * 100);

          observer.unobserve(el);
        }
      });
    }, {
      root: null,
      rootMargin: '0px 0px -50px 0px',
      threshold: 0.1
    });

    animItems.forEach(function (item) { observer.observe(item); });

    var heroTitle = document.querySelector('.hero-title');
    if (heroTitle) {
      var titleObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            heroTitle.classList.add('revealed');
            titleObserver.unobserve(entry.target);
          }
        });
      }, { threshold: 0.1 });
      titleObserver.observe(heroTitle);
    }
  }

  // ═══════════════════ PARALLAX (subtle) ═══════════════════
  var heroGlow = document.querySelector('.hero-glow');
  if (heroGlow) {
    window.addEventListener('scroll', function () {
      var scrollY = window.scrollY;
      heroGlow.style.transform = 'translateX(-50%) translateY(' + (scrollY * 0.15) + 'px)';
    }, { passive: true });
  }

  // ═══════════════════ SCROLL-DRIVEN MARQUEE ═══════════════════
  (function initScrollMarquee() {
    var section = document.getElementById('marquee-section');
    var content = document.getElementById('marquee-content');
    if (!section || !content) return;

    var currentX = 0;
    var targetX = 0;
    var speed = 1.2;

    function onScroll() {
      var rect = section.getBoundingClientRect();
      var viewportH = window.innerHeight;
      var sectionCenter = rect.top + rect.height / 2;
      var offset = (viewportH / 2) - sectionCenter;
      targetX = Math.max(0, offset * speed);
    }

    function smoothLoop() {
      currentX += (targetX - currentX) * 0.08;
      if (Math.abs(currentX - targetX) < 0.3) currentX = targetX;
      content.style.transform = 'translateX(' + (-currentX) + 'px)';
      requestAnimationFrame(smoothLoop);
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    onScroll();
    requestAnimationFrame(smoothLoop);
  })();

  // ═══════════════════ DEMO WAVEFORM ═══════════════════
  function animateWaveform() {
    var bars = document.querySelectorAll('.wave-bar:not(.highlight)');
    bars.forEach(function (bar) {
      var baseH = parseInt(bar.style.height) || 30;
      var variance = 12;
      var newH = baseH + (Math.random() * variance * 2 - variance);
      bar.style.height = Math.max(10, Math.min(90, newH)) + '%';
    });
  }
  setInterval(animateWaveform, 2000);

  // ═══════════════════ HIW WAVEFORM VISUALIZER ═══════════════════
  (function initHIWWaveform() {
    var barsContainer = document.getElementById('hiw-waveform-bars');
    var progressFill = document.getElementById('waveform-progress-fill');
    var playhead = document.getElementById('waveform-playhead');
    var timeCurrent = document.getElementById('waveform-time-current');
    if (!barsContainer) return;

    var barCount = 60;
    var pattern = [];

    var speechGroups = [
      { start: 0, end: 8, peak: 0.7 },
      { start: 10, end: 18, peak: 0.9 },
      { start: 20, end: 24, peak: 0.5 },
      { start: 26, end: 36, peak: 0.85 },
      { start: 38, end: 40, peak: 0.4 },
      { start: 42, end: 52, peak: 0.95 },
      { start: 54, end: 59, peak: 0.6 }
    ];

    for (var i = 0; i < barCount; i++) {
      var groupPeak = 0.15;
      for (var g = 0; g < speechGroups.length; g++) {
        if (i >= speechGroups[g].start && i <= speechGroups[g].end) {
          var groupMid = (speechGroups[g].start + speechGroups[g].end) / 2;
          var groupHalf = (speechGroups[g].end - speechGroups[g].start) / 2;
          var dist = Math.abs(i - groupMid) / Math.max(groupHalf, 1);
          groupPeak = speechGroups[g].peak * (1 - dist * 0.4);
          break;
        }
      }
      var variation = (Math.random() - 0.5) * 0.25;
      var height = Math.max(0.08, Math.min(1, groupPeak + variation));
      pattern.push(height);
    }

    var bars = [];
    for (var j = 0; j < barCount; j++) {
      var bar = document.createElement('div');
      bar.className = 'wv-bar';
      var h = Math.round(pattern[j] * 90 + 6);
      bar.style.height = h + '%';
      bar.style.setProperty('--bar-delay', (j * 15) + 'ms');
      bar.dataset.baseHeight = h;
      barsContainer.appendChild(bar);
      bars.push(bar);
    }

    var totalDuration = 58 * 60 + 42;
    var cycleDuration = 20000;
    var startTime = null;
    var animRunning = false;

    function formatTime(seconds) {
      var m = Math.floor(seconds / 60);
      var s = Math.floor(seconds % 60);
      return m + ':' + (s < 10 ? '0' : '') + s;
    }

    function animatePlayback(timestamp) {
      if (!animRunning) return;
      if (!startTime) startTime = timestamp;

      var elapsed = (timestamp - startTime) % cycleDuration;
      var progress = elapsed / cycleDuration;
      var pct = progress * 100;
      if (progressFill) progressFill.style.width = pct + '%';
      if (playhead) playhead.style.left = pct + '%';

      var currentSec = Math.floor(progress * totalDuration);
      if (timeCurrent) timeCurrent.textContent = formatTime(currentSec);

      var activeBarIndex = Math.floor(progress * barCount);

      for (var k = 0; k < bars.length; k++) {
        var baseH = parseFloat(bars[k].dataset.baseHeight);
        var speed1 = 0.003 + (k % 7) * 0.0005;
        var speed2 = 0.0018 + (k % 5) * 0.0004;
        var speed3 = 0.005 + (k % 3) * 0.0007;
        var phase = k * 0.8;
        var wave1 = Math.sin(timestamp * speed1 + phase) * 12;
        var wave2 = Math.sin(timestamp * speed2 + phase * 1.3) * 6;
        var wave3 = Math.sin(timestamp * speed3 + phase * 0.7) * 3;
        var totalWave = wave1 + wave2 + wave3;
        var distFromHead = Math.abs(k - activeBarIndex);
        var intensity = distFromHead < 3 ? 1.6 : (distFromHead < 6 ? 1.2 : 1.0);
        var newH = baseH + totalWave * intensity;
        bars[k].style.height = Math.max(5, Math.min(98, newH)) + '%';
        bars[k].classList.remove('active', 'played');
        if (k < activeBarIndex) {
          bars[k].classList.add('played');
        } else if (distFromHead <= 1) {
          bars[k].classList.add('active');
        }
      }
      requestAnimationFrame(animatePlayback);
    }

    var waveformEl = document.getElementById('hiw-waveform');
    var wvObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && !animRunning) {
          animRunning = true;
          startTime = null;
          requestAnimationFrame(animatePlayback);
        }
        if (!entry.isIntersecting) {
          animRunning = false;
        }
      });
    }, { threshold: 0.3 });

    if (waveformEl) {
      wvObserver.observe(waveformEl);
    }
  })();

  // ═══════════════════ FEEDBACK FORM ═══════════════════
  var feedbackForm = document.getElementById('feedback-form');
  var formSuccess = document.getElementById('form-success');

  if (feedbackForm) {
    feedbackForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var submitBtn = document.getElementById('feedback-submit');
      var btnText = submitBtn.querySelector('.btn-text');

      submitBtn.disabled = true;
      if (btnText) btnText.textContent = 'Sending...';

      setTimeout(function () {
        feedbackForm.reset();
        submitBtn.disabled = false;
        if (btnText) btnText.textContent = 'Send Feedback';
        formSuccess.classList.add('visible');

        setTimeout(function () {
          formSuccess.classList.remove('visible');
        }, 5000);
      }, 1200);
    });
  }

  // ═══════════════════ ACTIVE NAV HIGHLIGHT ═══════════════════
  var sections = document.querySelectorAll('section[id]');
  var navLinkItems = document.querySelectorAll('.nav-links a');

  function highlightActiveNav() {
    if (!navbar) return;
    var scrollPos = window.scrollY + navbar.offsetHeight + 100;
    sections.forEach(function (sec) {
      var top = sec.offsetTop;
      var bottom = top + sec.offsetHeight;
      if (scrollPos >= top && scrollPos < bottom) {
        var id = sec.getAttribute('id');
        navLinkItems.forEach(function (link) {
          if (link.getAttribute('href') === '#' + id) {
            link.style.color = 'var(--text)';
          } else {
            link.style.color = '';
          }
        });
      }
    });
  }
  window.addEventListener('scroll', highlightActiveNav, { passive: true });

  // ═══════════════════ SIGNUP MODAL & TRIAL STATE ═══════════════════
  var signupModal = document.getElementById('signup-modal');
  var modalClose = document.getElementById('modal-close');
  var signupForm = document.getElementById('signup-form');

  // Tab Switching Logic
  var tabBtns = document.querySelectorAll('.tab-btn');
  var tabContents = document.querySelectorAll('.tab-content');

  tabBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      tabBtns.forEach(function(b) { b.classList.remove('active'); });
      tabContents.forEach(function(c) { c.classList.remove('active'); });
      btn.classList.add('active');
      var targetId = btn.getAttribute('data-tab');
      var targetEl = document.getElementById(targetId);
      if (targetEl) targetEl.classList.add('active');
    });
  });

  var navLoginBtn = document.getElementById('nav-login-btn');
  var loginModal = document.getElementById('login-modal');
  var loginModalClose = document.getElementById('login-modal-close');
  var loginForm = document.getElementById('login-form');
  var pendingPaymentBtn = null;

  function checkAuthState() {
    var isLoggedIn = localStorage.getItem('user_logged_in') === 'true';
    if (isLoggedIn && navLoginBtn) {
      navLoginBtn.textContent = 'Account';
    }
  }
  checkAuthState();

  var signupTriggers = [
    document.querySelector('#pricing-student-btn'),
    document.querySelector('#pricing-creator-btn'),
    document.querySelector('#pricing-podcast-btn')
  ].filter(Boolean);

  // Open modal logic
  signupTriggers.forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      if(btn.getAttribute('href') === '#pricing' && !btn.classList.contains('pricing-btn')) return;

      var isTrialActive = localStorage.getItem('trial_active') === 'true';
      var isTrialUsed = localStorage.getItem('trial_used') === 'true';
      var isLoggedIn = localStorage.getItem('user_logged_in') === 'true';

      if (!isLoggedIn) {
        e.preventDefault();
        pendingPaymentBtn = btn;
        if (loginModal) {
          loginModal.classList.add('active');
          document.body.style.overflow = 'hidden';
        }
        return;
      }

      if (isTrialUsed) {
        e.preventDefault();
        alert('Free trial used. Upgrade to continue using ClipPods.');
        return;
      }

      if (isTrialActive) {
        e.preventDefault();
        window.location.href = '/dashboard';
        return;
      }

      e.preventDefault();

      if (!signupModal) return;
      var modalTitle = signupModal.querySelector('.modal-title');
      var modalDesc = signupModal.querySelector('.modal-desc');
      var submitBtnText = signupModal.querySelector('#signup-submit .btn-text');

      if (btn.id === 'pricing-student-btn') {
        modalTitle.textContent = 'Start Your Free Trial';
        modalDesc.textContent = '1 free processing for 3 days, then ₹99/month. Cancel anytime.';
        submitBtnText.textContent = 'Start Free Trial';
      } else {
        var planName = btn.id === 'pricing-creator-btn' ? 'Creator' : 'Podcast Pro';
        var planPrice = btn.id === 'pricing-creator-btn' ? '₹499' : '₹999';
        modalTitle.textContent = 'Get Started with ' + planName;
        modalDesc.textContent = 'Subscribe for ' + planPrice + '/month to begin processing clips instantly.';
        submitBtnText.textContent = 'Complete Payment (' + planPrice + ')';
      }

      signupModal.classList.add('active');
      document.body.style.overflow = 'hidden';
    });
  });

  function closeSignupModal() {
    if (signupModal) signupModal.classList.remove('active');
    document.body.style.overflow = '';
  }

  if (modalClose) {
    modalClose.addEventListener('click', closeSignupModal);
  }

  // Handle Login Modal Logic
  function closeLoginModal() {
    if (loginModal) loginModal.classList.remove('active');
    document.body.style.overflow = '';
    pendingPaymentBtn = null;
  }

  if (loginModalClose) {
    loginModalClose.addEventListener('click', closeLoginModal);
  }

  if (navLoginBtn) {
    navLoginBtn.addEventListener('click', function(e) {
       e.preventDefault();
       var isLoggedIn = localStorage.getItem('user_logged_in') === 'true';
       if (isLoggedIn) {
           var confirmLogout = confirm('Are you sure you want to log out? (This will additionally reset your trial data so you can test the Free Trial Payment UI again natively without being blocked)');
           if (confirmLogout) {
               localStorage.removeItem('user_logged_in');
               localStorage.removeItem('trial_active');
               localStorage.removeItem('trial_used');
               navLoginBtn.textContent = 'Sign Up';
               alert('Securely logged out and trial constraints reset.');
           }
       } else {
           if (loginModal) {
             loginModal.classList.add('active');
             document.body.style.overflow = 'hidden';
           }
       }
    });
  }

  if (loginModal) {
    loginModal.addEventListener('click', function(e) {
      if (e.target === loginModal) {
        closeLoginModal();
      }
    });
  }

  var authToggleBtn = document.getElementById('auth-toggle-btn');
  var authMode = 'signup';

  if (authToggleBtn) {
    authToggleBtn.addEventListener('click', function(e) {
      e.preventDefault();
      var authTitle = document.getElementById('auth-title');
      var authDesc = document.getElementById('auth-desc');
      var authConfirmGroup = document.getElementById('auth-confirm-group');
      var authConfirmPass = document.getElementById('auth-confirm-password');
      var authBtnText = document.getElementById('auth-btn-text');
      var authHint = document.getElementById('auth-toggle-hint');

      if (authMode === 'signup') {
        authMode = 'login';
        if (authTitle) authTitle.textContent = 'Log In to ClipPods';
        if (authDesc) authDesc.textContent = 'Welcome back! Please enter your details.';
        if (authConfirmGroup) authConfirmGroup.style.display = 'none';
        if (authConfirmPass) authConfirmPass.required = false;
        if (authBtnText) authBtnText.textContent = 'Log In';
        if (authHint) authHint.textContent = "Don't have an account?";
        authToggleBtn.textContent = 'Sign Up';
      } else {
        authMode = 'signup';
        if (authTitle) authTitle.textContent = 'Create an Account';
        if (authDesc) authDesc.textContent = 'Sign up to unlock podcast processing.';
        if (authConfirmGroup) authConfirmGroup.style.display = 'block';
        if (authConfirmPass) authConfirmPass.required = true;
        if (authBtnText) authBtnText.textContent = 'Sign Up';
        if (authHint) authHint.textContent = 'Already have an account?';
        authToggleBtn.textContent = 'Log In';
      }
    });
  }

  if (loginForm) {
    loginForm.addEventListener('submit', function(e) {
      e.preventDefault();
      var submitBtn = document.getElementById('login-submit');
      if (!submitBtn) return;
      var originalText = submitBtn.querySelector('.btn-text').textContent;

      submitBtn.querySelector('.btn-text').textContent = 'Authenticating...';
      submitBtn.disabled = true;

      setTimeout(function() {
        submitBtn.querySelector('.btn-text').textContent = 'Success!';
        localStorage.setItem('user_logged_in', 'true');
        checkAuthState();

        setTimeout(function() {
          if (loginModal) loginModal.classList.remove('active');
          loginForm.reset();
          submitBtn.disabled = false;
          submitBtn.querySelector('.btn-text').textContent = originalText;

          if (pendingPaymentBtn) {
             var triggerObj = pendingPaymentBtn;
             pendingPaymentBtn = null;
             setTimeout(function() { triggerObj.click(); }, 300);
          } else {
             document.body.style.overflow = '';
          }
        }, 800);
      }, 1500);
    });
  }

  if (signupModal) {
    signupModal.addEventListener('click', function(e) {
      if (e.target === signupModal) {
        closeSignupModal();
      }
    });
  }

  // Handle form submit (Simulated Paytm Processing)
  if (signupForm) {
    signupForm.addEventListener('submit', function(e) {
      e.preventDefault();
      var submitBtn = document.getElementById('signup-submit');
      if (!submitBtn) return;
      var originalText = submitBtn.querySelector('.btn-text').textContent;

      submitBtn.querySelector('.btn-text').textContent = 'Processing Payment...';
      submitBtn.disabled = true;

      setTimeout(function() {
        submitBtn.querySelector('.btn-text').textContent = 'Trial Activated!';
        localStorage.setItem('trial_active', 'true');

        setTimeout(function() {
          closeSignupModal();
          signupForm.reset();
          submitBtn.disabled = false;
          submitBtn.querySelector('.btn-text').textContent = originalText;
          // Redirect to real dashboard
          window.location.href = '/dashboard';
        }, 1200);
      }, 2000);
    });
  }

})();

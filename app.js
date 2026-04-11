/* ═══════════════════════════════════════════════════
   ClipPods — Integrated Application Logic
   Landing page: cursor glow, parallax grid, animated counters,
     text reveals, scroll animations, magnetic buttons,
     metric bars, connector line, waveform, form handling
   App dashboard: file upload, status polling, clip display
   ═══════════════════════════════════════════════════ */

(function () {
  'use strict';

  /* ╔═══════════════════════════════════════════════╗
     ║  SECTION A — LANDING PAGE (index.html)        ║
     ╚═══════════════════════════════════════════════╝ */

  // ═══════════════════ PAGE LOADER ═══════════════════
  var loader = document.getElementById('page-loader');
  var loaderDone = false;

  function hideLoader() {
    if (loaderDone) return;
    loaderDone = true;
    if (loader) loader.classList.add('hidden');
    document.body.style.overflow = '';
    requestAnimationFrame(function () {
      initAllAnimations();
    });
  }

  if (loader) {
    document.body.style.overflow = 'hidden';
    window.addEventListener('load', function () {
      setTimeout(hideLoader, 1600);
    });
    setTimeout(hideLoader, 3500); // Fallback
  } else {
    // No loader on app page — fire animations immediately
    window.addEventListener('load', function () {
      initAllAnimations();
    });
  }

  // ═══════════════════ CURSOR GLOW ═══════════════════
  var cursorGlow = document.getElementById('cursor-glow');
  var cursorX = 0, cursorY = 0, glowX = 0, glowY = 0;

  if (window.matchMedia('(hover: hover)').matches && cursorGlow) {
    document.addEventListener('mousemove', function (e) {
      cursorX = e.clientX;
      cursorY = e.clientY;
      if (!cursorGlow.classList.contains('active')) {
        cursorGlow.classList.add('active');
      }
    });

    document.addEventListener('mouseleave', function () {
      cursorGlow.classList.remove('active');
    });

    (function animateGlow() {
      glowX += (cursorX - glowX) * 0.08;
      glowY += (cursorY - glowY) * 0.08;
      cursorGlow.style.left = glowX + 'px';
      cursorGlow.style.top = glowY + 'px';
      requestAnimationFrame(animateGlow);
    })();
  }

  // ═══════════════════ HERO DOT GRID ═══════════════════
  var gridCanvas = document.getElementById('hero-grid');
  if (gridCanvas) {
    var ctx = gridCanvas.getContext('2d');
    var gridW, gridH;

    function resizeGrid() {
      var hero = document.getElementById('hero');
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
            ctx.fillStyle = 'rgba(201, 162, 74, ' + (alpha * proximity) + ')';
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

  if (navbar) {
    function handleNavScroll() {
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
          var navH = navbar.offsetHeight;
          var pos = target.getBoundingClientRect().top + window.scrollY - navH - 20;
          window.scrollTo({ top: pos, behavior: 'smooth' });
        }
      });
    });
  }

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

  // ═══════════════════ MAGNETIC BUTTONS ═══════════════════
  if (window.matchMedia('(hover: hover)').matches) {
    var magnetics = document.querySelectorAll('.magnetic');
    magnetics.forEach(function (btn) {
      btn.addEventListener('mousemove', function (e) {
        var rect = btn.getBoundingClientRect();
        var x = e.clientX - rect.left - rect.width / 2;
        var y = e.clientY - rect.top - rect.height / 2;
        btn.style.transform = 'translate(' + (x * 0.15) + 'px, ' + (y * 0.15) + 'px) scale(1.02)';
      });

      btn.addEventListener('mouseleave', function () {
        btn.style.transform = '';
      });
    });
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

    if (animItems.length > 0) {
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
    }

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

    // Initialize app dashboard if elements exist
    initAppDashboard();
  }

  // ═══════════════════ PARALLAX (subtle) ═══════════════════
  var heroGlow = document.querySelector('.hero-glow');
  if (heroGlow) {
    window.addEventListener('scroll', function () {
      var scrollY = window.scrollY;
      heroGlow.style.transform = 'translateX(-50%) translateY(' + (scrollY * 0.15) + 'px)';
    }, { passive: true });
  }

  // ═══════════════════ WAVEFORM ═══════════════════
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

  if (navbar && navLinkItems.length > 0) {
    function highlightActiveNav() {
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
  }


  /* ╔═══════════════════════════════════════════════╗
     ║  SECTION B — APP DASHBOARD (app.html)        ║
     ╚═══════════════════════════════════════════════╝ */

  var API_BASE = '';
  var POLL_INTERVAL_MS = 3000;

  function initAppDashboard() {
    // --- DOM Elements (only exist on app.html) ---
    var fileInput = document.getElementById('file-input');
    var uploadBtn = document.getElementById('upload-btn');
    var uploadStatus = document.getElementById('upload-status');
    var uploadSection = document.getElementById('upload-section');
    var statusSection = document.getElementById('status-section');
    var progressBar = document.getElementById('progress-bar');
    var statusText = document.getElementById('status-text');
    var resultsSection = document.getElementById('results-section');
    var clipsContainer = document.getElementById('clips-container');

    // Guard: skip if not on app dashboard page
    if (!fileInput || !uploadBtn) return;

    var currentJobId = null;
    var pollTimer = null;

    // --- File Selection ---
    fileInput.addEventListener('change', function () {
      uploadBtn.disabled = !fileInput.files.length;
    });

    // --- Upload ---
    uploadBtn.addEventListener('click', async function () {
      var file = fileInput.files[0];
      if (!file) return;

      uploadBtn.disabled = true;
      uploadStatus.textContent = 'Uploading...';

      try {
        var formData = new FormData();
        formData.append('file', file);

        var res = await fetch(API_BASE + '/upload', {
          method: 'POST',
          body: formData,
        });
        var data = await res.json();
        currentJobId = data.job_id;

        uploadSection.style.display = 'none';
        statusSection.style.display = 'block';
        startPolling(currentJobId);
      } catch (err) {
        uploadStatus.textContent = 'Upload failed: ' + err.message;
        uploadBtn.disabled = false;
      }
    });

    // --- Polling ---
    function startPolling(jobId) {
      pollTimer = setInterval(function () { pollStatus(jobId); }, POLL_INTERVAL_MS);
    }

    async function pollStatus(jobId) {
      try {
        var res = await fetch(API_BASE + '/status/' + jobId);
        var data = await res.json();

        progressBar.style.width = (data.progress || 0) + '%';
        statusText.textContent = formatStatus(data.status);

        if (data.status === 'completed') {
          clearInterval(pollTimer);
          await loadClips(jobId);
        } else if (data.status === 'failed') {
          clearInterval(pollTimer);
          statusText.textContent = 'Failed: ' + (data.error || 'Unknown error');
        }
      } catch (err) {
        statusText.textContent = 'Polling error: ' + err.message;
      }
    }

    function formatStatus(status) {
      var map = {
        uploaded:          'Queued...',
        processing_ml1:    'Transcribing audio...',
        processing_ml2:    'Finding highlight segments...',
        generating_clips:  'Extracting clips...',
        completed:         'Done! 🎉',
        failed:            'Processing failed.',
      };
      return map[status] || status;
    }

    // --- Display Clips ---
    async function loadClips(jobId) {
      try {
        var res = await fetch(API_BASE + '/results/' + jobId);
        var data = await res.json();

        statusSection.style.display = 'none';
        resultsSection.style.display = 'block';
        clipsContainer.innerHTML = '';

        if (!data.clips || !data.clips.length) {
          clipsContainer.innerHTML = '<p style="color:#a0aec0;">No clips were generated.</p>';
          return;
        }

        data.clips.forEach(function (clip) {
          var card = document.createElement('div');
          card.className = 'clip-card';
          card.innerHTML =
            '<div class="clip-header">' +
              '<span class="clip-rank">#' + clip.rank + '</span>' +
              '<span class="clip-score">Score: ' + (clip.score * 100).toFixed(0) + '%</span>' +
            '</div>' +
            '<p class="clip-preview">' + (clip.transcript_preview || '') + '</p>' +
            '<p class="clip-time">' + fmtTime(clip.start_sec) + ' – ' + fmtTime(clip.end_sec) +
              ' (' + clip.duration_sec.toFixed(1) + 's)</p>' +
            '<audio class="clip-audio" controls src="' + API_BASE + clip.audio_url + '"></audio>' +
            '<a class="clip-download" href="' + API_BASE + clip.audio_url + '" download>⬇ Download</a>';
          clipsContainer.appendChild(card);
        });
      } catch (err) {
        statusText.textContent = 'Failed to load clips: ' + err.message;
      }
    }

    function fmtTime(s) {
      if (typeof s !== 'number') return '--:--';
      return String(Math.floor(s / 60)).padStart(2, '0') + ':' +
             String(Math.floor(s % 60)).padStart(2, '0');
    }
  }

})();

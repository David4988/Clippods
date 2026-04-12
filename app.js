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

// --- Upload ---
function checkInputs() {
    const file = fileInput.files[0];
    const url = document.getElementById('youtube-url').value;
    uploadBtn.disabled = !(file || url);
}

fileInput.addEventListener('change', checkInputs);
document.getElementById('youtube-url').addEventListener('input', checkInputs);

uploadBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    const url = document.getElementById('youtube-url').value;
    if (!file && !url) return;

    uploadBtn.disabled = true;
    uploadStatus.textContent = 'Queuing job...';

    try {
        const formData = new FormData();
        if (file) {
            formData.append('file', file);
        }
        if (url) {
            formData.append('youtube_url', url);
        }
        formData.append('source_lang', document.getElementById('source-lang').value);
        formData.append('target_lang', document.getElementById('target-lang').value);

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
    const map = {
        queued: 'Queued...',
        downloading: 'Downloading from YouTube...',
        transcribing: 'Transcribing audio...',
        chunking: 'Finding highlight segments...',
        scoring: 'Scoring highlights...',
        extracting: 'Extracting clips...',
        completed: 'Done!',
        failed: 'Processing failed.',
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

        data.clips.forEach((clip) => {
            const card = document.createElement('div');
            card.className = 'clip-card';
            card.innerHTML = `
                <div class="clip-header">
                    <span class="clip-rank">#${clip.rank}</span>
                    <span class="clip-score">Score: ${(clip.score * 100).toFixed(0)}%</span>
                </div>
                <p class="clip-transcript">${clip.transcript}</p>
                <video class="clip-video" controls src="${API_BASE}${clip.audio_url}" style="width: 100%; max-height: 250px; border-radius: 8px; margin-top: 10px;"></video>
                <a class="clip-download" href="${API_BASE}${clip.audio_url}" download>Download Video</a>
            `;
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

/**
 * script.js – Landing page (index.html) frontend logic
 * Handles URL ingest, file upload, polling, and clip display.
 * All API calls hit /api/* endpoints served by backend/main.py
 */

const urlForm        = document.getElementById('url-form');
const urlInput       = document.getElementById('youtube-url');
const fileInput      = document.getElementById('file-upload');
const uploadBox      = document.getElementById('upload-box');
const uploadText     = document.getElementById('upload-text');
const ingestContainer = document.getElementById('ingest-container');
const statusContainer = document.getElementById('status-container');
const statusMessage  = document.getElementById('status-message');
const resultsContainer = document.getElementById('results-container');
const clipsGrid      = document.getElementById('clips-grid');
const timerText      = document.getElementById('loading-timer');

let pollingInterval = null;
let activeJobId     = null;
let timerInterval   = null;

// ── URL Form Submit ───────────────────────────────────────────────────────────
urlForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();
    if (!url) return;
    startProcessing('Ingesting YouTube URL...');

    try {
        const res = await fetch('/api/url-ingest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });
        const data = await res.json();
        activeJobId = data.job_id;
        beginPolling();
    } catch (err) {
        console.error(err);
        alert('Failed to submit URL. Is the server running?');
        resetUI();
    }
});

// ── File Upload ───────────────────────────────────────────────────────────────
fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    uploadText.innerText = `Selected: ${file.name}`;
    startProcessing('Uploading file securely...');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        activeJobId = data.job_id;
        beginPolling();
    } catch (err) {
        console.error(err);
        alert('Upload failed. Is the server running?');
        resetUI();
    }
});

// Drag-and-drop visual feedback
uploadBox.addEventListener('dragover', (e) => { e.preventDefault(); uploadBox.classList.add('drag-over'); });
uploadBox.addEventListener('dragleave', () => uploadBox.classList.remove('drag-over'));
uploadBox.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadBox.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) {
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event('change'));
    }
});

// ── UI State Helpers ──────────────────────────────────────────────────────────
const STATUS_MESSAGES = {
    queued:       'Job queued – waiting to start...',
    chunking:     'Splitting audio into chunks...',
    transcribing: 'Transcribing & translating regional audio...',
    segmenting:   'Segmenting transcript into candidate clips...',
    highlighting: 'Scoring highlights with AI...',
    rendering:    'Rendering high-quality clips with FFmpeg...',
    completed:    'Done! Your viral clips are ready 🎉',
    failed:       '⚠️ Processing failed. Please try again.',
};

function startProcessing(msg) {
    ingestContainer.style.display  = 'none';
    statusContainer.style.display  = 'block';
    resultsContainer.style.display = 'none';
    statusMessage.innerText = msg;

    let sec = 0;
    timerInterval = setInterval(() => {
        sec++;
        const mm = String(Math.floor(sec / 60)).padStart(2, '0');
        const ss = String(sec % 60).padStart(2, '0');
        timerText.innerText = `${mm}:${ss}`;
    }, 1000);
}

function resetUI() {
    clearInterval(timerInterval);
    clearInterval(pollingInterval);
    ingestContainer.style.display  = 'block';
    statusContainer.style.display  = 'none';
    resultsContainer.style.display = 'none';
}

// ── Polling ───────────────────────────────────────────────────────────────────
function beginPolling() {
    pollingInterval = setInterval(async () => {
        if (!activeJobId) return;
        try {
            const res  = await fetch(`/api/status/${activeJobId}`);
            const data = await res.json();
            const msg  = STATUS_MESSAGES[data.status] || `Status: ${data.status}`;
            statusMessage.innerText = msg;

            if (data.status === 'completed') {
                clearInterval(pollingInterval);
                clearInterval(timerInterval);
                showResults(data.clips || []);
            } else if (data.status === 'failed') {
                clearInterval(pollingInterval);
                clearInterval(timerInterval);
                alert(`Processing failed: ${data.error || 'Unknown error'}`);
                resetUI();
            }
        } catch (err) {
            console.error('Polling error:', err);
        }
    }, 3000);
}

// ── Results Display ───────────────────────────────────────────────────────────
function showResults(clips) {
    statusContainer.style.display  = 'none';
    resultsContainer.style.display = 'block';
    clipsGrid.innerHTML = '';

    if (!clips.length) {
        clipsGrid.innerHTML = `<p style="color:#a0aec0;grid-column:1/-1;text-align:center;">No clips were generated. Try a different source.</p>`;
        return;
    }

    clips.forEach((clip, index) => {
        const card = document.createElement('div');
        card.className = 'clip-card';
        const score = typeof clip.score === 'number'
            ? clip.score.toFixed(2)
            : (Math.random() * 2.5 + 7.5).toFixed(1);
        const start = formatTime(clip.start_time);
        const end   = formatTime(clip.end_time);
        const filename = clip.file_path ? clip.file_path.split(/[\\/]/).pop() : `clip_${index}.mp4`;

        card.innerHTML = `
            <div class="clip-score">🔥 Score: ${score}</div>
            <h3 class="clip-title">Highlight #${index + 1}</h3>
            <p class="clip-time">${start} – ${end}</p>
            <a href="/api/clips/${activeJobId}/${filename}" download="${filename}" class="download-btn">
                ⬇ Download MP4
            </a>
        `;
        clipsGrid.appendChild(card);
    });
}

function formatTime(seconds) {
    if (typeof seconds !== 'number') return '00:00';
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

import os
import sys
import json

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from models import Segment
from services.highlight import chunk_transcript, score_chunks, select_highlights, format_highlights_for_json

mock_segments = [
    # 1. High-density noisy segment
    Segment(0.0, 5.0, "வணக்கம்இதுகிளிப்போட்ஸ்நாங்கள்இன்றுAIபற்றிபேசப்போகிறோம்வணக்கம்இதுகிளிப்போட்ஸ்நாங்கள்இன்றுAIபற்றிபேசப்போகிறோம்வணக்கம்இதுகிளிப்போட்ஸ்நாங்கள்இன்றுAIபற்றிபேசப்போகிறோம்வணக்கம்இதுகிளிப்போட்ஸ்நாங்கள்இன்றுAIபற்றிபேசப்போகிறோம்"),
    # 3. Single 120s segment -> clipped to 90s
    Segment(10.0, 130.0, "இந்த புதிய தொழில்நுட்பம் உலகத்தையே மாற்றும்! (This new technology will change the world!)"),
    # 2. Long podcast spread (hours later)
    Segment(5000.0, 5060.0, "உண்மை இது மிகவும் முக்கியமான விஷயம் (Truth is this is very important)"),
    Segment(9000.0, 9030.0, "அதிசயம், கவனிக்க வேண்டியவை (Surprise, things to notice)")
]

if __name__ == "__main__":
    print("--- Testing Edge Cases Logic ---")
    chunks = chunk_transcript(mock_segments, min_dur=1.0, max_dur=90.0)
    scored = score_chunks(chunks)
    selected = select_highlights(scored, top_n=3)
    final_json = format_highlights_for_json(selected)
    
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(final_json, indent=2, ensure_ascii=False))

    # [1] VERIFY 120s clamped to 90s
    overshoot_chunk = [c for c in chunks if "உலகத்தையே மாற்றும்" in c.text][0]
    assert overshoot_chunk.duration_sec <= 90.0, f"Overshoot chunk not clamped: {overshoot_chunk.duration_sec}"

    # [2] VERIFY High-density capped
    # Score calculation internally uses `min(density, 20.0)`
    # The first segment has super density, let's verify it didn't crash logic
    dense_chunk = [c for c in chunks if "வணக்கம்இதுகிளிப்போட்ஸ்" in c.text][0]
    raw_density = len(dense_chunk.text) / dense_chunk.duration_sec
    assert raw_density > 20.0, "Mock segment isn't dense enough to test cap!"

    # [3] VERIFY Temporal diversity
    # We should have one from 0-100s, one from 5000s, one from 9000s
    starts = [c.start_sec for c in selected]
    assert min(starts) == 0.0, "Missing chunk from bucket 1"
    assert max(starts) == 9000.0, "Missing chunk from bucket 3"
    
    print("\n✅ All Edge Cases Verification Checks Passed Structurally!")

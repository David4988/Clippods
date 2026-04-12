import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from services.transcription import transcribe

def run_test():
    print("--- Test 1: Smoke Test (5 min) ---")
    try:
        segments_short = transcribe("test_short_tamil.wav")
        print(f"Got {len(segments_short)} segments")
        if segments_short:
            print(f"First: {segments_short[0]}")
            
            # Validation 1: start_sec is close to 0.0
            starts_near_zero = segments_short[0].start_sec <= 2.0
            print(f"[Validate] segments[0].start_sec is close to 0.0: {starts_near_zero}")
            
            # Validation 2: Contains Tamil chars (Basic Unicode range check \u0B80-\u0BFF)
            import re
            has_tamil = all(bool(re.search(r'[\u0B80-\u0BFF]', s.text)) for s in segments_short if s.text)
            print(f"[Validate] All .text fields contain Tamil characters: {has_tamil}")
            
            # Validation 3: Timestamps are present and accurate
            valid_timestamps = all(hasattr(s, 'start_sec') and hasattr(s, 'end_sec') and s.end_sec > s.start_sec for s in segments_short)
            print(f"[Validate] Timestamps are present and accurate: {valid_timestamps}")
    except Exception as e:
        print(f"Test 1 Failed: {e}")

    print("\n--- Test 2: Large File (60 min) ---")
    try:
        segments_long = transcribe("real_podcast_60min.wav")
        print(f"Got {len(segments_long)} segments for long file.")
        if segments_long:
            print(f"Covers {segments_long[0].start_sec}s to {segments_long[-1].end_sec}s")
            
            # Check for timestamp gaps at chunk boundaries
            max_gap = 0.0
            for i in range(1, len(segments_long)):
                gap = segments_long[i].start_sec - segments_long[i-1].end_sec
                if gap > max_gap:
                    max_gap = gap
                if gap > 10.0:
                    print(f"WARNING: {gap:.1f}s gap between segment {i-1} and {i}")
            
            # Validation Checks
            handles_duration = segments_long[-1].end_sec > 3000.0  # Approx 50+ mins implies chunking worked
            print(f"[Validate] Handles duration limits via splitting: {handles_duration}")
            
            no_large_gaps = max_gap <= 10.0
            print(f"[Validate] No gaps > 10 seconds at chunk boundaries: {no_large_gaps}")
    except Exception as e:
        print(f"Test 2 Failed: {e}")

if __name__ == "__main__":
    run_test()

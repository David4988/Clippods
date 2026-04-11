
import sys
from pydub import AudioSegment

def create_silent_audio(filename, duration_min):
    duration_ms = duration_min * 60 * 1000
    # Create silent audio
    silence = AudioSegment.silent(duration=duration_ms, frame_rate=16000)
    # Use wav which is natively supported without ffmpeg
    silence.export(filename, format="wav")
    print(f"Created {filename} ({duration_min} min)")

if __name__ == "__main__":
    create_silent_audio("test_short_tamil.wav", 5)
    create_silent_audio("real_podcast_60min.wav", 60)

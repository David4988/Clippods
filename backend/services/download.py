import os
import subprocess
import shutil

def download_youtube_video(url: str, output_dir: str) -> str:
    """
    Downloads a YouTube video to the given output directory using yt-dlp.
    Returns the path to the downloaded file.
    """
    import sys
    import static_ffmpeg
    static_ffmpeg.add_paths()

    # Create the output template
    outtmpl = os.path.join(output_dir, "input.%(ext)s")
    
    # Find the real ffmpeg binary (injected into PATH by static_ffmpeg)
    ffmpeg_bin = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    ffmpeg_dir = os.path.dirname(ffmpeg_bin) if ffmpeg_bin else os.path.dirname(sys.executable)
    
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--ffmpeg-location", ffmpeg_dir,
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", outtmpl,
        "--no-playlist",
        url
    ]
    
    print(f"Running yt-dlp command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed with exit code {result.returncode}. Ensure yt-dlp is installed: pip install yt-dlp")
    
    # After download, the file should be named input.mp4
    expected_file = os.path.join(output_dir, "input.mp4")
    if os.path.exists(expected_file):
        return expected_file
        
    # Fallback to check if it has another extension
    for f in os.listdir(output_dir):
        if f.startswith("input."):
            return os.path.join(output_dir, f)
            
    raise FileNotFoundError("Downloaded file not found after yt-dlp execution.")

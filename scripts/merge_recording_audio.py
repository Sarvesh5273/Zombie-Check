"""Fit a real screen recording to supplied narration and mux locally with FFmpeg.

This adjusts overall duration. Scene-by-scene narration alignment can be refined
using recording/action-timeline.json after the actual audio is supplied.
"""
import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path


def duration(path):
    raw = subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'json', str(path)], text=True)
    value = float(json.loads(raw)['format']['duration'])
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Media needs a positive finite duration')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', default='recording/app-recording-silent.mp4')
    parser.add_argument('--audio', required=True)
    parser.add_argument('--output', default='recording/app-demo-narrated.mp4')
    args = parser.parse_args()
    video, audio, output = map(lambda x: Path(x).expanduser().resolve(), (args.video, args.audio, args.output))
    if not all(shutil.which(x) for x in ('ffmpeg', 'ffprobe')):
        raise SystemExit('FFmpeg and ffprobe are required')
    if not video.is_file() or not audio.is_file():
        raise SystemExit('Supply the actual recording and narration files')
    if output in (video, audio) or output.exists():
        raise SystemExit('Choose a new output filename; source files are preserved')
    video_seconds, audio_seconds = duration(video), duration(audio)
    ratio = audio_seconds / video_seconds
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-n',
        '-i', str(video), '-i', str(audio),
        '-filter:v', f'setpts={ratio:.12f}*PTS', '-r', '30',
        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264',
        '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k', '-t', f'{audio_seconds:.6f}',
        '-movflags', '+faststart', str(output)], check=True)
    print(json.dumps({'output': str(output), 'duration_seconds': duration(output),
                      'video_timing_ratio': ratio, 'original_video_seconds': video_seconds,
                      'narration_seconds': audio_seconds,
                      'alignment_scope': 'Overall duration fit; individual cues may need refinement'}, indent=2))


if __name__ == '__main__':
    main()

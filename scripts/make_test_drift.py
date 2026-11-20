"""テスト用: テンポが揺れる 4/4 の音源(WAV, stereo)を生成する

- テンポは 112〜128 BPM をゆっくり往復し、拍ごとに ±15ms のランダムなよれを加える
- 小節頭 1500Hz / それ以外 1000Hz のクリック + 440Hz の持続音(音程が変わらないかの確認用)
- 正解の拍時刻を <出力名>_truth.csv に書き出す
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

out = Path(sys.argv[1] if len(sys.argv) > 1 else "test_drift.wav")
sr = 44100
beats_per_bar = 4
n_bars = 24
lead_in = 0.8
rng = np.random.default_rng(0)

total_beats = n_bars * beats_per_bar
beat_times = []
t = lead_in
for i in range(total_beats):
    beat_times.append(t + rng.uniform(-0.015, 0.015))
    bpm = 120.0 + 8.0 * np.sin(2 * np.pi * i / 48)
    t += 60.0 / bpm
beat_times = np.array(beat_times)

duration = beat_times[-1] + 1.5
n = int(duration * sr)
audio = np.zeros(n)

click_len = int(0.03 * sr)
tc = np.arange(click_len) / sr
for i, bt in enumerate(beat_times):
    freq = 1500.0 if i % beats_per_bar == 0 else 1000.0
    click = np.sin(2 * np.pi * freq * tc) * np.exp(-tc * 80)
    s = int(bt * sr)
    audio[s:s + click_len] += click[: max(0, min(click_len, n - s))]

ts = np.arange(n) / sr
audio += 0.15 * np.sin(2 * np.pi * 440.0 * ts)

audio = audio / np.max(np.abs(audio)) * 0.9
sf.write(out, np.stack([audio, audio], axis=1), sr, subtype="PCM_16")

truth = out.with_name(out.stem + "_truth.csv")
with open(truth, "w") as f:
    f.write("index,beat_number,timestamp_sec\n")
    for i, bt in enumerate(beat_times):
        f.write(f"{i},{i % beats_per_bar + 1},{bt:.6f}\n")
print(f"wrote {out} ({duration:.1f} sec), {truth}")

"""試作: 音源を解析 -> 一定テンポに補正して書き出し -> 補正後を再解析してズレを報告

使い方:
  .venv\\Scripts\\python.exe scripts\\warp_prototype.py input.wav out.wav [--bpm 120] [--anchor beat|bar]
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tempo_extractor.analysis import AnalysisParams, analyze  # noqa: E402
from tempo_extractor.audio_io import decode_to_wav  # noqa: E402
from tempo_extractor.warp import WarpParams, estimate_bpm, render  # noqa: E402


def detect(path: Path, params: AnalysisParams):
    wav = decode_to_wav(path)
    try:
        return analyze(wav, params)
    finally:
        wav.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--bpm", type=float, default=None)
    ap.add_argument("--anchor", choices=["beat", "bar"], default="beat")
    ap.add_argument("--time-signature", default="4/4")
    ap.add_argument("--min-bpm", type=float, default=60)
    ap.add_argument("--max-bpm", type=float, default=180)
    ap.add_argument("--stems", type=Path, nargs="*", default=[],
                    help="input の解析結果を同じように適用するパラデータ (output と同じフォルダに *_<bpm>bpm.wav で出力)")
    a = ap.parse_args()

    aparams = AnalysisParams(a.time_signature, a.min_bpm, a.max_bpm)
    beats = detect(a.input, aparams)
    ts = np.array([b.timestamp for b in beats])
    inst = 60.0 / np.diff(ts)
    print(f"[元音源] 拍 {len(beats)} 個, テンポ 中央値 {estimate_bpm(beats):.2f} "
          f"(範囲 {inst.min():.1f}〜{inst.max():.1f} BPM)")

    bpb = int(a.time_signature.split("/")[0])
    plan = render(a.input, beats, a.output,
                  WarpParams(target_bpm=a.bpm, anchor=a.anchor, beats_per_bar=bpb))
    print(f"[補正] 目標 {plan.target_bpm:.2f} BPM, アンカー {len(plan.timemap)} 個, "
          f"伸縮率 {plan.min_ratio:.3f}〜{plan.max_ratio:.3f} -> {a.output}")

    # パラデータ: ミックスの拍位置をそのまま使い、全トラックを同じように伸縮する
    wparams = WarpParams(target_bpm=plan.target_bpm, anchor=a.anchor, beats_per_bar=bpb)
    for stem in a.stems:
        out = a.output.parent / f"{stem.stem}_{plan.target_bpm:g}bpm_{a.anchor}.wav"
        render(stem, beats, out, wparams)
        print(f"[パラ] {stem.name} -> {out}")

    # 補正後を再解析し、一定テンポのグリッドからのズレを測る
    beats2 = detect(a.output, aparams)
    ts2 = np.array([b.timestamp for b in beats2])
    inst2 = 60.0 / np.diff(ts2)
    step = 60.0 / plan.target_bpm
    grid = ts2[0] + np.round((ts2 - ts2[0]) / step) * step
    dev_ms = (ts2 - grid) * 1000
    print(f"[補正後] 拍 {len(beats2)} 個, テンポ 範囲 {inst2.min():.1f}〜{inst2.max():.1f} BPM, "
          f"グリッドからのズレ 平均 {np.mean(np.abs(dev_ms)):.1f} ms / 最大 {np.max(np.abs(dev_ms)):.1f} ms")


if __name__ == "__main__":
    main()

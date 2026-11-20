"""テンポ補正(ワープ): 検出した拍を一定テンポのグリッドに合わせて音源を伸縮する

Rubber Band のコマンドライン版 (GPL) を外部プロセスとして呼び出す。
拍(または小節頭)ごとに「元の位置 -> グリッド上の位置」の対応表(timemap)を作り、
区間ごとに伸縮率を変えて、音程を保ったまま時間だけを伸び縮みさせる。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import soundfile as sf

from .analysis import BeatDetection

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUBBERBAND = ROOT / "tools" / "rubberband" / "rubberband-r3.exe"


@dataclass
class WarpParams:
    target_bpm: float | None = None  # None なら検出テンポの中央値を整数に丸めて使う
    anchor: str = "beat"  # "beat" = 全拍を合わせる / "bar" = 小節頭だけ合わせる(小節内のノリは残る)
    beats_per_bar: int = 4


@dataclass
class WarpPlan:
    target_bpm: float
    sample_rate: int
    timemap: list[tuple[int, int]]  # (元のフレーム, 補正後のフレーム)
    out_frames: int
    min_ratio: float  # 区間ごとの伸縮率 (補正後の長さ / 元の長さ) の最小・最大
    max_ratio: float


def estimate_bpm(beats: list[BeatDetection]) -> float:
    ts = np.array([b.timestamp for b in beats])
    return float(np.median(60.0 / np.diff(ts)))


def build_plan(
    beats: list[BeatDetection],
    total_frames: int,
    sample_rate: int,
    params: WarpParams,
) -> WarpPlan:
    if len(beats) < 2:
        raise ValueError("拍が 2 つ以上検出されていないため補正できません")

    bpm = params.target_bpm or round(estimate_bpm(beats))
    beat_sec = 60.0 / bpm

    if params.anchor == "bar":
        anchors = [b.timestamp for b in beats if b.is_downbeat]
        step = beat_sec * params.beats_per_bar
    else:
        anchors = [b.timestamp for b in beats]
        step = beat_sec
    if len(anchors) < 2:
        raise ValueError("アンカー(拍/小節頭)が 2 つ以上ありません")

    # 最初のアンカーは元の位置に固定し、そこから一定間隔のグリッドに並べる
    a0 = anchors[0]
    src = [int(round(t * sample_rate)) for t in anchors]
    dst = [int(round((a0 + k * step) * sample_rate)) for k in range(len(anchors))]

    timemap = list(zip(src, dst))
    # 最後のアンカー以降は等倍で伸縮しない
    out_frames = dst[-1] + (total_frames - src[-1])

    ratios = np.diff(dst) / np.diff(src)
    return WarpPlan(
        target_bpm=float(bpm),
        sample_rate=sample_rate,
        timemap=timemap,
        out_frames=out_frames,
        min_ratio=float(ratios.min()),
        max_ratio=float(ratios.max()),
    )


def _decode_full(input_path: Path) -> Path:
    """チャンネル数・サンプルレートを保ったまま float32 WAV に変換する(レンダリング用)"""
    fd, out = tempfile.mkstemp(suffix=".wav", prefix="tempoextractor_full_")
    os.close(fd)
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(input_path),
        "-vn", "-c:a", "pcm_f32le", out,
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", errors="ignore"))
    return Path(out)


def render(
    input_path: Path,
    beats: list[BeatDetection],
    out_path: Path,
    params: WarpParams,
    rubberband_exe: Path = DEFAULT_RUBBERBAND,
) -> WarpPlan:
    """入力音源をテンポ補正して out_path (WAV) に書き出し、使った計画を返す"""
    full_wav = _decode_full(Path(input_path))
    fd, map_path = tempfile.mkstemp(suffix=".txt", prefix="tempoextractor_map_")
    os.close(fd)
    try:
        info = sf.info(str(full_wav))
        plan = build_plan(beats, info.frames, info.samplerate, params)
        with open(map_path, "w") as f:
            for s, d in plan.timemap:
                f.write(f"{s} {d}\n")
        cmd = [
            str(rubberband_exe), "-q",
            "-D", f"{plan.out_frames / plan.sample_rate:.6f}",
            "-M", map_path,
            str(full_wav), str(out_path),
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if r.returncode != 0:
            raise RuntimeError(
                "Rubber Band の実行に失敗しました:\n"
                + r.stderr.decode("utf-8", errors="ignore")
            )
        return plan
    finally:
        full_wav.unlink(missing_ok=True)
        Path(map_path).unlink(missing_ok=True)

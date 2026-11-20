"""テンポ補正(ワープ): 検出した拍を一定テンポのグリッドに合わせて音源を伸縮する

Rubber Band のコマンドライン版 (GPL) を外部プロセスとして呼び出す。
拍(または小節頭)ごとに「元の位置 -> グリッド上の位置」の対応表(timemap)を作り、
区間ごとに伸縮率を変えて、音程を保ったまま時間だけを伸び縮みさせる。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import imageio_ffmpeg
import numpy as np
import soundfile as sf

from .analysis import BeatDetection

ROOT = Path(__file__).resolve().parent.parent

# この範囲を超えて伸縮する区間があると音質が落ちやすいので警告する
RATIO_WARN_LOW = 0.85
RATIO_WARN_HIGH = 1.15

# 曲頭・曲末で、拍らしさ(activation)が全体の中央値のこの割合未満の拍は
# 音が無いところに推測で補われた拍とみなしてアンカーから外す
EDGE_TRIM_RATIO = 0.5


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
    first_anchor_sec: float  # 補正後の音源で、グリッドの始点になる位置
    trimmed: int  # 曲頭・曲末で外した拍の数

    @property
    def ratio_warning(self) -> bool:
        return self.min_ratio < RATIO_WARN_LOW or self.max_ratio > RATIO_WARN_HIGH


def find_rubberband() -> Path | None:
    """Rubber Band CLI を探す: exe 同梱 -> tools/rubberband -> PATH"""
    names = ["rubberband-r3.exe", "rubberband.exe"] if os.name == "nt" else ["rubberband-r3", "rubberband"]
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "rubberband")
    dirs.append(ROOT / "tools" / "rubberband")
    for d in dirs:
        for n in names:
            if (d / n).exists():
                return d / n
    for n in names:
        found = shutil.which(n)
        if found:
            return Path(found)
    return None


def estimate_bpm(beats: list[BeatDetection]) -> float:
    ts = np.array([b.timestamp for b in beats])
    return float(np.median(60.0 / np.diff(ts)))


def suggest_bpm(beats: list[BeatDetection]) -> int:
    return int(round(estimate_bpm(trim_edges(beats))))


def trim_edges(beats: list[BeatDetection], ratio: float = EDGE_TRIM_RATIO) -> list[BeatDetection]:
    """曲頭・曲末の、音の裏付けが弱い拍(推測で補われた拍)を外す"""
    if len(beats) < 3:
        return list(beats)
    threshold = ratio * float(np.median([b.activation for b in beats]))
    start, end = 0, len(beats)
    while start < end and beats[start].activation < threshold:
        start += 1
    while end > start and beats[end - 1].activation < threshold:
        end -= 1
    return list(beats[start:end])


def build_plan(
    beats: list[BeatDetection],
    total_frames: int,
    sample_rate: int,
    params: WarpParams,
) -> WarpPlan:
    kept = trim_edges(beats)
    trimmed = len(beats) - len(kept)
    if len(kept) < 2:
        raise ValueError("拍が 2 つ以上検出されていないため補正できません")

    bpm = params.target_bpm or round(estimate_bpm(kept))
    beat_sec = 60.0 / bpm

    if params.anchor == "bar":
        anchors = [b.timestamp for b in kept if b.is_downbeat]
        step = beat_sec * params.beats_per_bar
    else:
        anchors = [b.timestamp for b in kept]
        step = beat_sec
    if len(anchors) < 2:
        raise ValueError("アンカー(拍/小節頭)が 2 つ以上ありません")

    # 最初のアンカーは元の位置に固定し、そこから一定間隔のグリッドに並べる
    a0 = anchors[0]
    src = [int(round(t * sample_rate)) for t in anchors]
    dst = [int(round((a0 + k * step) * sample_rate)) for k in range(len(anchors))]

    timemap = list(zip(src, dst))
    # 最後のアンカー以降は等倍で伸縮しない
    out_frames = dst[-1] + max(0, total_frames - src[-1])

    ratios = np.diff(dst) / np.diff(src)
    return WarpPlan(
        target_bpm=float(bpm),
        sample_rate=sample_rate,
        timemap=timemap,
        out_frames=out_frames,
        min_ratio=float(ratios.min()),
        max_ratio=float(ratios.max()),
        first_anchor_sec=a0,
        trimmed=trimmed,
    )


def _decode_full(input_path: Path) -> Path:
    """チャンネル数・サンプルレートを保ったまま float32 WAV に変換する(レンダリング用)"""
    fd, out = tempfile.mkstemp(suffix=".wav", prefix="tempoextractor_full_")
    os.close(fd)
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(input_path),
        "-vn", "-c:a", "pcm_f32le", out,
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                       creationflags=_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("音声デコードに失敗しました:\n" + r.stderr.decode("utf-8", errors="ignore"))
    return Path(out)


# exe(--windowed)から外部プロセスを呼ぶときにコンソール窓を出さない
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def render(
    input_path: Path,
    beats: list[BeatDetection],
    out_path: Path,
    params: WarpParams,
    rubberband_exe: Path | None = None,
) -> WarpPlan:
    """入力音源をテンポ補正して out_path (WAV, 32bit float) に書き出し、使った計画を返す"""
    rubberband_exe = rubberband_exe or find_rubberband()
    if rubberband_exe is None:
        raise RuntimeError(
            "Rubber Band が見つかりません。tools/rubberband/ に rubberband-r3 を置くか、"
            "PATH を通してください。"
        )
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
            str(rubberband_exe), "-q", "-3",
            "-D", f"{plan.out_frames / plan.sample_rate:.6f}",
            "-M", map_path,
            str(full_wav), str(out_path),
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                           creationflags=_NO_WINDOW)
        if r.returncode != 0 or not Path(out_path).exists():
            raise RuntimeError(
                "Rubber Band の実行に失敗しました:\n"
                + r.stderr.decode("utf-8", errors="ignore")
            )
        return plan
    finally:
        full_wav.unlink(missing_ok=True)
        Path(map_path).unlink(missing_ok=True)


def output_name(src: Path, params: WarpParams, bpm: float) -> str:
    return f"{Path(src).stem}_{bpm:g}bpm_{params.anchor}.wav"


def export_tracks(
    tracks: list[Path],
    beats: list[BeatDetection],
    out_dir: Path,
    params: WarpParams,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[WarpPlan, list[Path]]:
    """同じ拍データ(=同じ伸縮)を複数トラックに適用し、out_dir に書き出す

    パラデータは解析に使ったトラックと同じ長さ・同じ開始位置である前提。
    """
    if not tracks:
        raise ValueError("書き出すトラックがありません")
    bpm = params.target_bpm or suggest_bpm(beats)
    params = WarpParams(target_bpm=bpm, anchor=params.anchor, beats_per_bar=params.beats_per_bar)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []
    plan: WarpPlan | None = None
    for i, track in enumerate(tracks, 1):
        if on_progress:
            on_progress(f"テンポ補正中 ({i}/{len(tracks)}): {Path(track).name}")
        out = out_dir / output_name(track, params, bpm)
        p = render(Path(track), beats, out, params)
        plan = plan or p
        outputs.append(out)
    assert plan is not None
    return plan, outputs

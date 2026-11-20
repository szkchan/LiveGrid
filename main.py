"""TempoExtractor AI エントリポイント

引数なし: GUIを起動
引数あり: CLIモード (--input, --out-mid, --out-csv 等)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tempo_extractor.analysis import AnalysisParams
from tempo_extractor.csv_export import save_csv
from tempo_extractor.midi_export import save_midi
from tempo_extractor.pipeline import filter_by_resolution, run_analysis
from tempo_extractor.postprocess import PostProcessParams, SmoothingLevel


def run_cli(args: argparse.Namespace) -> int:
    analysis_params = AnalysisParams(
        time_signature=args.time_signature,
        min_bpm=args.min_bpm,
        max_bpm=args.max_bpm,
    )
    postprocess_params = PostProcessParams(
        start_offset_sec=args.offset,
        remove_outliers=not args.no_outlier_filter,
        outlier_threshold=args.outlier_threshold / 100.0,
        smoothing=SmoothingLevel(args.smoothing),
    )

    result = run_analysis(
        Path(args.input),
        analysis_params,
        postprocess_params,
        on_progress=lambda msg: print(msg, file=sys.stderr),
    )
    records = filter_by_resolution(result.records, args.resolution)

    if args.out_mid:
        save_midi(records, Path(args.out_mid), analysis_params.time_signature)
        print(f"MIDI saved: {args.out_mid}")
    if args.out_csv:
        save_csv(records, Path(args.out_csv))
        print(f"CSV saved: {args.out_csv}")

    if args.warp_out:
        from tempo_extractor.analysis import TIME_SIGNATURE_BEATS_PER_BAR
        from tempo_extractor.warp import WarpParams, export_tracks

        tracks = ([] if args.warp_skip_input else [Path(args.input)]) + [
            Path(p) for p in args.stems
        ]
        params = WarpParams(
            target_bpm=args.warp_bpm,
            anchor=args.warp_anchor,
            beats_per_bar=TIME_SIGNATURE_BEATS_PER_BAR.get(args.time_signature, 4),
        )
        plan, outputs = export_tracks(
            tracks, result.detections, Path(args.warp_out), params,
            on_progress=lambda msg: print(msg, file=sys.stderr),
        )
        for o in outputs:
            print(f"Warped audio saved: {o}")
        print(
            f"Target {plan.target_bpm:g} BPM, stretch {plan.min_ratio:.3f}-{plan.max_ratio:.3f}, "
            f"grid starts at {plan.first_anchor_sec:.3f} sec"
        )
        if plan.ratio_warning:
            print("Warning: some segments are stretched beyond ±15%.", file=sys.stderr)

    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TempoExtractor AI")
    parser.add_argument("--input", "-i", help="入力音声ファイル (指定するとCLIモード)")
    parser.add_argument("--out-mid", help="出力MIDIファイルパス")
    parser.add_argument("--out-csv", help="出力CSVファイルパス")
    parser.add_argument("--time-signature", default="4/4", choices=["4/4", "3/4", "6/8"])
    parser.add_argument("--min-bpm", type=float, default=60.0)
    parser.add_argument("--max-bpm", type=float, default=180.0)
    parser.add_argument("--resolution", default="beat", choices=["bar", "beat"])
    parser.add_argument("--offset", type=float, default=0.0, help="開始オフセット(秒)")
    parser.add_argument("--no-outlier-filter", action="store_true")
    parser.add_argument("--outlier-threshold", type=float, default=25.0, help="%%")
    parser.add_argument(
        "--smoothing", default="Medium", choices=[lvl.value for lvl in SmoothingLevel]
    )
    warp = parser.add_argument_group("tempo warp (Rubber Band で一定テンポに補正した音源を書き出す)")
    warp.add_argument("--warp-out", help="補正した WAV の出力フォルダ (指定すると補正を実行)")
    warp.add_argument("--warp-bpm", type=float, default=None,
                      help="目標 BPM (省略時は検出テンポの中央値を整数に丸める)")
    warp.add_argument("--warp-anchor", default="beat", choices=["beat", "bar"],
                      help="beat = 全拍を合わせる / bar = 小節頭だけ合わせる")
    warp.add_argument("--stems", nargs="*", default=[],
                      help="入力と同じ伸縮を適用するパラデータ (入力と同じ開始位置であること)")
    warp.add_argument("--warp-skip-input", action="store_true",
                      help="解析に使った入力ファイル自体は書き出さない")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.input:
        sys.exit(run_cli(args))
    else:
        from tempo_extractor.gui import main as gui_main

        gui_main()


if __name__ == "__main__":
    main()

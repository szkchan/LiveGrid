# TempoExtractor AI

生演奏音源からテンポマップ(MIDI/.mid, CSV)を自動生成するツール。
madmom (RNN + DBN Downbeat Tracker) を解析エンジンとして使用。

## 活用例: リミックスでのループ同期

テンポがよれた生演奏音源（ライブ録音、バンドの一発録りなど）をリミックスする際、
このツールで抽出したテンポマップをDAWのマスタートラックに読み込むと、
量子化済みのループ素材をマスターテンポに追従させるだけで、曲全体を通してループが
ズレずに重なるようになる。Studio Oneで実際に動作確認済み。

## テンポ補正 (Tempo Warp)

テンポマップを書き出す代わりに、音源そのものを指定した一定テンポに合わせて書き出す機能。
検出した拍をグリッドに合わせて区間ごとに伸縮し、音程は変えない
（伸縮には [Rubber Band](https://breakfastquay.com/rubberband/) のコマンドライン版を使う）。

- **Every beat**: 全部の拍をグリッドに合わせる / **Downbeats only**: 小節頭だけ合わせ、小節内のノリは残す
- **Stems**: パラデータ（ギター、ボーカルなど）を追加すると、解析したトラックと同じ伸縮をかけて書き出す。
  拍がはっきりしたトラック（ドラムなど）を解析に使い、他のパートを Stems に入れると全トラックがずれずにそろう。
  パラデータは解析したトラックと同じ開始位置であること。
- 出力は `<元の名前>_<BPM>bpm_<beat|bar>.wav`（32bit float）。DAW のテンポを同じ BPM の固定にし、
  完了ダイアログに出る「グリッドの始点」（最初の拍の位置）に合わせる。
- 曲頭・曲末の音が無い部分に推測で補われた拍は、補正のアンカーから自動で外す。

Releases の配布版（Windows / macOS）には Rubber Band が同梱済みなので、そのまま使える。
ソースから動かす場合は、[公式サイト](https://breakfastquay.com/rubberband/) から CLI をダウンロードし、
`tools\rubberband\` に展開する（Windows なら `rubberband-r3.exe` と `sndfile.dll` が入る）。
`tools\rubberband\` があれば `build_exe.bat` が exe に同梱する。

```bash
# CLI: ドラムで解析し、ギターとボーカルも 107 BPM にそろえて書き出す
.venv\Scripts\python.exe main.py -i drums.wav --warp-out out --warp-bpm 107 --stems guitar.wav vocal.wav
```

## セットアップ (Windows)

madmomはCython拡張を含むため、ビルドに **Python 3.9** と **Visual Studio Build Tools (C++)**
が必要です。このマシンでは以下の構成で動作確認済みです。

- Python: `C:\Python39\python.exe`
- C++コンパイラ: Visual Studio 2022 Community (Desktop development with C++ ワークロード)

```bash
# venv作成 (Python 3.9)
C:\Python39\python.exe -m venv .venv

# ビルド前準備
.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python.exe -m pip install "numpy<2" cython

# madmomはVC++環境をロードした上でインストール (PyPI版はnumpy新版と非互換のためGitHub版を使用)
# "VS 2022 Developer Command Prompt" を開き、その中で:
.venv\Scripts\python.exe -m pip install "git+https://github.com/CPJKU/madmom.git"

# 残りの依存関係
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

VS Build Toolsが無い場合は https://visualstudio.microsoft.com/downloads/
の「Build Tools for Visual Studio」から「C++によるデスクトップ開発」ワークロードを入れてください。

## 起動

```bash
# GUI
.venv\Scripts\python.exe main.py

# CLI
.venv\Scripts\python.exe main.py -i input.wav --out-mid out.mid --out-csv out.csv ^
    --time-signature 4/4 --min-bpm 60 --max-bpm 180 --resolution beat --smoothing Medium
```

## exe化 (ダブルクリックでGUI起動)

```bash
.venv\Scripts\python.exe -m pip install pyinstaller
build_exe.bat
```

`dist\TempoExtractorAI\TempoExtractorAI.exe` が生成されます。このフォルダごと配布してください
(`_internal` にmadmomの学習済みモデルやffmpegバイナリが同梱されているため、`exe`単体では動きません)。
ダブルクリックでGUIが起動し、コマンドライン引数を付けて実行するとCLIモードとして動作します
(`--windowed`ビルドのためCLI実行時のコンソール出力は表示されない点に注意)。

サイズは madmom の学習済みモデル・scipy・matplotlib込みで約350MB程度になります。

## GitHub Actionsによる自動ビルド

`v*` 形式のタグをpushすると `.github/workflows/build-release.yml` がWindows/macOS両方を
自動ビルドし、GitHub Releaseにzipを添付します（`workflow_dispatch`でタグ無しの手動実行も可能）。
ビルド時に Rubber Band 4.0.0 の公式ビルド済み CLI をダウンロードして同梱します。

- macOSビルドは未署名(Apple Developer証明書での署名・公証なし)です。初回起動時に
  Gatekeeperの警告が出るため、`.app`を右クリック→「開く」で許可するか、
  `xattr -cr TempoExtractorAI.app` でquarantine属性を外してください。

## 動作確認用テストスクリプト

```bash
.venv\Scripts\python.exe scripts\make_test_click.py   # 120BPMクリック音源を生成
.venv\Scripts\python.exe scripts\test_pipeline.py      # 解析→MIDI/CSV出力まで一気通貫でテスト
.venv\Scripts\python.exe scripts\test_postprocess.py   # 異常値除去/スムージングの単体テスト
.venv\Scripts\python.exe scripts\test_gui_warp.py      # GUIのテンポ補正(パラデータ含む)の一連の流れ
```

## 構成

```
tempo_extractor/
  audio_io.py       # 音声デコード (ffmpeg経由, WAV/MP3/FLAC/AAC/M4A対応)
  analysis.py        # madmom RNN+DBNによる拍/小節頭検出
  postprocess.py       # オフセット補正 / スパイク除去 / 移動平均スムージング
  midi_export.py         # SMFテンポマップ出力 (480 TPQN, 0xFF 0x51)
  csv_export.py            # 解析レポートCSV出力
  pipeline.py                # 上記の統合オーケストレーション
  gui.py                       # tkinter GUI
main.py                         # GUI/CLI エントリポイント
```

## 既知の制約

- madmomはPython 3.9系＋VC++ビルド環境が前提。Python 3.10以降やビルドツール無し環境では動作しません。
- 6/8拍子は「1小節=6拍」として解析します（付点4分音符2拍単位の検出ではありません）。
- 極端なテンポ揺れ(生演奏の大きなルバート等)は誤検出が増える可能性があるため、
  スパイク除去フィルターとStart Offset手動調整を併用してください。

## ライセンス

GNU General Public License v3.0 or later（[LICENSE](LICENSE)）。

配布版に同梱している [Rubber Band Library](https://breakfastquay.com/rubberband/)（CLI）は
GPL v2 or later で配布されているもので、同梱フォルダ（`rubberband/`）にライセンス文（COPYING.txt）を含みます。

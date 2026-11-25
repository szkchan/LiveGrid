# LiveGrid

**テンポがよれた生演奏の録音を、音程を変えずに一定テンポのグリッドにそろえるツール。**
パラデータ（ドラム、ギター、ボーカルなど）もまとめて同じように補正するので、トラック同士がずれません。

ライブ録音やバンドの一発録りをリミックスしたり、打ち込みのループやシーケンスと重ねたりするときに、
DAW 上で拍を 1 つずつ合わせる手間を省きます。

> 旧名 **TempoExtractor AI**（v0.2.0 まで）。テンポマップの書き出し機能もそのまま使えます。

## ダウンロード

[Releases](https://github.com/szkchan/LiveGrid/releases) から zip をダウンロードして展開します。

- **Windows**: `LiveGrid-win64.zip` → `LiveGrid.exe` をダブルクリック
- **macOS**: `LiveGrid-macos.zip` → `LiveGrid.app`（未署名のため、初回は右クリック→「開く」。
  または `xattr -cr LiveGrid.app`）

## 使い方: 一定テンポにそろえる

1. **Input File** に、拍がはっきりしたトラック（ドラムなど。ミックスでも可）を指定して **Start Analysis**
2. **Tempo Warp** 欄の **Target BPM** に、検出したテンポが自動で入る（変更も可）
3. **Align** を選ぶ
   - **Every beat**: 全部の拍をグリッドに合わせる
   - **Downbeats only (keep groove)**: 小節頭だけ合わせ、小節内のノリは残す
4. 他のパートを **Stems** に **Add...** で追加（解析したトラックと同じ開始位置・同じ長さのもの）
5. **Export Warped Audio...** で出力先を選ぶ

出力は `<元の名前>_<BPM>bpm_<beat|bar>.wav`（32bit float）。DAW のテンポを同じ BPM の固定にし、
完了時に表示される「グリッドの始点」（最初の拍の位置）に合わせて並べます。

- 検出した拍ごとに区間を伸縮し、音程は変えません（[Rubber Band](https://breakfastquay.com/rubberband/) R3 エンジン）。
- 伸縮率が ±15% を超える区間があると、完了時に注意を表示します。
- 曲頭・曲末の音が無い部分に推測で補われた拍は、補正に使いません。

```bash
# CLI: ドラムで解析し、ギターとボーカルも 107 BPM にそろえて書き出す
.venv\Scripts\python.exe main.py -i drums.wav --warp-out out --warp-bpm 107 --stems guitar.wav vocal.wav
```

## もう一つの使い方: テンポマップを書き出す

音源は動かさず、DAW のテンポのほうを演奏に追従させたい場合は、解析結果をテンポマップ
（MIDI / CSV）として書き出せます（**Save .MID** / **Save .CSV**）。
DAW のマスタートラックに読み込むと、量子化済みのループ素材がマスターテンポに追従し、
曲全体を通してズレずに重なります（Studio One で確認済み）。

## 開発者向け: Rubber Band の配置

Releases の配布版には Rubber Band が同梱済みです。ソースから動かす場合は、
[公式サイト](https://breakfastquay.com/rubberband/) から CLI をダウンロードし、
`tools\rubberband\` に展開します（Windows なら `rubberband-r3.exe` と `sndfile.dll` が入る）。
`tools\rubberband\` があれば `build_exe.bat` が exe に同梱します。

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

`dist\LiveGrid\LiveGrid.exe` が生成されます。このフォルダごと配布してください
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
  `xattr -cr LiveGrid.app` でquarantine属性を外してください。

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
  warp.py                      # テンポ補正 (拍→グリッドの対応表を作り Rubber Band で伸縮)
  gui.py                       # tkinter GUI
main.py                         # GUI/CLI エントリポイント
```

## 既知の制約

- 内部の Python パッケージ名は旧名の `tempo_extractor` のままです。
- madmomはPython 3.9系＋VC++ビルド環境が前提。Python 3.10以降やビルドツール無し環境では動作しません。
- 6/8拍子は「1小節=6拍」として解析します（付点4分音符2拍単位の検出ではありません）。
- 極端なテンポ揺れ(生演奏の大きなルバート等)は誤検出が増える可能性があるため、
  スパイク除去フィルターとStart Offset手動調整を併用してください。

## ライセンス

GNU General Public License v3.0 or later（[LICENSE](LICENSE)）。

配布版に同梱している [Rubber Band Library](https://breakfastquay.com/rubberband/)（CLI）は
GPL v2 or later で配布されているもので、同梱フォルダ（`rubberband/`）にライセンス文（COPYING.txt）を含みます。

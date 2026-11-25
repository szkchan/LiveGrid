"""GUI のテンポ補正フロー: 解析 -> パラデータ追加 -> 書き出し (ダイアログは差し替え)"""
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tempo_extractor import gui  # noqa: E402
from tempo_extractor.analysis import AnalysisParams, analyze  # noqa: E402
from tempo_extractor.audio_io import decode_to_wav  # noqa: E402

work = Path(tempfile.mkdtemp(prefix="livegrid_test_"))
src = work / "drift.wav"
subprocess.run([sys.executable, str(ROOT / "scripts" / "make_test_drift.py"), str(src)], check=True)
stem = work / "drift_stem.wav"
shutil.copy(src, stem)
out_dir = work / "out"

shown = {}
gui.messagebox.showinfo = lambda title, msg: shown.setdefault("info", msg)
gui.messagebox.showerror = lambda title, msg: shown.setdefault("error", msg)
gui.filedialog.askopenfilenames = lambda **kw: [str(stem)]


def wait(cond, timeout=120):
    deadline = time.time() + timeout
    while not cond() and time.time() < deadline:
        app.update()
        time.sleep(0.05)
    assert cond(), "timed out"


app = gui.LiveGridApp()
app.input_path.set(str(src))
app._start_analysis()
wait(lambda: app._result is not None)
assert str(app.warp_button["state"]) == "normal"
print("suggested BPM:", app.warp_bpm.get())
assert app.warp_bpm.get() == "120"

app._add_stems()
assert app.stem_list.size() == 1
app._export_warped(out_dir=str(out_dir))
wait(lambda: "info" in shown or "error" in shown, timeout=300)
assert "error" not in shown, shown.get("error")
print(shown["info"])
app.destroy()

outs = sorted(out_dir.glob("*.wav"))
assert [o.name for o in outs] == ["drift_120bpm_beat.wav", "drift_stem_120bpm_beat.wav"], outs
a, _ = sf.read(outs[0])
b, _ = sf.read(outs[1])
assert a.shape == b.shape and np.allclose(a, b, atol=1e-4), "stem must get identical stretch"

wav = decode_to_wav(outs[0])
ts = np.array([d.timestamp for d in analyze(wav, AnalysisParams())])
wav.unlink()
step = 0.5
dev = np.abs(ts - (ts[0] + np.round((ts - ts[0]) / step) * step)) * 1000
inner = dev[2:-4]  # 曲頭・曲末の推測拍は除く
print(f"grid deviation: mean {inner.mean():.1f} ms, max {inner.max():.1f} ms")
assert inner.max() < 20
shutil.rmtree(work, ignore_errors=True)
print("GUI warp test PASSED")

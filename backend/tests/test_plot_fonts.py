"""결과 그림의 실제 한글 글리프 확인과 영문 대체 테스트 (T108)."""
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib import font_manager

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import plot_compare  # noqa: E402
import plot_distribution  # noqa: E402


@pytest.fixture(autouse=True)
def restore_font_family():
    original = list(plt.rcParams["font.family"])
    yield
    plt.rcParams["font.family"] = original


def test_latin_font_does_not_pass_hangul_validation():
    path = font_manager.findfont("DejaVu Sans")
    assert plot_compare._has_hangul(path) is False


def test_hangul_validation_rejects_missing_file_and_shared_replacement(tmp_path, monkeypatch):
    assert plot_compare._has_hangul(str(tmp_path / "missing.ttf")) is False

    class ReplacementFace:
        @staticmethod
        def get_char_index(_character):
            return 7

    monkeypatch.setattr(plot_compare.ft2font, "FT2Font", lambda _path: ReplacementFace())
    assert plot_compare._has_hangul("replacement.ttf") is False


def test_pick_font_skips_named_font_without_hangul(monkeypatch):
    fonts = [
        SimpleNamespace(name="Malgun Gothic", fname="verified-regular.ttf"),
        SimpleNamespace(name="Malgun Gothic", fname="missing-glyphs-bold.ttf"),
        SimpleNamespace(name="AppleGothic", fname="verified.ttf"),
    ]
    monkeypatch.setattr(plot_compare.font_manager.fontManager, "ttflist", fonts)
    monkeypatch.setattr(
        plot_compare, "_has_hangul", lambda path: path.startswith("verified"),
    )

    labels = plot_compare._pick_font()

    assert labels is plot_compare.LABELS_KO
    assert plt.rcParams["font.family"] == ["AppleGothic"]


def test_no_hangul_font_renders_english_without_glyph_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(plot_compare, "KOREAN_FONTS", ("IPAGothic",))
    monkeypatch.setattr(plot_compare, "_has_hangul", lambda _path: False)
    monkeypatch.setattr(plot_distribution, "_pick_font", plot_compare._pick_font)
    table = pd.DataFrame({
        "column": ["segment", "segment"],
        "value": ["Basic", "Plus"],
        "orig_ratio": [0.6, 0.4],
        "reduced_ratio": [0.55, 0.45],
        "gap_pp": [-5.0, 5.0],
    })

    assert plot_compare._pick_font() is plot_compare.LABELS_EN
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        path = plot_distribution.save_distribution_chart(
            str(tmp_path), "fallback", table, ["segment"],
            (np.array([1, 2, 2, 3]), np.array([1, 2, 3])),
        )

    assert Path(path).stat().st_size > 0
    assert not [warning for warning in caught if "Glyph" in str(warning.message)]

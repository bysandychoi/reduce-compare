"""CSV 수집·인코딩 감지 테스트 (T020, T021)."""
import os

import pandas as pd
import pytest

from app.core.ingest import (
    collect_csv_files,
    detect_delimiter,
    detect_encoding,
    read_csv,
    read_header,
)

SAMPLE = pd.DataFrame({"region": ["수도권", "영남"], "income": [4200, 5100]})


def _make_folder(tmp_path, encoding="utf-8"):
    SAMPLE.to_csv(tmp_path / "a.csv", index=False, encoding=encoding)
    SAMPLE.to_csv(tmp_path / "b.csv", index=False, encoding=encoding)
    (tmp_path / "readme.txt").write_text("csv 아님", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    SAMPLE.to_csv(sub / "c.csv", index=False, encoding=encoding)
    return tmp_path


def test_collect_csv_only(tmp_path):
    folder = _make_folder(tmp_path)
    names = [f.name for f in collect_csv_files(str(folder))]
    assert names == ["a.csv", "b.csv", os.path.join("sub", "c.csv")]


def test_collect_not_recursive(tmp_path):
    folder = _make_folder(tmp_path)
    names = [f.name for f in collect_csv_files(str(folder), recursive=False)]
    assert names == ["a.csv", "b.csv"]


def test_collect_missing_folder(tmp_path):
    with pytest.raises(NotADirectoryError):
        collect_csv_files(str(tmp_path / "없는폴더"))


def test_detect_and_read_cp949(tmp_path):
    path = tmp_path / "k.csv"
    SAMPLE.to_csv(path, index=False, encoding="cp949")
    assert detect_encoding(str(path)) in ("cp949", "euc-kr")
    df, enc = read_csv(str(path))
    assert list(df["region"]) == ["수도권", "영남"]
    assert enc in ("cp949", "euc-kr")


def test_read_utf8_bom(tmp_path):
    path = tmp_path / "bom.csv"
    SAMPLE.to_csv(path, index=False, encoding="utf-8-sig")
    df, enc = read_csv(str(path))
    assert list(df.columns) == ["region", "income"]
    assert enc == "utf-8-sig"


def test_read_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="내용이 없는"):
        read_csv(str(path))


def test_collect_reads_txt_and_tsv(tmp_path):
    SAMPLE.to_csv(tmp_path / "tab.txt", sep="\t", index=False)
    SAMPLE.to_csv(tmp_path / "pipe.tsv", sep="|", index=False)
    (tmp_path / "설명.txt").write_text("이 폴더 설명입니다.\n표가 아닙니다.\n", encoding="utf-8")
    names = [f.name for f in collect_csv_files(str(tmp_path))]
    assert names == ["pipe.tsv", "tab.txt"]          # 표가 아닌 txt는 빠진다


def test_delimiter_detection(tmp_path):
    for sep, fn in ((";", "semi.txt"), ("\t", "tab.txt"), ("|", "pipe.txt"), (",", "comma.csv")):
        path = tmp_path / fn
        SAMPLE.to_csv(path, sep=sep, index=False)
        assert detect_delimiter(str(path), detect_encoding(str(path))) == sep
        df, _ = read_csv(str(path))
        assert list(df.columns) == ["region", "income"]
        assert len(df) == 2


def test_read_header_only(tmp_path):
    path = tmp_path / "h.csv"
    SAMPLE.to_csv(path, index=False)
    assert read_header(str(path)) == ["region", "income"]

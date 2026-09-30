"""폴더에서 CSV를 찾아 읽는다 (T020 폴더 스캔, T021 인코딩 자동 감지)."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass

import pandas as pd

# 앞에서부터 시도한다. utf-8-sig가 BOM 있는 파일을 먼저 처리한다.
ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1")
CSV_SUFFIXES = (".csv", ".tsv", ".txt")      # txt·tsv는 구분자를 자동으로 찾는다
DELIMITERS = ",\t;|"


@dataclass
class CsvFile:
    """찾은 CSV 한 개."""

    path: str
    name: str
    size: int

    @property
    def rel(self) -> str:
        return self.name


def detect_delimiter(path: str, encoding: str) -> str:
    """구분자를 찾는다. 판단이 안 되면 후보 중 첫 줄에 가장 많이 나온 문자를 쓴다."""
    with open(path, encoding=encoding) as f:
        sample = f.read(8192)
    if not sample.strip():
        raise ValueError(f"내용이 없는 파일입니다: {os.path.basename(path)}")
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        head = sample.splitlines()[0]
        counts = {d: head.count(d) for d in DELIMITERS}
        best = max(counts, key=counts.get)
        return best if counts[best] else ","


def is_tabular(path: str) -> bool:
    """표로 읽을 수 있는 파일인지 본다 (설명용 txt를 걸러낸다)."""
    try:
        enc = detect_encoding(path)
        sep = detect_delimiter(path, enc)
        with open(path, encoding=enc) as f:
            head = f.readline()
        return head.count(sep) >= 1
    except (OSError, ValueError, UnicodeDecodeError):
        return False


def collect_csv_files(folder: str, recursive: bool = True) -> list[CsvFile]:
    """폴더에서 표 파일(.csv/.tsv/.txt)만 모아 경로 순으로 돌려준다.

    확장자가 맞아도 표로 읽을 수 없는 txt(설명 문서 등)는 건너뛴다.
    """
    if not os.path.isdir(folder):
        raise NotADirectoryError(f"폴더가 아닙니다: {folder}")
    found: list[CsvFile] = []
    walker = os.walk(folder) if recursive else [(folder, [], os.listdir(folder))]
    for root, _dirs, files in walker:
        for fn in files:
            if not fn.lower().endswith(CSV_SUFFIXES) or fn.startswith("."):
                continue
            full = os.path.join(root, fn)
            if fn.lower().endswith((".txt", ".tsv")) and not is_tabular(full):
                continue
            if os.path.isfile(full):
                found.append(CsvFile(path=full, name=os.path.relpath(full, folder),
                                     size=os.path.getsize(full)))
    return sorted(found, key=lambda f: f.name)


def detect_encoding(path: str, sample_rows: int = 200) -> str:
    """앞부분을 실제로 읽어 보며 깨지지 않는 인코딩을 고른다."""
    last_error: Exception | None = None
    for enc in ENCODINGS:
        try:
            with open(path, encoding=enc) as f:
                for i, _line in enumerate(f):
                    if i >= sample_rows:
                        break
            return enc
        except UnicodeDecodeError as e:  # 다음 인코딩으로 넘어간다
            last_error = e
    raise UnicodeDecodeError(
        "unknown", b"", 0, 1, f"인코딩을 찾지 못했습니다: {path} ({last_error})"
    )


def read_csv(path: str, encoding: str | None = None,
             nrows: int | None = None) -> tuple[pd.DataFrame, str]:
    """CSV를 읽어 (데이터프레임, 사용한 인코딩)을 돌려준다.

    빈 파일이나 열이 없는 파일은 무엇이 문제인지 알 수 있는 메시지로 올린다.
    """
    enc = encoding or detect_encoding(path)
    sep = detect_delimiter(path, enc)
    try:
        df = pd.read_csv(path, encoding=enc, nrows=nrows, sep=sep)
    except pd.errors.EmptyDataError as e:
        raise ValueError(f"내용이 없는 CSV입니다: {os.path.basename(path)}") from e
    except pd.errors.ParserError as e:
        raise ValueError(f"CSV 형식을 해석하지 못했습니다: {os.path.basename(path)} ({e})") from e
    if df.shape[1] == 0:
        raise ValueError(f"컬럼이 없는 CSV입니다: {os.path.basename(path)}")
    return df, enc


def read_header(path: str, encoding: str | None = None) -> list[str]:
    """헤더(컬럼 이름)만 읽는다. 큰 파일의 스키마 판별에 쓴다."""
    df, _ = read_csv(path, encoding=encoding, nrows=0)
    return list(df.columns)

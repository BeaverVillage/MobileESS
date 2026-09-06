from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd


def configure_logger(path: Path) -> logging.Logger:
    logger = logging.getLogger('kestrel_k5a')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    file_handler = logging.FileHandler(path, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        while block := file.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def copy_or_link(source: Path, target: Path, copy: bool) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copy2(source, target)
        return target
    return source


def zip_review(source_dir: Path, target_zip: Path) -> None:
    target_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in source_dir.rglob('*'):
            if not path.is_file() or path.suffix.lower() == '.parquet':
                continue
            archive.write(path, path.relative_to(source_dir))


def dataframe_to_markdown(frame: pd.DataFrame, max_rows: int = 30) -> str:
    if frame.empty:
        return '_No rows_'
    view = frame.head(max_rows)
    headers = [str(c) for c in view.columns]
    lines = ['| ' + ' | '.join(headers) + ' |', '|' + '|'.join('---:' for _ in headers) + '|']
    for row in view.itertuples(index=False, name=None):
        values = []
        for value in row:
            if isinstance(value, float):
                values.append(f'{value:.6g}')
            else:
                values.append(str(value).replace('|', '\\|'))
        lines.append('| ' + ' | '.join(values) + ' |')
    return '\n'.join(lines)

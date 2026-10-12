"""Fetch only the local layout/table models used by the PDF pipeline."""
import os
from pathlib import Path

from docling.utils.model_downloader import download_models

if __name__ == "__main__":
    download_models(
        output_dir=Path(os.environ.get("DOCLING_ARTIFACTS_PATH", "/opt/docling-models")),
        with_layout=True, with_tableformer=True,
        with_code_formula=False, with_picture_classifier=False, with_rapidocr=False,
    )

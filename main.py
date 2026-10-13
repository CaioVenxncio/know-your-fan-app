"""Streamlit entry point: ``streamlit run main.py``.

The package lives in ``src/``. When it has not been installed (for example on a
host that only runs ``pip install -r requirements.txt``), ``src/`` is added to
the import path so the app still starts.
"""

import sys
from pathlib import Path

try:
    from know_your_fan.app import main
except ModuleNotFoundError as exc:
    if exc.name != "know_your_fan":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from know_your_fan.app import main

main()

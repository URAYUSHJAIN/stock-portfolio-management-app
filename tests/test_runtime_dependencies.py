"""Guard the Arrow/NumPy interface used by Streamlit dataframes."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

local_deps = Path(__file__).resolve().parents[1] / ".deps"
if local_deps.exists() and str(local_deps) not in sys.path:
    sys.path.append(str(local_deps))

import pyarrow as pa  # noqa: E402


def test_pyarrow_can_convert_a_pandas_dataframe() -> None:
    """Catch incompatible PyArrow wheels before the dashboard reaches st.dataframe."""
    frame = pd.DataFrame({"value": np.array([1, 2], dtype=np.int64)})
    table = pa.Table.from_pandas(frame)
    assert table.column("value").to_pylist() == [1, 2]

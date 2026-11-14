"""Run the permanent evaluation tests in the same serverless environment as the job."""

from pathlib import Path
import sys

sys.dont_write_bytecode = True  # Workspace source snapshots are read-only on serverless.
root = Path(globals().get("__file__", sys.argv[0])).resolve().parents[2]
sys.path.insert(0, str(root))

import numpy
import pandas
import pyarrow
import pytest

print({"numpy": numpy.__version__, "pandas": pandas.__version__, "pyarrow": pyarrow.__version__})
result = pytest.main([str(root / "core/tests"), "-q", "-p", "no:cacheprovider"])
if result:
    raise RuntimeError(f"Evaluation tests failed with exit code {result}")

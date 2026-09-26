"""Run project tests without touching any operational SQLite database."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

with tempfile.TemporaryDirectory(prefix='portus-tests-') as directory:
    os.environ['PORTUS_DB_PATH'] = str(Path(directory) / 'tests.db')
    os.environ['PORTUS_DEMO_DATA'] = 'true'
    from PortusFase2.server import app
    app.terminal_state['protocolo'] = 'mock'
    runner = unittest.TextTestRunner(verbosity=1)
    first = runner.run(unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_*.py'))
    second = runner.run(unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='validate_scenarios.py'))
    sys.exit(0 if first.wasSuccessful() and second.wasSuccessful() else 1)

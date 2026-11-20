import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The licensed source workbook and the raw POI archive are not redistributed
# (see README.md). Override these with environment variables before running the
# reconstruction pipeline.
ORIGINAL = Path(os.environ.get('MCA_ORIGINAL_DIR', ROOT / 'inputs' / 'original'))
V2 = Path(os.environ.get('MCA_V2_DIR', ROOT.parent / 'Sustainability_Unified_Revision_Workspace_20261106_v2'))
POI_ROOT = Path(os.environ.get('MCA_POI_ROOT', ROOT / 'inputs' / 'poi'))
DIRS = ['02_audit', '03_cache', '04_data', '05_results', '06_logs', '07_report']
for name in DIRS:
    (ROOT / name).mkdir(parents=True, exist_ok=True)
RADII = [1, 3, 5, 10]
CATEGORIES = ['retail', 'bar', 'nightclub', 'ktv', 'disco']
CONTROLS = ['Size', 'Lev', 'ROA', 'Growth', 'CashFlow', 'FirmAge', 'SOE', 'Board', 'Indep', 'Dual', 'Top1', 'Inst', 'Big4']

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve()
datas = [
    (str(ROOT / "migrations"), "resources/migrations"),
    (str(ROOT / "rules"), "resources/rules"),
    (str(ROOT / "config" / "strategies"), "resources/config/strategies"),
    (str(ROOT / "contracts" / "schemas"), "resources/contracts/schemas"),
    (str(ROOT / "tests" / "fixtures"), "resources/tests/fixtures"),
]
binaries = []
hiddenimports = []

for package in ("akshare", "tushare", "duckdb", "langgraph", "pydantic"):
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package)
    except Exception:
        continue
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hiddenimports)

analysis = Analysis(
    ["sidecar_entry.py"],
    pathex=[str(ROOT / "packages-py" / "pia_runtime")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="pia-runtime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

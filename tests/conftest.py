"""pytest 共享 fixtures。"""
import sys
from pathlib import Path

# 把 lab_scripts 加到 sys.path，让测试可以直接 import 模块
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lab_scripts"))

# 提供常用 fixture
import pytest


@pytest.fixture
def ieee14_path():
    return str(ROOT / "Grids_and_profiles" / "grids" / "IEEE 14 bus.raw")

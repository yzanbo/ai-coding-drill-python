"""conftest.py の DSN suffix guard が dev DSN を弾くことを保証する。

guard は dev DB の作業データ消失事故 (issue #86) を構造的に防ぐ最後の砦。
将来コミットで誤って guard が緩む / 削除されることを CI で検知する目的で、
本テストは「dev 風 DSN を渡したら pytest 自体が起動拒否される」を観察する。

仕組み：
  - subprocess で子の pytest を起動し、PYTEST_DATABASE_URL に `_test` で終わらない
    dev 風 DSN を渡す
  - conftest.py の suffix guard が import 時 (app.main 読み込み前) に RuntimeError を投げ、
    子の pytest が collection 段階で非ゼロ exit するはず
  - 子プロセスの stderr に「DB 名末尾 '_test'」のガードメッセージが含まれることも確認
"""

import os
import subprocess
import sys
from pathlib import Path


def test_pytest_は_dev_DSN_では起動できない() -> None:
    # apps/api/ をカレントにして pytest を子プロセスで起動 (本ファイルから 2 階層上)。
    api_root = Path(__file__).resolve().parents[2]
    # 既存環境を継承しつつ PYTEST_DATABASE_URL を dev 風 DSN で上書きする。
    # PYTEST_DATABASE_URL は conftest.py のフォールバック順で最優先のため、
    # TEST_DATABASE_URL や os 既定の DATABASE_URL より先にこの値が採用される。
    child_env = {
        **os.environ,
        "PYTEST_DATABASE_URL": (
            "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill"
        ),
    }
    # --collect-only で実テスト実行はせず conftest.py の import 副作用だけ起こす。
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=api_root,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, (
        "dev DSN で pytest が collection できてしまった (suffix guard が機能していない)。"
        f" stdout/stderr:\n{combined}"
    )
    assert "_test" in combined, (
        f"guard のエラーメッセージが見当たらない。stdout/stderr:\n{combined}"
    )

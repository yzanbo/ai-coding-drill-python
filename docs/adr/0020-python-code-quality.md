# 0020. Python のコード品質ツールに ruff + pyright を採用

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- Python pivot（ADR 0033）に追従、R7 想定からバックエンド本体に役割変更。同日に型チェッカーも pyright で確定 -->
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0033](./0033-backend-language-pivot-to-python.md) でバックエンドが Python に pivot され、Python は **バックエンド本体の言語**として MVP から使われる。これに伴い Python 側のコード品質ツール（フォーマット・lint・型チェック）の方針を確定しておく必要がある。

- 当初本 ADR は「R7 分析パイプライン用の Python ツール選定」として起票されたが、pivot により対象が**バックエンド本体に変更**された
- 型チェッカーは当初「バックエンド着手時に再評価」として遅延していたが、2026-05 時点で各候補の状況を再調査した結果、判断材料が十分揃ったため**本 ADR で確定**する
- 「3 言語に等価な品質ゲートを設計した」と語れる構成にする

関連：

- TS の品質ツール → [ADR 0018](./0018-biome-for-tooling.md)（Superseded by 0033、移行軌跡として保持）
- Go の品質ツール → [ADR 0019](./0019-go-code-quality.md)
- 「可逆な判断は遅延させる」原則 → [ADR 0007: LLM プロバイダ抽象化](./0007-llm-provider-abstraction.md)

## Decision（決定内容）

- **lint + format に [`ruff`](https://docs.astral.sh/ruff/)** を採用する（Astral 製、Rust、linter + formatter 統合）
- **型チェックに [`pyright`](https://github.com/microsoft/pyright)** を採用する（Microsoft 製、TS 製、VS Code では Pylance として動作）
  - 開始は `typeCheckingMode = "basic"`、コードベースが安定したら `"strict"` への段階的引き上げを検討
  - 設定は `pyproject.toml` の `[tool.pyright]` に集約
- **`pyrefly`（Meta）/ `ty`（Astral）は将来の乗り換え候補**として watch する（§Consequences の見直しトリガー参照）

依存パッケージの脆弱性スキャン（`pip-audit`）は本 ADR の対象外。uv の lockfile を入力源とするため、[ADR 0035](./0035-uv-for-python-package-management.md) に集約する。

## Why（採用理由）

### なぜ ruff か（lint + format 統合）

1. **`lint + format` を Rust で統合**
   - Astral 製で `flake8` / `black` / `isort` 等を 1 ツールに置換
   - TS の Biome（[ADR 0018](./0018-biome-for-tooling.md)、Superseded by 0033 だが設計思想は継承）と対称的な設計思想（Rust 製・統合・高速）で、3 言語横断で「単一ツール統合」哲学が一貫する
2. **CI 高速化**
   - 大規模コードベースで flake8 + black + isort の数十倍速、CI 時間を顕著に短縮
3. **エコシステム集中**
   - ruff 単体で `flake8-bugbear` / `pyupgrade` / `pylint` 系ルール群を吸収、依存ツリーが薄い
4. **Astral エコシステム統合の余地**
   - ruff / uv / ty が同社製で連携する将来性に賭ける（パッケージ管理の `uv` もバックエンド着手時に正式採用候補）

### なぜ pyright か（型チェッカー）

1. **型仕様準拠率 98%（2026-05 時点）が他を圧倒**
   - mypy 58% / Pyrefly 90% / ty 53% に対し pyright は 98%
   - 新しい typing PEP の対応も最速、ライブラリ側 stub との齟齬が最少
2. **VS Code / Cursor で Pylance が標準**
   - 追加設定なしで保存即フィードバック、開発体験が完結する
   - IDE での即時警告は「警告を放置しない」運用ルールと整合
3. **`tsc --noEmit` 相当の運用感**
   - `strict` モードで段階的にゲートを締められる（11 段階の個別フラグ）
   - TS（Biome + tsc）→ Python（ruff + pyright）→ Go（gofmt + golangci-lint）で**「lint+format 1 本 / 型 1 本」の二層構造を 3 言語で揃えられる**
4. **CI でも安定**
   - `pyright` CLI が存在し、Microsoft が週次リリース、運用実績充分
5. **乗り換えコストが小さい**
   - `pyproject.toml` の `[tool.<checker>]` セクション差し替えで Pyrefly / ty へ移行可能、現時点で pyright を選んでも将来の選択肢を狭めない

### なぜ Pyrefly / ty を今は採らないか

- **Pyrefly（Meta）**：準拠率 90%・Instagram 2000 万行で本番運用中・PyTorch / JAX 採用と魅力的だが、**2026-05 時点で beta**。準拠率も pyright に届かない。GA かつ準拠率 95% 超を確認してから乗り換え判断する
- **ty（Astral）**：ruff / uv との同社統合は美しいが、**バージョン 0.0.x で破壊的変更継続中、準拠率 53% は最下位**。1.0 GA を待つ
- 両者とも「速度」を打ち出すが、**このプロジェクト規模（小〜中）では速度差は体感できない**ため採用ドライバにならない

## Alternatives Considered（検討した代替案）

### lint + format ツール

| 候補 | 採用しなかった理由 |
|---|---|
| ruff（採用） | — |
| flake8 + black + isort | 3 ツール構成、CI 遅い、設定ファイル乱立、メンテ衰退傾向 |
| pylint | 高機能だが遅く設定が冗長、ruff が pylint 系ルールも順次取り込み中 |

### 型チェッカー（2026-05 時点の比較）

| 候補 | 状態 | 型仕様準拠率 | 速度 | 採用判定 |
|---|---|---|---|---|
| **pyright（Microsoft、採用）** | 安定 | **98%** | 標準 | 採用：準拠率最高、Pylance で IDE 統合最強、運用実績充分 |
| Pyrefly（Meta） | beta | 90%（2026-04 時点） | 超高速（Rust） | 不採用：beta、準拠率が pyright に届かず。GA + 95% 超で再評価 |
| ty（Astral） | beta（0.0.x） | 53% | 最速（mypy/pyright の 10〜60 倍） | 不採用：破壊的変更継続中、準拠率最下位。1.0 GA で再評価 |
| mypy | 安定 | 58% | mypyc 後で改善 | 不採用：準拠率・速度ともに pyright に劣る。`pydantic` / `SQLAlchemy` 連携プラグインが必須になった場合のみ採用検討 |

## Consequences（結果・トレードオフ）

### 得られるもの

- 型仕様準拠率 98% という現時点で最も信頼性の高い型チェック基盤
- Pylance による IDE 統合で「保存即型エラー検知」の開発体験
- TS（Biome + tsc）/ Python（ruff + pyright）/ Go（gofmt + golangci-lint）で **3 言語に等価な「lint+format 1 本 / 型 1 本」の二層品質ゲート**を実現
- pyproject.toml への設定集約により、将来の Pyrefly / ty への乗り換えコストが小さい

### 失うもの・受容するリスク

- Astral 統合の美しさ（ruff / uv / ty で同社揃え）は今は採れない
- pyright は TypeScript 製で Pyrefly / ty より遅い（ただしこのプロジェクト規模では体感できない）
- ruff の rule set 拡充は速いが、特殊なルール（pylint 由来の一部）はカバー外の時期がある
- pyright は MIT ライセンスだが Pylance 拡張のクローズドソース部分があるため、一部の純 OSS 主義環境では避けられる場合がある（このプロジェクトには該当しない）

### 将来の見直しトリガー

- **Pyrefly が GA（alpha/beta ラベル除去）し、準拠率 95% 以上に到達した場合**
  - Pydantic / Django 組込サポート + Rust 製の高速性が魅力。乗り換えを再評価
- **ty が 1.0 GA に到達した場合**
  - Astral 統合（ruff / uv / ty）の一貫性が得られる。準拠率と stub 互換性を確認の上で乗り換え判断
- **2027 年頃を目安に再評価**（上記いずれかが発生していなくても、市場状況をレビューして本 ADR の妥当性を確認）
- 乗り換える場合は新規 ADR を起票し、本 ADR を Superseded by する形にする
- ruff が衰退・停滞した場合（極めて低確率）→ 個別ツール（black + isort + flake8）併用に戻す検討

## References

- [06-dev-workflow.md: コード品質ツール](../requirements/2-foundation/06-dev-workflow.md#コード品質ツール)
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（本 ADR の役割を「R7 分析」から「バックエンド本体」に変更した契機）
- [ADR 0034: バックエンド API に FastAPI を採用](./0034-fastapi-for-backend.md)
- [ADR 0018: TypeScript のコード品質ツール](./0018-biome-for-tooling.md)（Superseded by 0033）
- [ADR 0019: Go のコード品質ツール](./0019-go-code-quality.md)
- [ADR 0003: レイヤ別ポリグロット構成](./0003-phased-language-introduction.md)
- [ADR 0007: LLM プロバイダ抽象化（"可逆な判断は遅延させる" 原則）](./0007-llm-provider-abstraction.md)
- [Astral（ruff / uv / ty）](https://astral.sh/)
- [pyright 公式](https://github.com/microsoft/pyright)
- [Pyrefly（Meta）](https://pyrefly.org/)
- [Python Type Checker Comparison: Typing Spec Conformance](https://pyrefly.org/blog/typing-conformance-comparison/)

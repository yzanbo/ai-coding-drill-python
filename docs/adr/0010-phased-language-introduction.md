# 0010. 言語の段階導入（MVP は TS+Go、Phase 7 で Python 追加）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

ポートフォリオで複数言語を扱える証明をしたい。一方で、MVP の完成リスクは抑えたい。

- 候補言語：TypeScript（実務）、Go（差別化）、Python（AI/データ系）
- 「広く浅く」になることを避けたい
- 各言語の使いどころに**明確な役割**が欲しい

## Decision（決定内容）

3 言語を**段階的に導入**する：

| フェーズ | 言語構成 | 役割 |
|---|---|---|
| MVP | TypeScript（Web/API/LLM）+ Go（採点ワーカー） | 最短で動かす、Go の強みを活かす |
| 次期（Phase 7） | 上記 + Python（評価・分析パイプライン） | オフライン評価バッチ、重複検出、分布分析、人間評価との相関 |
| 将来 | 採点対象言語の多言語化（Python、Next.js コンポーネント等） | 言語アダプタ層を通じて追加 |

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| 段階導入（TS+Go → +Python） | フェーズで責務を分離 | （採用） |
| MVP から 3 言語（TS + Go + Python） | 一気に揃える | MVP 完成リスクが高い、Phase 7 の見せ場を作れない |
| TS のみ | シンプル | ポリグロットの差別化が消える |
| TS + Python（Go なし） | AI 系の見せ方優先 | 採点ワーカーの軽量・並列特性に Python は不向き |
| TS + Go のみ（Python 入れない） | 簡略 | AI エンジニア志望の見せ場が弱まる |

## Consequences（結果・トレードオフ）

### 得られるもの
- MVP は 2 言語で完成リスクを抑え、各言語の役割が明確
- Phase 7 で Python を「設計の進化」として導入でき、ポートフォリオで段階的成長を語れる
- 「言語選定ができる」レベルを示せる（広く浅くではなく、適材適所）

### 失うもの・受容するリスク
- MVP 時点では Python の経験がポートフォリオに出ない
- 言語ごとに採点対象を増やすには言語アダプタ層の抽象化を最初から意識する必要がある

### 将来の見直しトリガー
- Phase 7 で Python パイプラインを追加するタイミングで、必要なら Rust など別言語の追加も再検討

## References

- [01-overview.md: 言語・フレームワーク構成ロードマップ](../requirements/1-vision/01-overview.md)
- [02-architecture.md: 言語構成ロードマップ](../requirements/2-foundation/02-architecture.md)
- [01-roadmap.md: Phase 7](../requirements/5-roadmap/01-roadmap.md)

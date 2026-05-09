# 0013. Frontend ホスティングに Vercel を採用（AWS Amplify / S3+CloudFront / ECS Fargate 不採用）

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0002](./0002-aws-single-cloud.md) で AWS 単独に決めたが、Frontend（Next.js App Router）のホスティング先を検討した結果、**Frontend だけは外部 SaaS の方が合理的**と判断する局面が出た。

- Frontend スタック：Next.js 16+（App Router、RSC、CodeMirror エディタ）
- 用途：SSR + 静的配信、認証セッション維持、エディタ UI
- 想定トラフィック：数百ユーザー × 数十リクエスト/日（ポートフォリオ規模）
- コスト目標：Frontend 部分で月 $0
- ADR 0002 では「Vercel + Fly.io + Supabase 等の SaaS 寄せ集め」を不採用と明記しており、Vercel 単体採用も同方針との整合説明が必要
- すでに [ADR 0012](./0012-upstash-redis-over-elasticache.md) で Redis に Upstash を採用しており、AWS 単独方針からの「合理的逸脱」の前例がある

## Decision（決定内容）

**Vercel** を Frontend ホスティングに採用する。AWS 単独の方針からは一部外れるが、Next.js とのファーストパーティ統合とコスト効率を優先する。

## Why（採用理由）

1. **Next.js とのファーストパーティ統合**
   - Vercel は Next.js の開発元であり、App Router / Server Components / ISR / Image Optimization / Edge Runtime 等の最新機能が**最も早く・最も自然に**動く
   - AWS Amplify Hosting も Next.js 対応を謳うが、新機能の追従に遅れが出やすく、トラブル時の情報量も Vercel が圧倒的
2. **コスト目標（月 $0）への適合**
   - Hobby プランの無料枠（100 GB 帯域 / ビルド時間）で本プロジェクトのトラフィック（数百ユーザー × 数十リクエスト/日）を十分カバー
   - ECS Fargate に SSR を載せると最小タスク 1 常駐で月額が発生し、Frontend だけで AWS コストが膨らむ
3. **運用負荷ゼロ**
   - GitHub リポジトリ連携で push 即デプロイ、PR ごとのプレビュー環境が自動生成される
   - エッジ CDN・SSL 証明書・キャッシュ無効化が標準装備で、Terraform で組む必要がない
4. **AWS 単一クラウド方針からの逸脱を「合理的判断」として説明可能**
   - ADR 0002 は **「Vercel + Fly.io + Supabase 等の SaaS 寄せ集め」** を不採用としたが、これは「クラウド選定の見せ場が薄い」「IAM/IaC の練習機会が減る」が主理由
   - 本プロジェクトでは Backend API / 採点ワーカー / DB / シークレット管理など **コアの設計判断は AWS 上で完結**しており、Frontend の単独逸脱はその主理由に抵触しない
   - ADR 0012（Upstash）と同じく、原則の機械的適用ではなく適合性とコスト効率を優先した明示的判断として README に記録できる
5. **将来の戻り道が確保されている**
   - Next.js は Vercel 専用ではないため、必要になれば AWS Amplify / ECS Fargate / Cloudflare Pages へ移行可能
   - Vercel 固有 API（Edge Functions / Image Optimization 等）への依存度を意識的に抑えれば移行コストは低い

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Vercel | Next.js 開発元のホスティング、Hobby 無料枠 | （採用） |
| AWS Amplify Hosting | AWS 純正、Next.js SSR 対応、AWS 単独方針に沿う | Next.js 新機能の追従遅延、Vercel に比べて情報量・トラブル事例が薄い、無料枠の制限が厳しい |
| S3 + CloudFront | AWS 標準の静的配信、コスト最小 | App Router の SSR / RSC が動かない（静的書き出しのみ）、本プロジェクトは認証セッション維持と動的レンダリングが必要 |
| ECS Fargate 上で Next.js を SSR 実行 | AWS 単独方針に沿う、Backend API と同じ基盤 | 最小タスク 1 常駐で月額固定費が発生、エッジ配信できないためレイテンシ不利、Frontend と Backend の責務分離が薄れる |
| EC2 自前 Next.js | コスト最小化が可能 | 運用負荷高、SSL / CDN を自前で組む必要、ポートフォリオ規模に対して過剰 |
| Cloudflare Pages | エッジ配信、Next.js 対応、無料枠豊富 | Next.js 対応は Vercel に一段劣る、AWS 単独方針からの逸脱コストを払うなら Next.js 純正の Vercel が筋 |
| Netlify | Next.js 対応、無料枠 | Vercel との機能差が小さい一方、Next.js 純正サポートで Vercel に劣るため採る理由がない |

## Consequences（結果・トレードオフ）

### 得られるもの
- 月 $0 で Frontend を運用可能、Hobby 無料枠で本プロジェクトのトラフィックを十分カバー
- Next.js の最新機能を即座に活用でき、ポートフォリオで「最新フレームワークを使いこなしている」と示せる
- GitHub 連携で push 即デプロイ・PR プレビュー環境が標準装備、開発体験が大幅改善
- 「AWS 一本」を維持しつつ、Frontend の適合性と無料枠を取りに行った合理的判断として README で説明可能

### 失うもの・受容するリスク
- 厳密には「AWS 一本」の方針に 2 例目の例外を作っている（1 例目は ADR 0012 Upstash）
- Frontend と Backend で環境変数 / シークレット管理が 2 系統に分かれる（Vercel の env と AWS Secrets Manager / Parameter Store）
- Vercel 固有 API（Edge Functions / Image Optimization）に依存しすぎると移行コストが膨らむため、利用範囲を意識的に抑える必要がある
- VPC 内に閉じ込められない（Frontend は public で問題なし、Backend API への通信は HTTPS over TLS）

### 将来の見直しトリガー
- Hobby 無料枠（帯域 100 GB / ビルド時間）を超過した場合は Pro プラン（$20/月）または AWS Amplify への移行を検討
- AWS への完全集約が要件として浮上した場合（例：エンタープライズ要件で全リソースを VPC 内にまとめる必要）
- Vercel 固有 API への依存度が想定を超えて高まった場合（移行コストの再評価）

## References

- [02-architecture.md: 物理配置](../requirements/2-foundation/02-architecture.md#物理配置責務分離)
- [05-runtime-stack.md: デプロイ先](../requirements/2-foundation/05-runtime-stack.md#デプロイ先)
- [ADR 0002](./0002-aws-single-cloud.md)：AWS 単独方針
- [ADR 0012](./0012-upstash-redis-over-elasticache.md)：AWS 単独方針からの 1 例目の例外（Upstash）

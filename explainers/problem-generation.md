# 問題のつくられ方（エンジニアじゃない人向け）

このサイトは、プログラミングの練習問題を **AI に作らせて** います。
でも「AI が作ったものをそのまま出す」ことはしません。

ここでは、「新しい問題がほしい」と頼んでから、
実際に解ける問題が手元に届くまで、裏で何が起きているかを
**絵と例え話だけ** で、まずはざっくり説明します。

> ℹ️ この流れは **今ちゃんと動いています**。
> ただし今は、みなさんの答えを採点する「職人」が、問題作りも **兼任** しています
> （同じ職人が 2 つの仕事を担当）。将来は問題作り専任の職人に分ける予定ですが、
> やっていることは下の説明と同じです。

---

## いちばん大事な考え方：AI を信用しすぎない

AI（文章を書くのが得意な人工知能）は、問題作りがとても上手です。
でも、ときどき **まちがえます**。

- 問題文は読めるのに、**模範解答が実は動かない**
- テスト（採点の基準）が**ズレていて、正しい答えなのに不正解になる**
- どこかで見たような**ありきたりな問題**を出してくる

そこでこのサイトは、**AI が作った問題をそのまま信用せず**、
「本当にちゃんとした問題か？」を **機械で確かめてから** みなさんに届けます。

例えるなら、**料理人（AI）が作った料理を、お客さんに出す前に
味見係がチェックする** ようなものです。

---

## 登場人物（システム構成）

```
 ブラウザ    Backend API   ジョブキュー    Worker        生成 LLM     Sandbox      Judge LLM    Postgres
 (ユーザー)  (FastAPI)    (jobs テーブル) (Go)          (Gemini)    (Docker)     (品質評価)   (問題保管)
   👤        🏪            📋            🧑‍🍳          🤖          🧪           🧐          📚
```

各コンポーネントの役割（**例え名** は直感的に掴むための補助。本文・図ではコンポーネント名を使います）：

| コンポーネント | 例え名 | 役割 |
|---|---|---|
| **ブラウザ（ユーザー）** | あなた | カテゴリ・難易度を指定して生成をリクエストする |
| **Backend API（FastAPI / Python）** | 受付 | リクエストを受けて **ジョブを enqueue するだけ**。LLM は呼ばず即 `202` を返す（→ [ADR 0040](../docs/adr/0040-worker-grouping-and-llm-in-worker.md)） |
| **ジョブキュー（Postgres の `jobs` テーブル）** | やることリスト | 生成ジョブを貯める待ち行列。`SELECT FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY` で Worker に渡す（→ [ADR 0004](../docs/adr/0004-postgres-as-job-queue.md)） |
| **Worker（Go）** | 職人 | ジョブを取り出し、生成 → 検証 → 評価 → 保存を実行する裏方。**現状は採点 Worker（`apps/workers/grading`）が生成も兼務**（専任の `apps/workers/generation` への切り出しは R7 予定） |
| **生成 LLM（Google Gemini）** | AI | 問題文・入出力例・テストケース・模範解答を生成。抽象化レイヤ経由で差し替え可能（→ [ADR 0007](../docs/adr/0007-llm-provider-abstraction.md)）。`temperature=0.7` + JSON mode |
| **Sandbox（Docker コンテナ）** | 検査室 | 模範解答を Vitest で実行し動作保証。ネットワーク遮断・メモリ/CPU/PID 制限・read-only の隔離環境（→ [ADR 0009](../docs/adr/0009-disposable-sandbox-container.md)） |
| **Judge LLM** | 審査員 | 生成した問題の品質を 5 軸で評価する **別用途の LLM 呼び出し**。自己評価バイアスを避ける（→ [ADR 0008](../docs/adr/0008-custom-llm-judge.md)）。`temperature=0.0` + JSON mode |
| **Postgres（`problems` / `generation_requests`）** | 本棚 | 完成した問題と、生成リクエストの進捗・結果を永続化する |

> 🤔 なぜ Backend API（受付）と Worker（職人）を分けるの？
> 問題生成は LLM 呼び出し + サンドボックス実行 + Judge 評価で数秒〜数十秒かかります。
> API が同期で処理するとレスポンスが遅く・不安定になるため、API は **enqueue だけして即返し**、
> 重い処理は非同期で Worker に委譲します。ユーザーはすぐ「作成中…」画面に遷移でき、
> API のレスポンス時間も予測可能に保てます（→ [ADR 0040](../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。

---

## 全体の流れ（ざっくり版）

```
①リクエスト送信         ②API が enqueue            ③Worker がジョブ取得
   👤 ブラウザ            🏪 Backend API             🧑‍🍳 Worker
   │ POST /api/          │ generation_requests       │ SELECT FOR UPDATE
   │  problems/generate  │  + jobs に INSERT          │  SKIP LOCKED で claim
   │ {category,          │  + NOTIFY                  │ (NOTIFY 受信 or
   │  difficulty}        │ → 202 即返                 │  30 秒ポーリング)
   ▼                     ▼ (ブラウザはポーリング開始)  ▼
 ┌──────┐             ┌──────┐                  ┌──────┐
 │ API  │ ──────────►│ジョブ  │ ◄────────────── │Worker│
 │ 🏪    │             │キュー │                  │ 🧑‍🍳  │
 └──────┘             │ 📋   │                  └──────┘
                       └──────┘


④生成 LLM 呼び出し      ⑤Sandbox で検証            ⑥Judge LLM で評価
   step=llm_generating   step=sandbox_verifying      step=judging
   🤖 生成 LLM           🧪 Sandbox (Docker)         🧐 Judge LLM
   │ 問題文・入出力例・    │ 模範解答を Vitest で       │ 5 軸（明確さ/網羅性/
   ▼ テスト・模範解答      ▼ 実行（隔離コンテナ）       ▼ 難易度/教育的価値/独自性）
 ┌──────┐             ┌──────┐                  ┌──────┐
 │生成LLM│             │Sandbox│                  │Judge │
 │ 🤖   │             │ 🧪   │                  │ 🧐   │
 └──────┘             └──────┘                  └──────┘
   │                      │                          │
   │ ProblemDraft         │ ❌テスト失敗/timeout→再生成 │ ❌閾値未満→再生成
   │ (JSON) を取得         │ ✅全テスト通過→次へ         │ ✅合格点→次へ
   ▼                      ▼                          ▼


⑦Postgres に保存        ⑧ブラウザが完了検出
   step=persisting        👤 ブラウザ
   🧑‍🍳 Worker            │ ポーリングで
   │ problems INSERT      ▼ status=completed を検出
   ▼ + generation_       ┌──────────┐
 ┌────────┐ requests    │ /problems/:id │
 │Postgres│ =completed   │ へ自動遷移 ✏️  │
 │ 📚     │ ───────────►│ (problemId)   │
 └────────┘             └──────────┘
```

ポイントは ⑤と⑥の **2 段階の品質ゲート** です（「LLM 出力を信用しない」設計の中核）。

- **⑤ Sandbox（決定論的チェック）**：模範解答を隔離コンテナで実行し、**全テストが通るか機械的に検証**
- **⑥ Judge LLM（評価的チェック）**：生成とは **別用途の LLM 呼び出し** で教材としての品質を 5 軸採点

この 2 つを通過した ProblemDraft だけが `problems` に INSERT され、ユーザーに届きます。
途中で失敗した場合は **上位モデルで最大 3 回まで再生成**、それでも全失敗なら
`generation_requests.status='failed'` を返し、ブラウザは「生成に失敗しました」と表示します
（再生成・コスト上限 USD 0.20 の打ち切りは [problem-generation.md](../docs/requirements/4-features/problem-generation.md) を参照）。

---

## まとめ

```
   ┌────────────────────────────────────────────────┐
   │ 問題は LLM が生成するが、そのまま採用しない        │
   │                                                │
   │  Backend API は enqueue だけして 202 を即返す     │
   │  Worker が非同期でジョブを取り、生成 LLM を呼ぶ    │
   │  Sandbox(Docker) で模範解答を実行し動作保証        │
   │  Judge LLM（別呼び出し）で品質を 5 軸評価          │
   │  2 つのゲートを通った問題だけを Postgres に保存    │
   └────────────────────────────────────────────────┘
```

ユーザーの操作は **カテゴリ・難易度を指定してリクエストするだけ**。
あとは API → ジョブキュー → Worker → LLM / Sandbox / Judge → Postgres の
非同期パイプラインが、**動作保証された問題だけ** を選んで届けます。

---

## もっと詳しく知りたい人へ

技術的な仕様は以下のドキュメントを参照してください（エンジニア向け）：

- [../docs/requirements/4-features/problem-generation.md](../docs/requirements/4-features/problem-generation.md) — 問題生成の正式な要件定義
- [../SYSTEM_OVERVIEW.md](../SYSTEM_OVERVIEW.md) — システム全体の流れ
- [../docs/adr/0004-postgres-as-job-queue.md](../docs/adr/0004-postgres-as-job-queue.md) — 「やることリスト」の仕組み（ジョブキュー）
- [../docs/adr/0008-custom-llm-judge.md](../docs/adr/0008-custom-llm-judge.md) — なぜ別の AI（審査員）で採点するか
- [../docs/adr/0009-disposable-sandbox-container.md](../docs/adr/0009-disposable-sandbox-container.md) — 検査室（サンドボックス）の仕組み

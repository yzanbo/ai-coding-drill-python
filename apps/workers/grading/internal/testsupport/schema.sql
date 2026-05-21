-- Worker integration テスト用の最小スキーマ。
--
-- ⚠️ 同期必須:
--   本ファイルは apps/api/alembic/versions/ の Alembic マイグレーション結果と
--   同じ schema を表現する。Alembic 側で schema 変更があったら本ファイルを
--   手で追随する必要がある。CI で diff 検出する gate は未整備 (TODO)。
--
-- 構造:
--   - gen_random_uuid() のため pgcrypto 拡張を有効化
--   - users / problems / generation_requests / jobs / submissions の 5 テーブル
--   - 認証 (auth_providers) は Worker integration テストでは触らないため省略
--
-- Worker 実装側 SSoT との対応:
--   - jobs           : apps/api/app/models/jobs.py
--   - generation_requests : apps/api/app/models/generation_requests.py
--   - problems       : apps/api/app/models/problems.py
--   - submissions    : apps/api/app/models/submissions.py (R1-5 採点フローで追加)
--   - users          : apps/api/app/models/users.py (一部のみ)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- users: generation_requests.user_id の FK を満たすだけの最小定義。
CREATE TABLE IF NOT EXISTS users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email       VARCHAR,
  display_name VARCHAR NOT NULL,
  created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  deleted_at  TIMESTAMP WITH TIME ZONE
);

-- problems: 完成した問題本体。Worker (R1〜R6 は grading) が INSERT する。
CREATE TABLE IF NOT EXISTS problems (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title               VARCHAR(255) NOT NULL,
  description         VARCHAR NOT NULL,
  category            VARCHAR(32) NOT NULL,
  difficulty          VARCHAR(16) NOT NULL,
  language            VARCHAR(32) NOT NULL,
  examples            JSONB NOT NULL,
  test_cases          JSONB NOT NULL,
  reference_solution  VARCHAR NOT NULL,
  judge_scores        JSONB NOT NULL,
  created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  deleted_at          TIMESTAMP WITH TIME ZONE
);

-- generation_requests: 問題生成リクエストの受付台帳。
CREATE TABLE IF NOT EXISTS generation_requests (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category             VARCHAR(32) NOT NULL,
  difficulty           VARCHAR(16) NOT NULL,
  status               VARCHAR(16) NOT NULL DEFAULT 'pending',
  produced_problem_id  UUID REFERENCES problems(id) ON DELETE SET NULL,
  created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_generation_requests_user_id_created_at
  ON generation_requests(user_id, created_at);

-- jobs: Postgres を SELECT FOR UPDATE SKIP LOCKED で叩くキュー。
CREATE TABLE IF NOT EXISTS jobs (
  id          BIGSERIAL PRIMARY KEY,
  queue       VARCHAR(64) NOT NULL,
  type        VARCHAR(64) NOT NULL,
  payload     JSONB NOT NULL,
  state       VARCHAR(16) NOT NULL DEFAULT 'queued',
  attempts    INTEGER NOT NULL DEFAULT 0,
  run_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  locked_at   TIMESTAMP WITH TIME ZONE,
  locked_by   VARCHAR(128),
  last_error  VARCHAR,
  result      JSONB,
  created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_jobs_queue_state_run_at ON jobs(queue, state, run_at);

-- submissions: 解答送信 + 採点結果の台帳 (R1-5)。Worker (grading) が
-- pending → graded / failed を UPDATE する。Backend は INSERT と read のみ。
CREATE TABLE IF NOT EXISTS submissions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  problem_id  UUID NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
  code        VARCHAR NOT NULL,
  status      VARCHAR(16) NOT NULL DEFAULT 'pending',
  result      JSONB,
  score       INTEGER,
  created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  graded_at   TIMESTAMP WITH TIME ZONE,
  deleted_at  TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_submissions_user_id_created_at_active
  ON submissions(user_id, created_at DESC)
  WHERE deleted_at IS NULL;

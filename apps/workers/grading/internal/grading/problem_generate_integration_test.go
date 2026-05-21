//go:build integration

// problem_generate_integration_test.go: problemGenerateHandler.Handle の
// end-to-end 経路を実 Postgres + pgGenerationStore で検証する。
//
// 単体テスト (problem_generate_test.go) は fake store で sentinel を仕込んで
// 「handler が sentinel を見て nil を返す」を pin するが、本ファイルは
// 「実 DB の DELETE → real pgGenerationStore → handler 出力」の rule-out が
// 目的（issue #83）。fake が prod の挙動を正しく模擬していたか、real path で
// 検証する責務分離。
package grading

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/jobtypes"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/judge"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/sandbox"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/testsupport"
)

// neverCalledGenerator / neverCalledSandbox / neverCalledJudge:
// 呼ばれたら即 t.Fatal。Handle が短絡経路を通って「LLM / sandbox / judge を
// 呼ばないこと」を構造的に保証する（呼ばれた瞬間にテスト失敗）。
type neverCalledGenerator struct{ t *testing.T }

func (g *neverCalledGenerator) Generate(_ context.Context, _, _ string) (*ProblemDraft, error) {
	g.t.Fatal("LLM generator must not be called when generation_request is vanished")
	return nil, nil
}

type neverCalledSandbox struct{ t *testing.T }

func (s *neverCalledSandbox) Run(_ context.Context, _ []sandbox.FileSource, _ []string) (*sandbox.Result, error) {
	s.t.Fatal("sandbox must not be called when generation_request is vanished")
	return nil, nil
}

type neverCalledJudge struct{ t *testing.T }

func (j *neverCalledJudge) Evaluate(_ context.Context, _ string) (*judge.Result, error) {
	j.t.Fatal("judge must not be called when generation_request is vanished")
	return nil, nil
}

// makeJobForRequest: integration test 用に、指定 requestID を payload に持つ
// problem.generate ジョブを組み立てる。makeJob (unit test 側) は requestID を
// uuid.NewString() で勝手に振ってしまうため、本テストでは別 helper を持つ。
func makeJobForRequest(t *testing.T, requestID string) *job.Job {
	t.Helper()
	payload, err := json.Marshal(jobtypes.ProblemGenerationJobPayload{
		GenerationRequestID: requestID,
		Category:            "array",
		Difficulty:          "easy",
	})
	require.NoError(t, err)
	return &job.Job{ID: 1, Queue: job.GenerationQueue, Type: job.TypeProblemGenerate, Payload: payload, Attempts: 1}
}

// TestHandle_Integration_EntryVanishedReturnsNilWithRealStore:
// issue #83 の主動機（E2E /_test/reset レース）を実 DB で直接再現する。
//
// 流れ：
//  1. generation_requests に pending 行を INSERT
//  2. その行を DELETE（reset レースを模擬）
//  3. real pgGenerationStore を持つ handler で Handle を呼ぶ
//  4. Handle は LLM / sandbox / judge を呼ばずに nil を返すことを assert
//  5. problems テーブルにも新規行が作られていないことを assert
//
// unit test では fakeStore が pgx.ErrNoRows を返すように仕込まれていたため、
// 「real pgGenerationStore.SelectStatus が DELETE 済み行に対して pgx.ErrNoRows を
// 返す」契約は pin されていなかった。本テストでその契約も同時に固定する。
func TestHandle_Integration_EntryVanishedReturnsNilWithRealStore(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	userID := testsupport.InsertTestUser(t, pool)
	reqID := insertGenerationRequest(t, ctx, pool, userID)

	// 行 DELETE で reset レース / 管理画面削除 / GDPR 削除 を模擬。
	_, err := pool.Exec(ctx, `DELETE FROM generation_requests WHERE id = $1`, reqID)
	require.NoError(t, err)

	// 事前 problems 件数（後で 1 件も増えていないことを確認するため）。
	var problemsBefore int
	require.NoError(t, pool.QueryRow(ctx, `SELECT COUNT(*) FROM problems`).Scan(&problemsBefore))

	h := &problemGenerateHandler{
		store: newPgGenerationStore(pool),
		// 呼ばれてはいけない依存を「呼ばれたら Fatal」な fake に差す。
		generator: &neverCalledGenerator{t: t},
		sandbox:   &neverCalledSandbox{t: t},
		judge:     &neverCalledJudge{t: t},
	}

	j := makeJobForRequest(t, reqID.String())
	err = h.Handle(ctx, j)
	require.NoError(t, err, "vanished row は INFO + nil 返却で MarkSucceeded に倒すべき")

	// problems が増えていない（孤児 problem が残らない）。
	var problemsAfter int
	require.NoError(t, pool.QueryRow(ctx, `SELECT COUNT(*) FROM problems`).Scan(&problemsAfter))
	assert.Equal(t, problemsBefore, problemsAfter, "vanished row 経路では problems を作ってはいけない")
}

// 注：OnDead の vanished swallow 経路の integration test は意図的に置かない。
// 以下 2 層で十分カバーされているため：
//   - 単体（problem_generate_test.go の TestOnDead_VanishedSwallowsAsInfo）
//     fakeStore が ErrGenerationRequestVanished を返した時に handler が
//     panic せず INFO 経路を通ることを pin
//   - SQL（repository_integration_test.go の
//     TestMarkGenerationRequestFailed_VanishedReturnsSentinel）
//     実 Postgres で行不在時に markGenerationRequestFailed が sentinel を
//     wrap して返すことを pin
//
// 統合 (handler → real pgGenerationStore.MarkFailed → DB) を別に重ねると、
// 現状の testsupport/schema.sql が Alembic の最新 (failure_reason / completed_at /
// progress_step / attempt_errors 等) を追随していない関係で、UPDATE が
// "column does not exist" で先に倒れて vanished path を通らないため、
// 「通っているように見えて実は別経路」という偽陽性が出る。schema.sql の
// 整備は本 PR スコープ外（別 issue 起票推奨）。

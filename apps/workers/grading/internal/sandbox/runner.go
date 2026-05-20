// Package sandbox: 使い捨て Docker コンテナで TypeScript コードを実行する。
//
// 採点 (受験者の解答実行) と生成検証 (模範解答実行) で同じ image を起動する
// (apps/workers/grading/sandbox/Dockerfile が SSoT、ADR 0040)。
//
// 強制制約 (worker.md §採点コンテナの制約):
//   - --network none: ネット遮断
//   - --memory 256m / --cpus 0.5
//   - --read-only + --tmpfs /tmp:rw,size=64m
//   - --user 1000:1000 (非 root)
//   - 実行タイムアウト (既定 5 秒) は Runner.timeout
//
// 設計:
//   - 1 ジョブ 1 コンテナ、終わったら必ず Remove (defer + recover で漏れ防止)
//   - DooD: ホストの Docker daemon を /var/run/docker.sock 経由で叩く
//     (ADR 0045、DinD は使わない)
//   - ソースは host の tmp ディレクトリに書き出して bind mount (read-only)
package sandbox

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"time"

	// moby/moby に移行: github.com/docker/docker/* は GO-2026-4887 / 4883
	// (AuthZ plugin 関連、全バージョン未修正) を踏むため、fix 反映済みの
	// github.com/moby/moby/* (client v0.x / api v1.x) を使う。
	// API 互換 (NewClientWithOpts / ContainerCreate 等は同 signature)。
	"github.com/moby/moby/api/pkg/stdcopy"
	"github.com/moby/moby/api/types/container"
	"github.com/moby/moby/api/types/mount"
	"github.com/moby/moby/api/types/network"
	"github.com/moby/moby/client"
)

// sandboxPidsLimit: コンテナあたりの PID 上限。
// LLM が生成するコードを信用しない方針に従い、`fork()` を無制限に繰り返す
// プロセスでホストの PID テーブルを食い潰される事故を防ぐ。Vitest 1 ファイル
// 実行に必要なプロセス数 (node 本体 + tsx loader + 数個の child) を踏まえて
// 余裕を持って 128 に置く。--read-only / --network none / --memory 等と
// 並ぶ強制制約の 1 つ (.claude/rules/worker.md「採点コンテナの制約」)。
const sandboxPidsLimit int64 = 128

// ptrInt64: int64 から *int64 を作る薄い helper。
// container.Resources.PidsLimit が *int64 を要求 (nil = 制限なし、値あり = 上限)
// のため、定数 sandboxPidsLimit のアドレスを直接渡せず変換ヘルパを挟む。
func ptrInt64(v int64) *int64 { return &v }

// FileSource: コンテナにマウントする 1 ファイル。
// Name は /sandbox/ 配下に置かれるファイル名 (e.g. "solution.ts")。
// パスセパレータは含めない (相対サブディレクトリは禁止)。
type FileSource struct {
	Name    string
	Content string
}

// Result: 1 回のコンテナ実行結果。
type Result struct {
	ExitCode int
	Stdout   string
	Stderr   string
	// TimedOut: Runner.timeout で打ち切った場合 true。
	// false で ExitCode != 0 は「コードが Exit 0 以外で終了した」(テスト失敗 / 例外)。
	TimedOut bool
	// Duration: コンテナ実行に要した時間 (Stat/Logs 取得は除く)。観測ログ用。
	Duration time.Duration
}

// Runner: Docker client + 共通設定を保持し、Run で 1 回の実行を行う。
type Runner struct {
	cli     *client.Client
	image   string
	timeout time.Duration
}

// Options: Runner 生成パラメータ。Image / Timeout は必須。
type Options struct {
	Image   string
	Timeout time.Duration
}

// NewRunner: Docker daemon に繋いで Runner を組み立てる。
//
// Docker daemon に繋げない場合 (=ローカルで daemon 未起動) は ConfigErr を返す。
// Worker 起動時に fail-fast する想定。
func NewRunner(opts Options) (*Runner, error) {
	if opts.Image == "" {
		return nil, fmt.Errorf("sandbox: empty image name")
	}
	if opts.Timeout <= 0 {
		return nil, fmt.Errorf("sandbox: timeout must be > 0 (got %s)", opts.Timeout)
	}
	// moby/client v0.4: NewClientWithOpts は deprecated、New に置換 (go:fix inline 指示)。
	// WithAPIVersionNegotiation は v0.4 で既定 ON の no-op deprecated になったため不要。
	cli, err := client.New(client.FromEnv)
	if err != nil {
		return nil, fmt.Errorf("sandbox: docker client: %w", err)
	}
	return &Runner{cli: cli, image: opts.Image, timeout: opts.Timeout}, nil
}

// Close: Docker client を閉じる。
func (r *Runner) Close() error {
	return r.cli.Close()
}

// Run: ファイル群をマウントしたコンテナで cmd を実行し結果を返す。
//
// 流れ:
//  1. host tmp dir を作成して FileSource を全て書き出す
//  2. ContainerCreate (隔離設定 + bind mount, 読み取り専用)
//  3. ContainerStart + ContainerWait (timeout 付き ctx)
//  4. ContainerLogs で stdout / stderr を回収
//  5. ContainerRemove で必ず後片付け
//
// 戻り値:
//   - Result: 正常実行 (ExitCode 含む)。TimedOut=true なら timeout 打ち切り
//   - error : Docker API エラー or ファイル書き出し失敗 (= 環境問題)
//
// 重要: 「Exit 0 以外」は error として返さない。テスト失敗は Result.ExitCode != 0
// として正常に取得できるべき (orchestrator が判断する)。
func (r *Runner) Run(ctx context.Context, files []FileSource, cmd []string) (*Result, error) {
	if len(files) == 0 {
		return nil, fmt.Errorf("sandbox: no files to mount")
	}
	if len(cmd) == 0 {
		return nil, fmt.Errorf("sandbox: empty cmd")
	}

	hostDir, err := r.writeFiles(files)
	if err != nil {
		return nil, err
	}
	// host tmp は実行後必ず削除する (定期清掃に頼らない)。
	defer func() {
		if rmErr := os.RemoveAll(hostDir); rmErr != nil {
			slog.WarnContext(ctx, "sandbox: failed to remove host tmp dir", "dir", hostDir, "err", rmErr)
		}
	}()

	runCtx, cancel := context.WithTimeout(ctx, r.timeout)
	defer cancel()

	createResp, err := r.cli.ContainerCreate(runCtx, client.ContainerCreateOptions{
		Config: &container.Config{
			Image:        r.image,
			Cmd:          cmd,
			Tty:          false,
			AttachStdout: true,
			AttachStderr: true,
			WorkingDir:   "/sandbox",
			// Entrypoint を空 slice で上書きする: Dockerfile の ENTRYPOINT ["tsx"] を
			// 無効化して cmd の先頭が直接 exec される (vitest 等を実行するため)。
			Entrypoint: []string{},
			// uid 1000 (node ユーザ) で起動。ホスト側 hostDir はそのまま 1000 でも
			// 読み取れる権限で書く (os.WriteFile 0644)。
			User: "1000:1000",
		},
		HostConfig: &container.HostConfig{
			// network.NetworkNone = "none": 完全ネット遮断。文字列直書きより型 safety。
			NetworkMode: container.NetworkMode(network.NetworkNone),
			Resources: container.Resources{
				Memory:    256 * 1024 * 1024,          //nolint:mnd // 256 MiB (worker.md SSoT)
				NanoCPUs:  500_000_000,                //nolint:mnd // 0.5 CPU (worker.md SSoT)
				PidsLimit: ptrInt64(sandboxPidsLimit), // fork 爆弾耐性 (LLM 生成コードを信用しない哲学)
			},
			ReadonlyRootfs: true,
			Tmpfs: map[string]string{
				"/tmp": "rw,size=64m",
			},
			AutoRemove: false, // 後で Logs を回収するため Remove は手動
			Mounts: []mount.Mount{
				{
					Type:     mount.TypeBind,
					Source:   hostDir,
					Target:   "/sandbox",
					ReadOnly: true,
				},
			},
		},
	})
	if err != nil {
		return nil, fmt.Errorf("sandbox: container create: %w", err)
	}
	containerID := createResp.ID
	defer func() {
		// AutoRemove=false なので明示的に Remove。残骸を残さない。
		removeCtx, removeCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer removeCancel()
		_, _ = r.cli.ContainerRemove(removeCtx, containerID, client.ContainerRemoveOptions{Force: true})
	}()

	start := time.Now()
	if _, err := r.cli.ContainerStart(runCtx, containerID, client.ContainerStartOptions{}); err != nil {
		return nil, fmt.Errorf("sandbox: container start: %w", err)
	}

	waitRes := r.cli.ContainerWait(runCtx, containerID, client.ContainerWaitOptions{Condition: container.WaitConditionNotRunning})
	var (
		exitCode int64
		timedOut bool
	)
	select {
	case <-runCtx.Done():
		// timeout / cancel: 強制停止して logs だけ回収する。
		timedOut = errors.Is(runCtx.Err(), context.DeadlineExceeded)
		stopCtx, stopCancel := context.WithTimeout(context.Background(), 5*time.Second)
		_, _ = r.cli.ContainerStop(stopCtx, containerID, client.ContainerStopOptions{})
		stopCancel()
		exitCode = -1
	case err := <-waitRes.Error:
		if err != nil {
			return nil, fmt.Errorf("sandbox: container wait: %w", err)
		}
	case status := <-waitRes.Result:
		exitCode = status.StatusCode
	}
	duration := time.Since(start)

	stdout, stderr, err := r.collectLogs(ctx, containerID)
	if err != nil {
		return nil, fmt.Errorf("sandbox: collect logs: %w", err)
	}

	return &Result{
		ExitCode: int(exitCode),
		Stdout:   stdout,
		Stderr:   stderr,
		TimedOut: timedOut,
		Duration: duration,
	}, nil
}

// writeFiles: host の tmp dir を 1 個作って FileSource を全部書き出す。
// 戻り値は dir path。呼び出し側が defer os.RemoveAll する。
func (r *Runner) writeFiles(files []FileSource) (string, error) {
	dir, err := os.MkdirTemp("", "ai-coding-drill-sandbox-*")
	if err != nil {
		return "", fmt.Errorf("sandbox: mktmp: %w", err)
	}
	// 0755 にしないと container 内の uid 1000 が読み込めない。
	if err := os.Chmod(dir, 0o755); err != nil { //nolint:gosec // container 内 uid 1000 から読む必要があり、対象は使い捨て tmp dir のみ
		_ = os.RemoveAll(dir)
		return "", fmt.Errorf("sandbox: chmod tmp dir: %w", err)
	}
	for _, f := range files {
		if filepath.Base(f.Name) != f.Name {
			_ = os.RemoveAll(dir)
			return "", fmt.Errorf("sandbox: file name must not contain path separator: %q", f.Name)
		}
		full := filepath.Join(dir, f.Name)
		if err := os.WriteFile(full, []byte(f.Content), 0o644); err != nil { //nolint:gosec // sandbox 入力、外部読まれて問題ない
			_ = os.RemoveAll(dir)
			return "", fmt.Errorf("sandbox: write %s: %w", f.Name, err)
		}
	}
	return dir, nil
}

// collectLogs: コンテナの stdout / stderr を取得する。
// Docker API は両者を多重化したストリームで返すため stdcopy.StdCopy で分離する。
func (r *Runner) collectLogs(ctx context.Context, containerID string) (string, string, error) {
	logsCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	reader, err := r.cli.ContainerLogs(logsCtx, containerID, client.ContainerLogsOptions{
		ShowStdout: true,
		ShowStderr: true,
	})
	if err != nil {
		return "", "", err
	}
	defer func() { _ = reader.Close() }()
	var stdout, stderr bytes.Buffer
	if _, err := stdcopy.StdCopy(&stdout, &stderr, reader); err != nil && !errors.Is(err, io.EOF) {
		return "", "", err
	}
	return stdout.String(), stderr.String(), nil
}

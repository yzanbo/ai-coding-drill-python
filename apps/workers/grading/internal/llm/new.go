package llm

// new.go: 設定から Provider 実装を組み立てるファクトリ。
//
// R1-2 skeleton 段階では各 provider sub-package が未実装のため、
// New は ErrNotImplemented を返す。初期モデル選定 ADR (0049) で
// 第一プロバイダが確定したら、対応する sub-package を import して
// switch ケースを実装で埋める。
//
// 設計意図:
//   - cmd/grading/main.go から `llm.New(cfg)` だけで Provider を取れる形にする
//     (worker.md「OK コード例」の DI 起点)。
//   - 役割ごとに別 Provider を返すのではなく、単一 Provider が opts.Role
//     相当の情報を Options 経由で受け取る前提。役割ごとにモデルを切替える
//     ロジックは Provider の実装内で RoleConfigFor を引いて行う。

// New: Config から Provider 実装を返すファクトリ。
//
// R1-2 skeleton ではまだどの provider 実装も配線されていないので
// ErrNotImplemented を返す。初期モデル選定 ADR 確定後に
// switch cfg.Generation.Provider { case "anthropic": ...} のような形で
// 実装に差し替える。
func New(_ Config) (Provider, error) {
	return nil, ErrNotImplemented
}

package llm

// new.go: Provider 実装を Config から組み立てるファクトリ + プロバイダ登録 API。
//
// 設計意図 (循環インポート回避):
//   - llm package は Provider interface と型のみを公開する Layer 0 / leaf
//   - 各 provider sub-package (internal/llm/<provider>/) は llm package を
//     import して Provider を実装する
//   - llm が google/anthropic 等を直接 import すると Go の import cycle で
//     コンパイル不可になるため、main が ProviderFactory を Register して
//     llm.New が登録 map から引く形にする
//   - 標準ライブラリの database/sql / image/png / encoding/gob と同じ
//     registration pattern
//
// Register / New の使い方は cmd/grading/main.go と
// ../../../.claude/rules/worker.md の OK 例を参照。

import (
	// errors: ErrUnknownProvider の sentinel 定義に使う。
	// fmt:    Provider 名 / 詳細メッセージを wrap して投げる。
	// sync:   Register と New が並行に呼ばれた場合の map 競合保護。
	//         実際は main で goroutine 起動前に Register、その後 New 連発という
	//         流れだが、テストや R2 でロール別 provider を register する時に
	//         並行になっても安全であるよう RWMutex を被せる
	//         (database/sql.Register と同じ)。
	"errors"
	"fmt"
	"sync"
)

// ProviderFactory: Config から Provider を組み立てる関数の型。
// 各プロバイダ sub-package は `func New(cfg llm.Config) (llm.Provider, error)`
// として実装し、main から llm.Register(name, sub.New) で登録する。
type ProviderFactory func(Config) (Provider, error)

// ErrUnknownProvider: Config.Generation.Provider に対応する factory が
// Register されていない時に New が返す sentinel。
// 設定ミス (llm.yaml のタイポ) もしくは main で sub-package を
// import + Register し忘れた時に発火する。
var ErrUnknownProvider = errors.New("llm: provider not registered")

var (
	providerMu        sync.RWMutex
	providerFactories = map[string]ProviderFactory{}
)

// Register: プロバイダ sub-package のファクトリを名前付きで登録する。
//
// 想定呼び出し場所: cmd/<worker>/main.go (goroutine 起動前)。
//
// 同名で二重 Register された場合は後勝ち。テストで fake provider を
// 差し込む / R2 でモデル A/B 切替を検証する用途を見越して許容する。
func Register(name string, factory ProviderFactory) {
	providerMu.Lock()
	defer providerMu.Unlock()
	providerFactories[name] = factory
}

// New: Config から Provider 実装を返すファクトリ。
//
// Config.Generation.Provider の値で Register 済の factory を引いて呼び出す。
// MVP では generation / regeneration / judge すべて同一プロバイダ
// (ADR 0049 で Gemini 単独) のため、Generation.Provider 1 つで判定する。
// R2 でロール別プロバイダに分岐する場合は、戻り値を「ロール別 Provider を
// 多重化したラッパ」に拡張するか、呼び出し側で 3 回 New を呼ぶ。
//
// 未登録プロバイダ / Provider 名空文字は ErrUnknownProvider を wrap して返す。
func New(cfg Config) (Provider, error) {
	name := cfg.Generation.Provider
	if name == "" {
		return nil, fmt.Errorf("llm: empty Config.Generation.Provider: %w", ErrUnknownProvider)
	}
	providerMu.RLock()
	factory, ok := providerFactories[name]
	providerMu.RUnlock()
	if !ok {
		return nil, fmt.Errorf("llm: %q is not registered (Register from main): %w", name, ErrUnknownProvider)
	}
	return factory(cfg)
}

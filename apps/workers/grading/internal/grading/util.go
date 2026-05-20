// util.go: 本 package 内のローカルヘルパ。
//
// jsonUnmarshal / parseUUID は orchestrator.go の error 経路で payload を
// 部分的に読みたいケースに使う。標準 lib 直叩きでもよいが、テストで差し替え
// たくなった時のフックを残しておく。
package grading

import (
	"encoding/json"

	"github.com/google/uuid"
)

// jsonUnmarshal: encoding/json.Unmarshal の薄いラッパ。
func jsonUnmarshal(data []byte, v any) error {
	return json.Unmarshal(data, v)
}

// parseUUID: uuid.Parse の薄いラッパ。
func parseUUID(s string) (uuid.UUID, error) {
	return uuid.Parse(s)
}

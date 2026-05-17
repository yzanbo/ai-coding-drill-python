// extractApiErrorMessage の単体テスト。
//   FastAPI が返す代表的なエラーボディ（detail 文字列 / detail 配列）と、
//   status だけで判定する場合のフォールバック分岐をすべて検証する。
import { describe, expect, it } from "vitest";

import { extractApiErrorMessage } from "./extract-api-error-message";

describe("extractApiErrorMessage", () => {
  describe("status 不明（fetch 失敗・ネットワーク断）", () => {
    it("status=undefined は通信失敗メッセージ", () => {
      expect(extractApiErrorMessage(undefined, undefined)).toBe(
        "通信に失敗しました。しばらく経ってから再度お試しください。",
      );
    });

    it("status=0 も通信失敗メッセージ", () => {
      expect(extractApiErrorMessage(0, undefined)).toBe(
        "通信に失敗しました。しばらく経ってから再度お試しください。",
      );
    });
  });

  describe("detail を優先して採用する", () => {
    it("detail が文字列ならそのまま返す（HTTPException 形式）", () => {
      expect(extractApiErrorMessage(400, { detail: "認証情報が不正です" })).toBe(
        "認証情報が不正です",
      );
    });

    it("detail が配列なら先頭要素の msg を返す（バリデーションエラー形式）", () => {
      expect(
        extractApiErrorMessage(422, {
          detail: [{ msg: "メールアドレスの形式が不正です" }, { msg: "別エラー" }],
        }),
      ).toBe("メールアドレスの形式が不正です");
    });

    it("detail が空文字列なら status 別フォールバックに流れる", () => {
      expect(extractApiErrorMessage(401, { detail: "" })).toBe("ログインが必要です。");
    });

    it("detail が空配列なら status 別フォールバックに流れる", () => {
      expect(extractApiErrorMessage(404, { detail: [] })).toBe("対象が見つかりません。");
    });

    it("detail 配列の先頭に msg が無いなら status 別フォールバックに流れる", () => {
      expect(extractApiErrorMessage(500, { detail: [{}] })).toBe(
        "サーバーでエラーが発生しました。",
      );
    });

    it("detail 配列の先頭 msg が空文字でも status 別フォールバックに流れる", () => {
      expect(extractApiErrorMessage(403, { detail: [{ msg: "" }] })).toBe(
        "この操作を実行する権限がありません。",
      );
    });
  });

  describe("status 別フォールバック（detail 無し / 不明形式の body）", () => {
    it("401 → ログインが必要", () => {
      expect(extractApiErrorMessage(401, undefined)).toBe("ログインが必要です。");
    });

    it("403 → 権限なし", () => {
      expect(extractApiErrorMessage(403, undefined)).toBe("この操作を実行する権限がありません。");
    });

    it("404 → 対象が見つからない", () => {
      expect(extractApiErrorMessage(404, undefined)).toBe("対象が見つかりません。");
    });

    it("500 系 → サーバーエラー", () => {
      expect(extractApiErrorMessage(500, undefined)).toBe("サーバーでエラーが発生しました。");
      expect(extractApiErrorMessage(503, undefined)).toBe("サーバーでエラーが発生しました。");
    });

    it("該当ステータスなしの 4xx → 汎用エラー", () => {
      expect(extractApiErrorMessage(418, undefined)).toBe("エラーが発生しました。");
    });

    it("body が不明な形（文字列・null）でも status 別フォールバックに流れる", () => {
      expect(extractApiErrorMessage(401, "raw text")).toBe("ログインが必要です。");
      expect(extractApiErrorMessage(401, null)).toBe("ログインが必要です。");
    });
  });
});

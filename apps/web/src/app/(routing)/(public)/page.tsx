// / : ルートへのアクセスは /problems に常時リダイレクトする。
//   - 認証要否に関わらず一律で /problems へ送る（/problems はゲスト閲覧可）。
//   - ランディングページは MVP では不要との判断（主動線は問題一覧から始まる）。
//   - Server Component で redirect() を呼ぶことで、クライアント JS を待たずに
//     ネットワーク層で 307 リダイレクトが返り、Cookie 状態に依存しない。

import { redirect } from "next/navigation";

export default function RootRedirectPage() {
  redirect("/problems");
}

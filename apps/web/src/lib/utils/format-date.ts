// format-date: ISO 8601 文字列を "YYYY/MM/DD HH:mm" に整形する共通ヘルパ。
//
//   - タイムゾーン：ブラウザのローカル（getMonth() / getHours() を使う）。
//     UTC のまま表示する用途は別 helper を切る方針（現状は不要なので置かない）。
//   - 不正値（null / undefined / parse 失敗）は固定で "—" を返す。
//     縦並び一覧で「日時欄が空」のレイアウト崩れを避けるための placeholder。
//   - 2 桁ゼロ埋め：String(n).padStart(2, "0")。1 桁の月日時分が混在して
//     縦並びの列幅が揺れるのを防ぐ。
//
//   使用箇所：/me/history, /me/generations 等の履歴系一覧
//   （秒精度が要る画面で本 helper を使うと「秒の刻みが見えない」になる点に注意。
//    秒精度が必要なら別 helper を切る。「YYYY/MM/DD HH:mm」固定であることが
//    本 helper の契約）。

export const formatDate = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${yyyy}/${mm}/${dd} ${hh}:${mi}`;
};

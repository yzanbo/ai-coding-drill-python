"""DB スキーマのドキュメント（ER 図 + テーブル別カラム表）の HTML を組み立てる。

- 入力：SQLAlchemy モデル（app.models）= スキーマの唯一の正（SSoT）
- 出力：ブラウザ表示用 HTML（GET /dev/erd が返す、routers/erd.py）
- DB 接続・外部サービスは不要（モデル定義の metadata だけ読む）

各カラムに表示する 3 つの名前・説明：
  - 物理名：column.name（例 user_id）
  - 論理名：mapped_column(info={"label": "送信ユーザー"}) の info["label"]（短い日本語名）
  - 用途  ：mapped_column(comment="...") の comment（説明文。DB の COMMENT にも伝播）

metadata から毎リクエスト生成するので、モデルを変えれば /dev/erd も即座に最新が映る。
"""

import html

from sqlalchemy import Column, Table

# app.models を import すると全モデルが Base.metadata に登録される
# （models/__init__.py が全テーブルを re-export しているため）。
import app.models  # noqa: F401  (副作用 import：metadata 登録のため)
from app.db.base import Base


def _logical_name(column: Column) -> str:
    """論理名（人が読む短い日本語名）。mapped_column(info={"label": ...}) が SSoT。"""
    label = column.info.get("label", "")
    return str(label) if label else ""


def _key_marker(column: Column) -> str:
    """主キー（PK）/ 外部キー（FK）の印。"""
    markers = []
    if column.primary_key:
        markers.append("PK")
    if column.foreign_keys:
        markers.append("FK")
    return ",".join(markers)


def _mermaid_type(column: Column) -> str:
    """Mermaid 属性用に型名を英数字 1 語へ整形（VARCHAR(16) → VARCHAR16）。"""
    raw = type(column.type).__name__
    return "".join(ch for ch in raw if ch.isalnum()) or "unknown"


def _server_default(column: Column) -> str:
    """server_default を読みやすい文字列にする（無ければ空）。"""
    default = column.server_default
    if default is None:
        return ""
    arg = getattr(default, "arg", default)
    return str(getattr(arg, "text", arg))


def _sorted_tables() -> list[Table]:
    """外部キー依存順（親→子）に並んだ全テーブル。"""
    return list(Base.metadata.sorted_tables)


def build_mermaid(tables: list[Table]) -> str:
    """Mermaid の erDiagram テキストを組み立てる。"""
    lines = ["erDiagram"]

    # 各テーブルを箱で描く（型・物理名・PK/FK 印・論理名コメント）。
    #   Mermaid 属性は `型 名前 キー "コメント"` の順。論理名を末尾コメントに出す。
    for table in tables:
        lines.append(f"  {table.name} {{")
        for column in table.columns:
            attr = f"    {_mermaid_type(column)} {column.name}"
            marker = _key_marker(column)
            if marker:
                attr += f" {marker}"
            logical = _logical_name(column)
            if logical:
                # 引用符内の " は崩れ防止に除去。
                attr += f' "{logical.replace(chr(34), "")}"'
            lines.append(attr)
        lines.append("  }")

    # 外部キーから関連線を引く（親 1 - 子 多）。
    #   子 FK が非 NULL なら「ちょうど 1」、NULL 可なら「0 or 1」。
    for table in tables:
        for column in table.columns:
            for fk in column.foreign_keys:
                parent = fk.column.table.name
                child = table.name
                left = "||" if not column.nullable else "|o"
                lines.append(f'  {parent} {left}--o{{ {child} : "{column.name}"')

    return "\n".join(lines)


def _column_rows(table: Table) -> list[dict[str, str]]:
    """1 テーブルのカラム行（物理名・論理名・型・NULL・デフォルト・キー・用途）。"""
    rows = []
    for column in table.columns:
        rows.append(
            {
                "physical": column.name,
                "logical": _logical_name(column),
                "type": str(column.type),
                "nullable": "可" if column.nullable else "—",
                "default": _server_default(column),
                "key": _key_marker(column),
                "comment": column.comment or "",
            }
        )
    return rows


def _table_html(table: Table) -> str:
    """1 テーブル分の HTML（見出し + カラム表）。"""
    head = (
        "<tr><th>物理名</th><th>論理名</th><th>型</th>"
        "<th>NULL</th><th>デフォルト</th><th>キー</th><th>用途</th></tr>"
    )
    body_rows = []
    for r in _column_rows(table):
        default = f"<code>{html.escape(r['default'])}</code>" if r["default"] else ""
        body_rows.append(
            "<tr>"
            f"<td><code>{html.escape(r['physical'])}</code></td>"
            f"<td>{html.escape(r['logical'])}</td>"
            f"<td>{html.escape(r['type'])}</td>"
            f"<td>{r['nullable']}</td>"
            f"<td>{default}</td>"
            f"<td>{html.escape(r['key'])}</td>"
            f"<td>{html.escape(r['comment'])}</td>"
            "</tr>"
        )
    return (
        f'<h3 id="{html.escape(table.name)}">{html.escape(table.name)}</h3>'
        f"<table>{head}{''.join(body_rows)}</table>"
    )


def render_html() -> str:
    """GET /dev/erd が返す HTML 全文。Mermaid.js（CDN）で ER 図を描画する。"""
    tables = _sorted_tables()
    mermaid_src = html.escape(build_mermaid(tables))
    tables_html = "".join(_table_html(t) for t in tables)
    # 目次（テーブル名のアンカーリンク）。
    toc = " · ".join(f'<a href="#{html.escape(t.name)}">{html.escape(t.name)}</a>' for t in tables)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>DB スキーマ（ER 図）| AI Coding Drill</title>
<style>
  body {{ font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", Meiryo, sans-serif;
    margin: 0; padding: 2rem clamp(1rem, 4vw, 4rem); background: #0f172a; color: #e2e8f0; }}
  h1 {{ font-size: 1.6rem; }}
  h2 {{ margin-top: 2.5rem; border-left: 5px solid #38bdf8; padding-left: .6rem; }}
  h3 {{ margin-top: 2rem; color: #38bdf8; }}
  .note {{ color: #94a3b8; font-size: .9rem; }}
  .toc {{ color: #94a3b8; font-size: .85rem; line-height: 1.9; }}
  .toc a, a {{ color: #7dd3fc; text-decoration: none; }}
  .mermaid {{ background: #0b1220; border: 1px solid #1e293b; border-radius: 10px;
    padding: 1rem; overflow-x: auto; }}
  table {{ border-collapse: collapse; width: 100%; margin: .5rem 0 1.5rem; font-size: .9rem; }}
  th, td {{ border: 1px solid #1e293b; padding: 6px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #1e293b; color: #38bdf8; }}
  code {{ background: rgba(255,255,255,.08); padding: 1px 6px; border-radius: 5px; }}
</style>
</head>
<body>
  <h1>DB スキーマ（ER 図 + 物理名 / 論理名）</h1>
  <p class="note">SQLAlchemy モデル（SSoT）から自動生成。モデルを変えれば即更新。</p>
  <h2>ER 図</h2>
  <pre class="mermaid">{mermaid_src}</pre>
  <h2>テーブル別カラム一覧</h2>
  <p class="toc">{toc}</p>
  {tables_html}
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "dark" }});
  </script>
</body>
</html>
"""

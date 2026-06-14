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
from enum import StrEnum
from typing import get_args

from sqlalchemy import Column, Index, Table, UniqueConstraint

# app.models を import すると全モデルが Base.metadata に登録される
# （models/__init__.py が全テーブルを re-export しているため）。
import app.models  # noqa: F401  (副作用 import：metadata 登録のため)

# 列の「取りうる値（選択肢）」を表示するため、その SSoT である enum / Literal を読み込む。
#   docs.py は本来 DB 層だが、ER 図を描く dev ツールなので schemas を参照する例外とする
#   （/dev/erd が本番非公開・読み取り専用なのと同じ位置づけ）。
from app.core.enums import JobQueue, JobState, JobType, Provider
from app.db.base import Base
from app.schemas.me_generations import FailureReasonTag, ProgressStep
from app.schemas.problems import GenerationStatus, ProblemCategory, ProblemDifficulty
from app.schemas.submissions import SubmissionStatus


def _enum_values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    """StrEnum のメンバ値を定義順のタプルで返す。"""
    return tuple(str(member.value) for member in enum_cls)


# _COLUMN_CHOICES: (テーブル名, カラム名) → 取りうる値のタプル。
#   値の SSoT は各 enum / Literal（ここで重複定義はしない）。/dev/erd の用途欄に出す。
_COLUMN_CHOICES: dict[tuple[str, str], tuple[str, ...]] = {
    ("auth_providers", "provider"): _enum_values(Provider),
    ("problems", "category"): _enum_values(ProblemCategory),
    ("problems", "difficulty"): _enum_values(ProblemDifficulty),
    ("submissions", "status"): _enum_values(SubmissionStatus),
    ("generation_requests", "category"): _enum_values(ProblemCategory),
    ("generation_requests", "difficulty"): _enum_values(ProblemDifficulty),
    ("generation_requests", "status"): _enum_values(GenerationStatus),
    ("generation_requests", "failure_reason"): get_args(FailureReasonTag),
    ("generation_requests", "progress_step"): get_args(ProgressStep),
    ("jobs", "state"): _enum_values(JobState),
    ("jobs", "type"): _enum_values(JobType),
    ("jobs", "queue"): _enum_values(JobQueue),
}

# _CHOICE_LABELS: 選択肢の値 → 日本語の短い説明（/dev/erd で「値（説明）」と出す）。
#   表示専用ラベル。値そのものの SSoT は各 enum / Literal。ここは ER 図を読む人向けの注釈。
#   値を増やしたらここにも 1 行足す（未登録なら値だけ表示され、壊れはしない）。
_CHOICE_LABELS: dict[str, str] = {
    # provider
    "github": "GitHub",
    # problems.category
    "string": "文字列",
    "array": "配列",
    "recursion": "再帰",
    "async": "非同期",
    "type-puzzle": "型パズル",
    # difficulty
    "easy": "初級",
    "medium": "中級",
    "hard": "上級",
    # submission / generation status
    "pending": "処理待ち",
    "graded": "採点済み",
    "completed": "完了",
    "failed": "失敗",
    "canceled": "キャンセル（旧仕様）",
    # generation_requests.failure_reason
    "llm_unauthorized": "LLM 認証エラー",
    "llm_cost_exceeded": "コスト上限超過",
    "judge_below_threshold": "品質スコア不足",
    "sandbox_failed": "サンドボックス検証失敗",
    "sandbox_infrastructure": "サンドボックス基盤エラー",
    "llm_invalid_output": "LLM 出力不正",
    "llm_rate_limit": "LLM レート制限",
    "llm_timeout": "LLM タイムアウト",
    "llm_schema_invalid": "LLM スキーマ違反",
    "max_attempts_exceeded": "試行上限超過",
    # generation_requests.progress_step
    "llm_generating": "問題生成中",
    "sandbox_verifying": "模範解答の検証中",
    "judging": "品質評価中",
    "persisting": "保存中",
    # jobs.state
    "queued": "投入待ち",
    "running": "処理中",
    "succeeded": "成功",
    # jobs.type
    "submission.grade": "解答の採点",
    "problem.generate": "問題の生成",
    # jobs.queue
    "grading": "採点ワーカー向け",
    "generation": "生成ワーカー向け",
}


def _format_choice(value: str) -> str:
    """選択肢を「値（日本語説明）」に整形。説明が無ければ値のみ。"""
    label = _CHOICE_LABELS.get(value)
    return f"{value}（{label}）" if label else value


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


def _index_columns(index: Index) -> list[str]:
    """インデックスの対象を定義順で返す（"created_at DESC" のような式は文字列のまま）。"""
    names = []
    for expr in index.expressions:
        name = getattr(expr, "name", None)
        names.append(str(name) if name else str(expr))
    return names


def _partial_where(index: Index) -> str:
    """部分インデックスの WHERE 条件（postgresql_where）。無ければ空。"""
    try:
        where = index.dialect_options["postgresql"]["where"]
    except KeyError, AttributeError:
        return ""
    return str(where) if where is not None else ""


def _table_indexes(table: Table) -> list[dict[str, str]]:
    """テーブルのインデックス + UNIQUE 制約（名前・対象カラム・UNIQUE・部分条件）。"""
    rows = []
    # Index オブジェクト（Index(...) や mapped_column(index=True) 由来）。
    for idx in sorted(table.indexes, key=lambda i: i.name or ""):
        rows.append(
            {
                "name": idx.name or "",
                "columns": ", ".join(_index_columns(idx)),
                "unique": "✓" if idx.unique else "",
                "where": _partial_where(idx),
            }
        )
    # UNIQUE 制約も一意インデックスとして効くので併記（PK はキー列で表示済みのため除外）。
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint) and constraint.name:
            rows.append(
                {
                    "name": constraint.name,
                    "columns": ", ".join(col.name for col in constraint.columns),
                    "unique": "✓",
                    "where": "",
                }
            )
    return rows


def _indexed_column_names(table: Table) -> set[str]:
    """いずれかのインデックス / UNIQUE 制約に含まれるカラム名の集合（カラム表の索引✓ 判定用）。"""
    colnames = {c.name for c in table.columns}
    names: set[str] = set()
    for idx in table.indexes:
        for part in _index_columns(idx):
            # "created_at DESC" のような式は先頭トークンをカラム名として拾う。
            token = part.split()[0] if part else ""
            if token in colnames:
                names.add(token)
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            for col in constraint.columns:
                names.add(col.name)
    return names


def _table_logical(table: Table) -> str:
    """テーブルの論理名（人が読む名前）。__table_args__ の info["label"] が SSoT。"""
    label = table.info.get("label", "")
    return str(label) if label else ""


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
    """1 テーブルのカラム行（物理名・論理名・型・NULL・デフォルト・キー・索引・用途）。"""
    indexed = _indexed_column_names(table)
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
                # 索引: いずれかのインデックス / UNIQUE 制約に含まれるカラムに ✓。
                #   複合インデックスの順序・部分条件はテーブル下の「インデックス」一覧で確認する。
                "indexed": "✓" if column.name in indexed else "",
                "comment": column.comment or "",
                # choices: 取りうる固定値（enum / Literal が決まっている列のみ）。
                #   用途欄に「選択肢: a / b / c」として出す。無ければ空文字。
                "choices": " / ".join(
                    _format_choice(v) for v in _COLUMN_CHOICES.get((table.name, column.name), ())
                ),
            }
        )
    return rows


def _table_html(table: Table) -> str:
    """1 テーブル分の HTML（見出し + カラム表 + インデックス一覧）。"""
    # colgroup: 列幅を % で固定。画面幅が変わっても比率が一定になり、全テーブルで列が揃う。
    colgroup = (
        '<colgroup><col style="width:15%"><col style="width:12%"><col style="width:11%">'
        '<col style="width:6%"><col style="width:13%"><col style="width:7%">'
        '<col style="width:6%"><col style="width:30%"></colgroup>'
    )
    head = (
        "<tr><th>物理名</th><th>論理名</th><th>型</th><th>NULL</th>"
        "<th>デフォルト</th><th>キー</th><th>索引</th><th>用途</th></tr>"
    )
    body_rows = []
    for r in _column_rows(table):
        default = f"<code>{html.escape(r['default'])}</code>" if r["default"] else ""
        # 用途セル = コメント + 選択肢（取りうる固定値がある列のみ）。
        use_cell = html.escape(r["comment"])
        if r["choices"]:
            use_cell += f'<div class="choices">選択肢: {html.escape(r["choices"])}</div>'
        body_rows.append(
            "<tr>"
            f"<td><code>{html.escape(r['physical'])}</code></td>"
            f"<td>{html.escape(r['logical'])}</td>"
            f"<td>{html.escape(r['type'])}</td>"
            f"<td>{r['nullable']}</td>"
            f"<td>{default}</td>"
            f"<td>{html.escape(r['key'])}</td>"
            f"<td>{r['indexed']}</td>"
            f"<td>{use_cell}</td>"
            "</tr>"
        )

    # 見出しは「物理名（論理名）」。論理名が無ければ物理名のみ。
    logical = _table_logical(table)
    heading = html.escape(table.name)
    if logical:
        heading += f"（{html.escape(logical)}）"

    # インデックス一覧：複合の順序・UNIQUE・部分条件（WHERE）まで正確に出す。
    index_html = ""
    idx_rows = _table_indexes(table)
    if idx_rows:
        idx_colgroup = (
            '<colgroup><col style="width:32%"><col style="width:34%">'
            '<col style="width:10%"><col style="width:24%"></colgroup>'
        )
        idx_head = "<tr><th>索引名</th><th>対象カラム</th><th>UNIQUE</th><th>部分条件</th></tr>"
        idx_body = []
        for r in idx_rows:
            where = f"<code>{html.escape(r['where'])}</code>" if r["where"] else ""
            idx_body.append(
                "<tr>"
                f"<td><code>{html.escape(r['name'])}</code></td>"
                f"<td>{html.escape(r['columns'])}</td>"
                f"<td>{r['unique']}</td>"
                f"<td>{where}</td>"
                "</tr>"
            )
        index_html = (
            '<p class="idx-label">インデックス</p>'
            f'<table class="idx-table">{idx_colgroup}{idx_head}{"".join(idx_body)}</table>'
        )

    return (
        f'<h3 id="{html.escape(table.name)}">{heading}</h3>'
        f"<table>{colgroup}{head}{''.join(body_rows)}</table>"
        f"{index_html}"
    )


def _table_summary_html(tables: list[Table]) -> str:
    """テーブル一覧（物理名 / 論理名）のサマリ表。

    Mermaid の箱には論理名を出せない仕様のため、ER 図の近くにこの対応表を置いて補う。
    """
    colgroup = '<colgroup><col style="width:28%"><col style="width:72%"></colgroup>'
    head = "<tr><th>物理名</th><th>論理名</th></tr>"
    rows = []
    for t in tables:
        rows.append(
            "<tr>"
            f'<td><a href="#{html.escape(t.name)}"><code>{html.escape(t.name)}</code></a></td>'
            f"<td>{html.escape(_table_logical(t))}</td>"
            "</tr>"
        )
    return f"<table>{colgroup}{head}{''.join(rows)}</table>"


def render_html() -> str:
    """GET /dev/erd が返す HTML 全文。Mermaid.js（CDN）で ER 図を描画する。"""
    tables = _sorted_tables()
    mermaid_src = html.escape(build_mermaid(tables))
    summary_html = _table_summary_html(tables)
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
  /* インデックス表は補助情報。主表（青系）と差をつける：紫アクセント + 小さめ + 淡い背景。 */
  .idx-label {{ color: #a78bfa; font-size: .8rem; margin: .2rem 0 .1rem; font-weight: 600; }}
  .choices {{ color: #94a3b8; font-size: .8rem; margin-top: .25rem; }}
  .idx-table {{ font-size: .8rem; width: 92%; margin-left: auto;
    background: rgba(167,139,250,.05); }}
  .idx-table th {{ background: #2a2440; color: #a78bfa; }}
  .idx-table th, .idx-table td {{ border-color: #3b2f5e; }}
  .toc a, a {{ color: #7dd3fc; text-decoration: none; }}
  .mermaid {{ background: #0b1220; border: 1px solid #1e293b; border-radius: 10px;
    padding: 1rem; overflow-x: auto; }}
  /* table-layout: fixed + colgroup で列幅を固定し、テーブルごとの幅のばらつきをなくす。 */
  table {{ border-collapse: collapse; width: 100%; margin: .5rem 0 1.5rem; font-size: .9rem;
    table-layout: fixed; }}
  th, td {{ border: 1px solid #1e293b; padding: 6px 10px; text-align: left; vertical-align: top;
    overflow-wrap: anywhere; }}
  th {{ background: #1e293b; color: #38bdf8; }}
  code {{ background: rgba(255,255,255,.08); padding: 1px 6px; border-radius: 5px; }}
</style>
</head>
<body>
  <h1>DB スキーマ（ER 図 + 物理名 / 論理名）</h1>
  <p class="note">SQLAlchemy モデル（SSoT）から自動生成。モデルを変えれば即更新。</p>
  <h2>テーブル一覧（物理名 / 論理名）</h2>
  {summary_html}
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

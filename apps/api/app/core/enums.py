# このファイルの役割：
#   DB の文字列カラムが「取りうる固定値」を 1 か所にまとめた列挙（enum）。
#   これまで server_default やサービスにベタ書きしていた "queued" / "github" 等の
#   文字列を enum に集約し、typo や値のズレ（drift）を防ぐ唯一の正（SSoT）にする。
#
#   置き場所が core なのは、モデル（app/models/）からも参照したいため
#   （models は core だけ import できる、→ .claude/rules/backend.md）。
#
#   ここで定義した値は /dev/erd（app/db/docs.py）が「選択肢」として表示する。
#   問題のカテゴリ・難易度や採点ステータス等、Pydantic 側に既に enum がある値は
#   そちら（app/schemas/）が SSoT なので、ここには重複させない。

# StrEnum: 値が文字列の列挙。メンバそのものが str として扱えるので、
#   server_default やクエリ比較にそのまま使える（Python 3.11+ 標準）。
from enum import StrEnum


# JobState: jobs テーブルの state カラム（マシン的な処理状態）。
#   遷移は Go ワーカーが行うが、許容値の Python 側 SSoT として定義する。
class JobState(StrEnum):
    QUEUED = "queued"  # 投入直後（ワーカー未取得）
    RUNNING = "running"  # ワーカーが処理中
    SUCCEEDED = "succeeded"  # 正常終了
    FAILED = "failed"  # 失敗（リトライ上限到達など）


# JobType: jobs テーブルの type カラム（どの種類のジョブか）。
#   値は "<対象>.<動作>" 形式。
class JobType(StrEnum):
    SUBMISSION_GRADE = "submission.grade"  # 解答の採点
    PROBLEM_GENERATE = "problem.generate"  # 問題の生成


# JobQueue: jobs テーブルの queue カラム（どの論理キューに積むか）。
#   採点と生成でワーカーを分けるため、キュー名で振り分ける。
class JobQueue(StrEnum):
    GRADING = "grading"  # 採点ワーカー向け
    GENERATION = "generation"  # 生成ワーカー向け


# Provider: auth_providers テーブルの provider カラム（認証プロバイダ種別）。
#   MVP は GitHub のみ。Google / メール等を足す時はここに追加する。
class Provider(StrEnum):
    GITHUB = "github"

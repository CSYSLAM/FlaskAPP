#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库内容查看器

把 SQLite 数据库的全部表导出成一个自包含的 HTML 文件，直接用浏览器打开即可。
只读连接，不会干扰正在运行的游戏进程。

用法:
    python scripts/db_viewer.py
    python scripts/db_viewer.py --db instance/game_data.db --out db_view.html
    python scripts/db_viewer.py --limit 500        # 每个表最多导出 500 行
    python scripts/db_viewer.py --tables players    # 只看指定表(逗号分隔)
"""
import argparse
import html
import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_DB = PROJECT_ROOT / "instance" / "game_data.db"
DEFAULT_OUT = PROJECT_ROOT / "instance" / "db_view.html"

CELL_TRUNCATE = 300        # 单元格文本超过此长度则截断
LONG_TEXT_COLS = {         # 这些列即使较长也容易超长,额外收紧
    "chat_history", "notifications", "shortcuts", "enemies", "friends",
    "blacklist", "owned_titles", "activity_data", "visited_locations",
    "active_quests", "completed_quests", "item_usage_raw", "dungeon_clears_raw",
    "boss_kills_raw", "finance_data", "training_data", "garden_data",
    "visitor_logs", "skills_raw", "base_stats", "extra_stats", "initial_stats",
    "occupied_cities_raw", "relation_requests", "content", "declaration",
    "signature", "title_prefix_id", "title_suffix_id",
}


def esc(value):
    """HTML 转义,避免数据里的 < > & 破坏页面或被注入。"""
    return html.escape(str(value), quote=True)


def render_cell(value, col_name):
    if value is None:
        return '<span class="null">NULL</span>'
    if isinstance(value, (bytes, bytearray)):
        text = repr(bytes(value))
        if len(text) > CELL_TRUNCATE:
            text = text[:CELL_TRUNCATE] + "…"
        return '<span class="blob">' + esc(text) + "</span>"
    text = str(value)
    limit = 80 if col_name in LONG_TEXT_COLS else CELL_TRUNCATE
    if len(text) > limit:
        text = text[:limit] + "…"
    return esc(text)


def get_tables(con, only=None):
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    names = [r[0] for r in rows]
    if only:
        wanted = set(only.split(","))
        names = [n for n in names if n in wanted]
    return names


def build_table_section(con, table, limit):
    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
    total = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    rows = con.execute(f'SELECT * FROM "{table}" LIMIT ?', (limit,)).fetchall()
    truncated = total > len(rows)

    thead = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = []
    for row in rows:
        tds = "".join(f"<td>{render_cell(v, cols[i])}</td>" for i, v in enumerate(row))
        body.append(f"<tr>{tds}</tr>")
    body_html = "\n".join(body)

    count_label = f"{len(rows)} / {total} 行" + (" (已截断)" if truncated else "")
    anchor = f"tbl-{esc(table)}"
    return f"""
    <section id="{anchor}" class="table-section">
      <h2>{esc(table)} <span class="count">{count_label}</span></h2>
      <div class="table-wrap">
        <table>
          <thead><tr>{thead}</tr></thead>
          <tbody>
{body_html}
          </tbody>
        </table>
      </div>
    </section>
    """


def build_html(con, tables, limit):
    toc_items = []
    sections = []
    for t in tables:
        total = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        anchor = f"tbl-{esc(t)}"
        toc_items.append(
            f'<li><a href="#{anchor}">{esc(t)}</a> '
            f'<span class="toc-count">{total}</span></li>'
        )
        sections.append(build_table_section(con, t, limit))
    toc_html = "\n".join(toc_items)
    sections_html = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>数据库查看器 · game_data.db</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, "Segoe UI", "PingFang SC",
         "Microsoft YaHei", sans-serif; font-size: 13px; color: #1f2329;
         background: #f5f6f8; }}
  header {{ position: sticky; top: 0; z-index: 10; background: #2b3a55;
           color: #fff; padding: 10px 14px; display: flex; gap: 12px;
           align-items: center; flex-wrap: wrap; }}
  header h1 {{ font-size: 15px; margin: 0; font-weight: 600; }}
  header input {{ flex: 1; min-width: 160px; padding: 6px 10px; border: 0;
                 border-radius: 6px; font-size: 13px; }}
  .layout {{ display: flex; align-items: flex-start; }}
  nav {{ position: sticky; top: 48px; align-self: flex-start; width: 220px;
        max-height: calc(100vh - 48px); overflow: auto; background: #fff;
        border-right: 1px solid #e5e7eb; padding: 10px 0; }}
  nav ul {{ list-style: none; margin: 0; padding: 0; }}
  nav li {{ padding: 4px 14px; }}
  nav a {{ color: #2b3a55; text-decoration: none; }}
  nav a:hover {{ text-decoration: underline; }}
  .toc-count {{ color: #9aa3b2; font-size: 11px; margin-left: 4px; }}
  main {{ flex: 1; padding: 14px; min-width: 0; }}
  .table-section {{ background: #fff; border: 1px solid #e5e7eb;
                   border-radius: 8px; margin-bottom: 16px; overflow: hidden; }}
  .table-section h2 {{ margin: 0; padding: 10px 14px; background: #eef1f6;
                      font-size: 14px; border-bottom: 1px solid #e5e7eb; }}
  .count {{ color: #9aa3b2; font-weight: 400; font-size: 12px; margin-left: 8px; }}
  .table-wrap {{ overflow: auto; max-height: 70vh; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 5px 8px; text-align: left;
           white-space: nowrap; vertical-align: top; }}
  th {{ position: sticky; top: 0; background: #f0f3f8; z-index: 1;
       font-weight: 600; }}
  tbody tr:nth-child(even) {{ background: #fafbfc; }}
  td:hover {{ background: #fff7e6; }}
  .null {{ color: #c0c4cc; font-style: italic; }}
  .blob {{ color: #b76e22; }}
  .empty {{ color: #9aa3b2; padding: 20px; }}
</style>
</head>
<body>
<header>
  <h1>数据库查看器</h1>
  <input id="search" type="search" placeholder="搜索任意单元格内容 (表格内过滤)…" oninput="filterRows(this.value)">
</header>
<div class="layout">
  <nav>
    <ul>{toc_html}</ul>
  </nav>
  <main>
{sections_html}
  </main>
</div>
<script>
function filterRows(q) {{
  q = q.trim().toLowerCase();
  document.querySelectorAll('main tbody tr').forEach(function(tr) {{
    if (!q) {{ tr.style.display = ''; return; }}
    var hit = false;
    tr.querySelectorAll('td').forEach(function(td) {{
      if (td.textContent.toLowerCase().indexOf(q) !== -1) hit = true;
    }});
    tr.style.display = hit ? '' : 'none';
  }});
}}
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="把 SQLite 数据库导出成可浏览的 HTML")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="数据库文件路径")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 HTML 路径")
    ap.add_argument("--limit", type=int, default=2000, help="每个表最多导出的行数")
    ap.add_argument("--tables", default=None, help="只看指定表,逗号分隔")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"数据库不存在: {db_path}")

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        tables = get_tables(con, args.tables)
        if not tables:
            raise SystemExit("没有匹配的表。")
        out = Path(args.out)
        out.write_text(build_html(con, tables, args.limit), encoding="utf-8")
        print(f"已生成: {out}")
        print(f"共 {len(tables)} 张表, 输出大小 {out.stat().st_size/1024:.1f} KB")
    finally:
        con.close()


if __name__ == "__main__":
    main()

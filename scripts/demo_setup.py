"""Create a synthetic demo DB (no production text)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

MEMORIES = [
    ("manual_remember", 9, "项目起点=手机端安装失败，提示先启用 Google 账号；当时手里没有任何日志。"),
    ("auto_patrol", 8, "起点排查：同包在旧 Android 手机能装，在新手机上失败，先怀疑安装校验。"),
    ("auto_patrol", 8, "8-19：启动器 v3 的根因是 scoped storage，旧 app 读不到共享目录。"),
    ("auto_patrol", 8, "8-19：v4 修掉 InjectActivity finish 陷阱，根因在代码里可见。"),
    ("episodic", 7, "8-23：装不上、无 logcat、上次成功不可复现，进入盲改期。"),
    ("manual_remember", 9, "8-23 比 8-19 更难：前者缺新信息（盲改），后者有明确根因可验证。"),
    ("learning_gap", 7, "教训：排障先固定版本与环境，再改代码；否则会把工具链问题当成程序 bug。"),
    ("contract", 9, "红线：不删用户数据、不把生产库当测试库。"),
    ("progress", 6, "进度：已能复现问题，下一步是补齐错误日志开关。"),
    ("profile", 5, "画像：偏好结论+判据+证据的答法，不喜欢只给结论。"),
    ("intent", 7, "待办：给排障脚本加一条“先记录版本”的检查。"),
    ("semantic", 6, "领域事实：抓取上下文时，私聊与群聊要分开处理。"),
]


def main(argv=None) -> int:
    path = Path((argv or sys.argv[1:2] or ["/tmp/mem-patrol-demo/demo.db"])[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table memories (id integer primary key, group_id text, user_id text,
          content text, importance integer, memory_type text, created_at integer,
          last_accessed integer, access_count integer, emotion text);
        create table raw_messages (id integer primary key, sender_id text, sender_name text,
          message text, group_id text, timestamp integer);
        create table bot_messages (id integer primary key, group_id text, message text, timestamp integer);
        """
    )
    base = 1_792_000_000
    for index, (memory_type, importance, content) in enumerate(MEMORIES, start=1):
        conn.execute(
            "insert into memories values (?,?,?,?,?,?,?,?,?,?)",
            (index, "demo", "demo-user", content, importance, memory_type, (base + index) * 1000, 0, 0, None),
        )
    conn.execute("insert into raw_messages values (1,'demo-user','demo-user','项目最困难的阶段是什么','demo-user',?)", (base + 20,))
    conn.execute("insert into bot_messages values (1,'demo','我们会从起点开始理。',?)", (base + 21,))
    conn.commit()
    conn.close()
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

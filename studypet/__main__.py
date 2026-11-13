"""Run with: python -m studypet --help."""

import argparse
import json
import sys
from datetime import datetime, timezone

from .tasks import TaskStore


def main():
    # Redirected output on non-Chinese Windows may otherwise use cp1252.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="StudyPet 本地任务工具（早期版本）")
    parser.add_argument("--db", default=".local/studypet.sqlite3", help="任务数据库路径")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="新增一个已确认的学习任务")
    add.add_argument("title")
    add.add_argument("--due", required=True, help="带时区的 ISO 时间")
    commands.add_parser("list", help="列出所有任务")
    commands.add_parser("due", help="列出到时且未完成的任务（不会启动提醒）")
    done = commands.add_parser("done", help="完成任务")
    done.add_argument("id", type=int)
    args = parser.parse_args()
    try:
        store = TaskStore(args.db)
        if args.command == "add":
            result = {"id": store.add(args.title, datetime.fromisoformat(args.due))}
        elif args.command == "done":
            store.complete(args.id)
            result = {"id": args.id, "status": "done"}
        else:
            cutoff = datetime.now(timezone.utc) if args.command == "due" else None
            result = store.list(cutoff)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

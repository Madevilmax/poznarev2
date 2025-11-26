import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


class TaskManagerBot:
    def __init__(self, token: str):
        self.token = token
        self.base_dir = Path(__file__).parent
        self.tasks_file = self.base_dir / "tasks.json"
        self.users_file = self.base_dir / "users.json"
        self.config_file = self.base_dir / "config.json"

    # ---------- data helpers ----------
    def load_data(self, filename: Path, default_data: Dict) -> Dict:
        if filename.exists():
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        self.save_data(default_data, filename)
        return default_data.copy()

    def save_data(self, data: Dict, filename: Path) -> None:
        temp_file = filename.with_suffix(filename.suffix + ".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if filename.exists():
            os.replace(temp_file, filename)
        else:
            os.rename(temp_file, filename)

    def get_tasks_data(self) -> Dict:
        return self.load_data(self.tasks_file, {"tasks": []})

    def save_tasks(self, tasks_data: Dict) -> None:
        self.save_data(tasks_data, self.tasks_file)

    # ---------- id helpers ----------
    def next_task_id(self, tasks_data: Dict) -> int:
        ids = [task.get("id", 0) for task in tasks_data.get("tasks", [])]
        return max(ids) + 1 if ids else 1

    def next_group_task_id(self, tasks_data: Dict) -> int:
        ids = [task.get("group_task_id", 0) for task in tasks_data.get("tasks", []) if task.get("group_task_id")]
        return max(ids) + 1 if ids else 1

    # ---------- core operations ----------
    def create_task(
        self,
        task_text: str,
        deadline: str,
        group_id: str,
        assigned_by: str,
        assignees: List[str],
    ) -> Dict:
        tasks_data = self.get_tasks_data()
        group_task_id = self.next_group_task_id(tasks_data)
        created_tasks = []

        for user in assignees:
            new_task = {
                "id": self.next_task_id(tasks_data),
                "group_task_id": group_task_id,
                "task_text": task_text,
                "deadline": deadline,
                "group_id": group_id,
                "assigned_to": user,
                "assigned_by": assigned_by,
                "status": "active",
                "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "completed_at": "",
            }
            tasks_data["tasks"].append(new_task)
            created_tasks.append(new_task)

        self.save_tasks(tasks_data)
        return {"group_task_id": group_task_id, "tasks": created_tasks}

    def reassign_task_for_task(self, task_id: int, new_assignee: str, reassigned_by: str) -> Optional[Dict]:
        tasks_data = self.get_tasks_data()
        task = next((t for t in tasks_data.get("tasks", []) if t.get("id") == task_id), None)
        if not task:
            return None

        new_task = {
            "id": self.next_task_id(tasks_data),
            "group_task_id": task.get("group_task_id"),
            "task_text": task.get("task_text", ""),
            "deadline": task.get("deadline", ""),
            "group_id": task.get("group_id", ""),
            "assigned_to": new_assignee,
            "assigned_by": reassigned_by,
            "status": "active",
            "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "completed_at": "",
        }
        tasks_data["tasks"].append(new_task)
        self.save_tasks(tasks_data)
        return new_task

    def update_status(self, task_id: int, status: str) -> Optional[Dict]:
        tasks_data = self.get_tasks_data()
        task = next((t for t in tasks_data.get("tasks", []) if t.get("id") == task_id), None)
        if not task:
            return None

        task["status"] = status
        if status == "completed":
            task["completed_at"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        else:
            task["completed_at"] = ""
        self.save_tasks(tasks_data)
        return task

    # ---------- telegram handlers ----------
    async def start(self, update: Update, context: CallbackContext) -> None:
        await update.message.reply_text(
            "Привет! Я помогаю управлять групповыми задачами.\n"
            "Команды:\n"
            "- /newtask <текст> | <дата в формате ДД.ММ.ГГГГ> | <group_id> | <@user1,@user2>\n"
            "- /complete <task_id>\n"
            "- /reassign <task_id> <@user>\n"
            "- /tasks"
        )

    async def list_tasks(self, update: Update, context: CallbackContext) -> None:
        tasks_data = self.get_tasks_data()
        if not tasks_data.get("tasks"):
            await update.message.reply_text("Задач нет")
            return

        groups: Dict[int, List[Dict]] = {}
        for task in tasks_data.get("tasks", []):
            gid = task.get("group_task_id") or task.get("id")
            groups.setdefault(gid, []).append(task)

        lines = []
        for gid, tasks in groups.items():
            lines.append(f"# Группа {gid}")
            for t in tasks:
                status = "✅" if t.get("status") == "completed" else "⏳"
                lines.append(
                    f"{status} {t.get('id')} — {t.get('task_text')} (до {t.get('deadline')}) для {t.get('assigned_to')}"
                )
        await update.message.reply_text("\n".join(lines))

    async def new_task_handler(self, update: Update, context: CallbackContext) -> None:
        if not context.args:
            await update.message.reply_text(
                "Используйте формат: /newtask <текст> | <ДД.ММ.ГГГГ> | <group_id> | <@user1,@user2>"
            )
            return

        raw = " ".join(context.args)
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) != 4:
            await update.message.reply_text(
                "Неверный формат. Пример: /newtask Сделать отчёт | 31.12.2024 | -100 | @user1,@user2"
            )
            return

        task_text, deadline, group_id, assignees_raw = parts
        assignees = [a.strip() for a in assignees_raw.split(",") if a.strip()]
        if not assignees:
            await update.message.reply_text("Нужно указать хотя бы одного исполнителя")
            return

        result = self.create_task(task_text, deadline, group_id, update.effective_user.username or "", assignees)
        await update.message.reply_text(
            f"Создана группа задач {result['group_task_id']} для: {', '.join(assignees)}"
        )

        if group_id:
            await context.bot.send_message(
                chat_id=group_id,
                text=(
                    "🎯 Новая группа задач\n"
                    f"📝 {task_text}\n"
                    f"⏰ Срок: {deadline}\n"
                    f"👥 Исполнители: {', '.join(assignees)}"
                ),
            )

    async def complete_handler(self, update: Update, context: CallbackContext) -> None:
        if not context.args:
            await update.message.reply_text("Укажите ID задачи: /complete <task_id>")
            return
        try:
            task_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("ID задачи должен быть числом")
            return

        updated = self.update_status(task_id, "completed")
        if not updated:
            await update.message.reply_text("Задача не найдена")
            return
        await update.message.reply_text(f"Задача {task_id} отмечена выполненной")

    async def reassign_handler(self, update: Update, context: CallbackContext) -> None:
        if len(context.args) < 2:
            await update.message.reply_text("Используйте: /reassign <task_id> <@user>")
            return
        try:
            task_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("ID задачи должен быть числом")
            return
        new_user = context.args[1]
        new_task = self.reassign_task_for_task(task_id, new_user, update.effective_user.username or "")
        if not new_task:
            await update.message.reply_text("Задача не найдена")
            return
        await update.message.reply_text(
            f"Создана новая подзадача {new_task['id']} в группе {new_task['group_task_id']} для {new_user}"
        )

    def build_application(self) -> Application:
        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("tasks", self.list_tasks))
        app.add_handler(CommandHandler("newtask", self.new_task_handler))
        app.add_handler(CommandHandler("complete", self.complete_handler))
        app.add_handler(CommandHandler("reassign", self.reassign_handler))
        app.add_handler(MessageHandler(filters.COMMAND, self.start))
        return app

    def run(self) -> None:
        application = self.build_application()
        application.run_polling()


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан")
    bot = TaskManagerBot(token)
    bot.run()


if __name__ == "__main__":
    main()

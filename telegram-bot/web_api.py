import json
import logging
import os
from datetime import datetime
from threading import Lock

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(BASE_DIR, "tasks.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

file_lock = Lock()


class DataManager:
    def load_data(self, filename, default_data):
        with file_lock:
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            self.save_data(default_data, filename)
            return default_data.copy()

    def save_data(self, data, filename):
        with file_lock:
            temp_file = f"{filename}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if os.path.exists(filename):
                os.replace(temp_file, filename)
            else:
                os.rename(temp_file, filename)

    def next_task_id(self, tasks_data):
        existing = [task.get("id", 0) for task in tasks_data.get("tasks", [])]
        return max(existing) + 1 if existing else 1

    def next_group_task_id(self, tasks_data):
        existing = [task.get("group_task_id", 0) for task in tasks_data.get("tasks", []) if task.get("group_task_id")]
        return max(existing) + 1 if existing else 1


data_manager = DataManager()


def send_telegram_message(chat_id: str, text: str):
    if not BOT_TOKEN or not chat_id:
        return
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        if not response.ok:
            logging.warning("Не удалось отправить уведомление в Telegram: %s", response.text)
    except Exception as exc:  # noqa: BLE001
        logging.error("Ошибка отправки уведомления: %s", exc)


def is_task_overdue(deadline_str: str) -> bool:
    if not deadline_str:
        return False
    try:
        deadline = datetime.strptime(deadline_str, "%d.%m.%Y").replace(hour=23, minute=59, second=59)
        return deadline < datetime.now()
    except ValueError:
        return False


def find_task_by_id(tasks_data, task_id):
    for task in tasks_data.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    tasks_data = data_manager.load_data(TASKS_FILE, {"tasks": []})
    for task in tasks_data.get("tasks", []):
        task["is_overdue"] = is_task_overdue(task.get("deadline", "")) if task.get("status") == "active" else False
    return jsonify(tasks_data)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    payload = request.json or {}
    assigned_to = payload.get("assigned_to") or []
    if isinstance(assigned_to, str):
        assigned_to = [assigned_to]
    if not assigned_to:
        return jsonify({"success": False, "error": "assigned_to обязателен"}), 400

    tasks_data = data_manager.load_data(TASKS_FILE, {"tasks": []})
    group_task_id = payload.get("group_task_id") or data_manager.next_group_task_id(tasks_data)

    created = []
    for user in assigned_to:
        new_task = {
            "id": data_manager.next_task_id(tasks_data),
            "group_task_id": group_task_id,
            "assigned_to": user,
            "assigned_by": payload.get("assigned_by", ""),
            "task_text": payload.get("task_text", ""),
            "deadline": payload.get("deadline", ""),
            "status": "active",
            "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "completed_at": "",
            "group_id": payload.get("group_id", ""),
        }
        tasks_data["tasks"].append(new_task)
        created.append(new_task)

    data_manager.save_data(tasks_data, TASKS_FILE)

    group_id = str(payload.get("group_id", ""))
    if group_id:
        assigned_display = ", ".join(str(u) for u in assigned_to)
        message = (
            "🎯 Новая группа задач\n"
            f"📝 {payload.get('task_text', '')}\n"
            f"⏰ Срок: {payload.get('deadline', '')}\n"
            f"👥 Исполнители: {assigned_display}"
        )
        send_telegram_message(group_id, message)

    return jsonify({"success": True, "group_task_id": group_task_id, "tasks": created}), 201


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    payload = request.json or {}
    tasks_data = data_manager.load_data(TASKS_FILE, {"tasks": []})
    task = find_task_by_id(tasks_data, task_id)
    if not task:
        return jsonify({"success": False, "error": "Задача не найдена"}), 404

    if payload.get("group_operation"):
        group_id = task.get("group_task_id")
        updated_tasks = []
        for t in tasks_data.get("tasks", []):
            if t.get("group_task_id") == group_id:
                if "task_text" in payload:
                    t["task_text"] = payload["task_text"]
                if "deadline" in payload:
                    t["deadline"] = payload["deadline"]
                if "group_id" in payload:
                    t["group_id"] = payload["group_id"]
                updated_tasks.append(dict(t))
        data_manager.save_data(tasks_data, TASKS_FILE)
        return jsonify({"success": True, "is_group_operation": True, "tasks": updated_tasks})

    if "status" in payload:
        task["status"] = payload.get("status")
        if task["status"] == "completed":
            task["completed_at"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        else:
            task["completed_at"] = payload.get("completed_at", "")

    if "assigned_to" in payload:
        new_assignee = payload.get("assigned_to")
        if isinstance(new_assignee, list):
            new_assignee = new_assignee[0] if new_assignee else task.get("assigned_to")
        task["assigned_to"] = new_assignee

    if "task_text" in payload:
        task["task_text"] = payload["task_text"]
    if "deadline" in payload:
        task["deadline"] = payload["deadline"]
    if "group_id" in payload:
        task["group_id"] = payload["group_id"]
    if "completed_at" in payload and payload.get("status") != "completed":
        task["completed_at"] = payload["completed_at"]

    data_manager.save_data(tasks_data, TASKS_FILE)
    return jsonify({"success": True, "task": dict(task)})


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    tasks_data = data_manager.load_data(TASKS_FILE, {"tasks": []})
    task = find_task_by_id(tasks_data, task_id)
    if not task:
        return jsonify({"success": False, "error": "Задача не найдена"}), 404

    group_id = task.get("group_task_id")
    tasks_data["tasks"] = [t for t in tasks_data.get("tasks", []) if t.get("id") != task_id]
    remaining = len([t for t in tasks_data.get("tasks", []) if t.get("group_task_id") == group_id])
    data_manager.save_data(tasks_data, TASKS_FILE)
    return jsonify({"success": True, "remaining_in_group": remaining})


@app.route("/api/users", methods=["GET"])
def get_users():
    users = data_manager.load_data(USERS_FILE, {"groups": {}, "all_users": {}})
    return jsonify(users)


@app.route("/api/config", methods=["GET"])
def get_config():
    config = data_manager.load_data(
        CONFIG_FILE,
        {
            "group_chat_ids": [],
            "admins": [],
            "notifications": {
                "task_created": True,
                "task_completed": True,
                "task_deleted": True,
                "overdue_reminder": True,
            },
        },
    )
    return jsonify(config)


@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("web", path)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("web_api.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

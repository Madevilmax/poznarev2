# web_api.py
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
import os
import logging
from datetime import datetime
import threading
import time
import copy
import requests

app = Flask(__name__)
CORS(app)

# Абсолютные пути к файлам
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(BASE_DIR, 'tasks.json')
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Блокировки для потокобезопасности
file_lock = threading.Lock()

class DataManager:
    def load_data_from_file(self, filename, default_data):
        """Загружает данные из файла с блокировкой"""
        with file_lock:
            try:
                if os.path.exists(filename):
                    with open(filename, 'r', encoding='utf-8') as f:
                        return json.load(f)
                else:
                    logging.warning(f"📁 Файл {filename} не найден, создаем с данными по умолчанию")
                    self.save_data_to_file(default_data, filename)
                    return default_data.copy()
            except Exception as e:
                logging.error(f"❌ Ошибка загрузки {filename}: {e}")
                return default_data.copy()
    
    def save_data_to_file(self, data, filename):
        """Сохраняет данные в файл с блокировкой"""
        with file_lock:
            try:
                # Создаем временный файл
                temp_file = f"{filename}.tmp"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Заменяем оригинальный файл
                if os.path.exists(filename):
                    os.replace(temp_file, filename)
                else:
                    os.rename(temp_file, filename)
                
                return True
            except Exception as e:
                logging.error(f"❌ Ошибка сохранения {filename}: {e}")
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception:
                    pass
                return False

    def get_next_task_id(self, tasks_data):
        """Генерирует уникальный ID для задачи на основе текущих данных"""
        try:
            existing_ids = [task.get('id', 0) for task in tasks_data.get("tasks", [])]
            return max(existing_ids) + 1 if existing_ids else 1
        except Exception as e:
            logging.error(f"Ошибка генерации ID задачи: {e}")
            return len(tasks_data.get("tasks", [])) + 1

# Инициализация менеджера данных
data_manager = DataManager()


def send_telegram_message(chat_id: str, text: str):
    """Отправляет сообщение в Telegram, если доступен токен"""
    if not BOT_TOKEN:
        logging.warning("TELEGRAM_BOT_TOKEN не задан, уведомления не отправлены")
        return

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text}
        )
        if not response.ok:
            logging.warning(f"Не удалось отправить уведомление в Telegram: {response.text}")
    except Exception as e:
        logging.error(f"Ошибка отправки уведомления в Telegram: {e}")

def is_task_overdue(deadline_str):
    """Проверяет, просрочена ли задача"""
    try:
        deadline = datetime.strptime(deadline_str, '%d.%m.%Y')
        today = datetime.now()
        deadline = deadline.replace(hour=23, minute=59, second=59)
        return deadline < today
    except ValueError:
        return False

def get_tasks_by_group(tasks_data, task_text, deadline, group_id):
    """Находит все задачи с одинаковыми параметрами группы"""
    return [task for task in tasks_data.get("tasks", []) 
            if task.get("task_text") == task_text 
            and task.get("deadline") == deadline 
            and task.get("group_id") == group_id]

def find_task_by_id(tasks_data, task_id):
    """Находит задачу по ID в данных"""
    for task in tasks_data.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


def normalize_username(username: str) -> str:
    """Возвращает логин с ведущим @"""
    if not username:
        return ""
    return username if username.startswith("@") else f"@{username}"

# API Routes
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """Получить все задачи"""
    try:
        tasks_data = data_manager.load_data_from_file(TASKS_FILE, {"tasks": []})
        
        # Добавляем информацию о просроченности
        for task in tasks_data.get("tasks", []):
            if task.get("status") == "active":
                task["is_overdue"] = is_task_overdue(task.get("deadline", ""))
            else:
                task["is_overdue"] = False
        
        logging.info(f"📊 API: Отправлено {len(tasks_data.get('tasks', []))} задач")
        return jsonify(tasks_data)
    except Exception as e:
        logging.error(f"❌ Ошибка получения задач: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/tasks', methods=['POST'])
def create_task():
    """Создать новую задачу"""
    try:
        task_data = request.json

        assigned_by = task_data.get('assigned_by')
        if not assigned_by:
            return jsonify({"success": False, "error": "Выберите назначившего администратора"}), 400

        skip_notification = bool(task_data.get('skip_notification', False))
        
        # Загружаем текущие задачи ОДИН РАЗ
        tasks_data = data_manager.load_data_from_file(TASKS_FILE, {"tasks": []})
        
        created_tasks = []
        assigned_to = task_data.get('assigned_to')
        
        # Если assigned_to - список, создаем задачи для каждого пользователя с РАЗНЫМИ ID
        if isinstance(assigned_to, list):
            for user in assigned_to:
                # ГЕНЕРИРУЕМ УНИКАЛЬНЫЙ ID ДЛЯ КАЖДОЙ ЗАДАЧИ
                new_task_id = data_manager.get_next_task_id(tasks_data)
                
                new_task = {
                    "id": new_task_id,  # Уникальный ID для каждой задачи
                    "assigned_to": user,
                    "assigned_by": assigned_by,
                    "task_text": task_data.get('task_text'),
                    "deadline": task_data.get('deadline'),
                    "status": "active",
                    "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                    "completed_at": "",
                    "group_id": task_data.get('group_id', 'web'),
                    "initiator": task_data.get('initiator', assigned_by),
                }
                tasks_data["tasks"].append(new_task)
                created_tasks.append(new_task)
                
                # ОБНОВЛЯЕМ ID ДЛЯ СЛЕДУЮЩЕЙ ЗАДАЧИ
                # Для этого просто увеличиваем счетчик в текущей сессии
                # Не перезагружаем файл, чтобы не терять производительность
        else:
            # Одиночное назначение
            new_task_id = data_manager.get_next_task_id(tasks_data)
            new_task = {
                "id": new_task_id,
                "assigned_to": assigned_to,
                "assigned_by": assigned_by,
                "task_text": task_data.get('task_text'),
                "deadline": task_data.get('deadline'),
                "status": "active",
                "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "completed_at": "",
                "group_id": task_data.get('group_id', 'web'),
                "initiator": task_data.get('initiator', assigned_by),
            }
            tasks_data["tasks"].append(new_task)
            created_tasks.append(new_task)
        
        # Сохраняем ВСЕ задачи ОДНИМ ЗАПРОСОМ
        if data_manager.save_data_to_file(tasks_data, TASKS_FILE):
            logging.info(f"✅ Создано {len(created_tasks)} задач через веб-интерфейс")

            config_data = data_manager.load_data_from_file(CONFIG_FILE, {"notifications": {"task_created": True}})
            if (config_data.get("notifications", {}).get("task_created", True)
                    and not skip_notification):
                group_id = str(task_data.get('group_id', ''))
                if group_id:
                    assigned_list = assigned_to if isinstance(assigned_to, list) else [assigned_to]
                    assigned_display = ", ".join(user for user in assigned_list if user)
                    message = (
                        "🎯 Новая задача создана через веб!\n\n"
                        f"👥 Исполнители: {assigned_display}\n"
                        f"📝 Задача: {task_data.get('task_text', '')}\n"
                        f"⏰ Срок: {task_data.get('deadline', '')}\n"
                        f"👑 Назначил: {assigned_by}"
                    )
                    send_telegram_message(group_id, message)
            return jsonify({"success": True, "tasks": created_tasks})
        else:
            return jsonify({"success": False, "error": "Ошибка сохранения"}), 500
            
    except Exception as e:
        logging.error(f"❌ Ошибка создания задачи: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    """Обновить задачу"""
    try:
        update_data = request.json
        logging.info(f"🔄 Обновление задачи #{task_id}: {update_data}")
        
        # Загружаем текущие задачи
        tasks_data = data_manager.load_data_from_file(TASKS_FILE, {"tasks": []})
        
        # Находим задачу
        task_to_update = find_task_by_id(tasks_data, task_id)
        
        if not task_to_update:
            logging.error(f"❌ Задача #{task_id} не найдена")
            return jsonify({"success": False, "error": "Задача не найдена"}), 404
        
        # Групповая операция - обновляем все задачи с одинаковыми параметрами
        if update_data.get('group_operation'):
            group_tasks = get_tasks_by_group(tasks_data, 
                                           task_to_update.get('task_text'), 
                                           task_to_update.get('deadline'), 
                                           task_to_update.get('group_id'))
            
            updated_tasks = []
            for group_task in group_tasks:
                if 'task_text' in update_data:
                    group_task['task_text'] = update_data['task_text']
                if 'deadline' in update_data:
                    group_task['deadline'] = update_data['deadline']
                if 'group_id' in update_data:
                    group_task['group_id'] = update_data['group_id']
                
                updated_tasks.append(copy.deepcopy(group_task))
            
            # Сохраняем
            if data_manager.save_data_to_file(tasks_data, TASKS_FILE):
                logging.info(f"✅ Обновлена группа задач через веб-интерфейс (всего {len(updated_tasks)} задач)")
                return jsonify({"success": True, "is_group_operation": True, "tasks": updated_tasks})
            else:
                return jsonify({"success": False, "error": "Ошибка сохранения"}), 500
        
        # Обновление статуса - только для конкретной задачи
        if 'status' in update_data:
            old_status = task_to_update.get('status')
            new_status = update_data['status']
            
            task_to_update['status'] = new_status
            if new_status == 'completed':
                task_to_update['completed_at'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            else:
                task_to_update['completed_at'] = ""
            
            logging.info(f"✅ Статус задачи #{task_id} изменен: {old_status} -> {new_status}")
        
        # Обновление других полей
        if 'task_text' in update_data:
            task_to_update['task_text'] = update_data['task_text']
        
        if 'deadline' in update_data:
            task_to_update['deadline'] = update_data['deadline']
        
        if 'assigned_to' in update_data:
            assigned_to = update_data['assigned_to']
            task_to_update['assigned_to'] = assigned_to[0] if isinstance(assigned_to, list) else assigned_to
        
        # Сохраняем
        if data_manager.save_data_to_file(tasks_data, TASKS_FILE):
            logging.info(f"✅ Задача #{task_id} успешно обновлена")
            return jsonify({"success": True, "task": copy.deepcopy(task_to_update)})
        else:
            return jsonify({"success": False, "error": "Ошибка сохранения"}), 500
            
    except Exception as e:
        logging.error(f"❌ Ошибка обновления задачи #{task_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Удалить задачу"""
    try:
        # Загружаем текущие задачи
        tasks_data = data_manager.load_data_from_file(TASKS_FILE, {"tasks": []})
        
        # Находим задачу для логирования и получения параметров группы
        task_to_delete = find_task_by_id(tasks_data, task_id)
        remaining_in_group = 0
        
        if task_to_delete:
            # Считаем сколько задач останется в группе после удаления
            group_tasks = get_tasks_by_group(tasks_data, 
                                           task_to_delete.get('task_text'), 
                                           task_to_delete.get('deadline'), 
                                           task_to_delete.get('group_id'))
            remaining_in_group = len(group_tasks) - 1  # Минус удаляемая задача
        
        # Фильтруем задачи
        original_count = len(tasks_data.get("tasks", []))
        tasks_data["tasks"] = [task for task in tasks_data.get("tasks", []) 
                              if task.get('id') != task_id]
        
        if len(tasks_data["tasks"]) == original_count:
            logging.error(f"❌ Задача #{task_id} не найдена для удаления")
            return jsonify({"success": False, "error": "Задача не найдена"}), 404
        
        # Сохраняем
        if data_manager.save_data_to_file(tasks_data, TASKS_FILE):
            logging.info(f"🗑 Задача #{task_id} удалена через веб-интерфейс")
            return jsonify({"success": True, "remaining_in_group": remaining_in_group})
        else:
            return jsonify({"success": False, "error": "Ошибка сохранения"}), 500
            
    except Exception as e:
        logging.error(f"❌ Ошибка удаления задачи #{task_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/users', methods=['GET'])
def get_users():
    """Получить всех пользователей"""
    try:
        users_data = data_manager.load_data_from_file(USERS_FILE, {"groups": {}, "all_users": {}})
        return jsonify(users_data)
    except Exception as e:
        logging.error(f"❌ Ошибка получения пользователей: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/users', methods=['POST'])
def create_or_update_user():
    """Создать нового пользователя"""
    try:
        payload = request.json or {}
        username = normalize_username(payload.get('username', '').strip())
        full_name = payload.get('full_name', '').strip()
        groups = payload.get('groups', [])

        if not username or not full_name:
            return jsonify({"success": False, "error": "Укажите логин и имя"}), 400

        users_data = data_manager.load_data_from_file(USERS_FILE, {"groups": {}, "all_users": {}})
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        all_users = users_data.setdefault("all_users", {})
        user_entry = all_users.get(username, {})
        user_entry.update({
            "full_name": full_name,
            "last_seen": now_str,
            "first_seen": user_entry.get("first_seen", now_str)
        })

        if groups:
            existing_groups = set(user_entry.get("groups", []))
            user_entry["groups"] = sorted(existing_groups.union(set(groups)))

        all_users[username] = user_entry

        # Добавляем пользователя в группы
        users_groups = users_data.setdefault("groups", {})
        for group_id in user_entry.get("groups", groups):
            group_ref = users_groups.setdefault(group_id, {"title": f"Группа {group_id}", "users": {}, "created_at": now_str})
            group_users = group_ref.setdefault("users", {})
            group_users[username] = {
                "full_name": full_name,
                "last_seen": now_str,
                "added_at": group_users.get(username, {}).get("added_at", now_str)
            }

        if data_manager.save_data_to_file(users_data, USERS_FILE):
            logging.info(f"✅ Пользователь {username} сохранен")
            return jsonify({"success": True, "user": user_entry})
        return jsonify({"success": False, "error": "Ошибка сохранения"}), 500
    except Exception as e:
        logging.error(f"❌ Ошибка сохранения пользователя: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/users/<username>', methods=['PUT'])
def update_user(username):
    """Обновление информации о пользователе"""
    try:
        payload = request.json or {}
        normalized_username = normalize_username(username)
        full_name = payload.get('full_name', '').strip()
        groups = payload.get('groups', [])

        users_data = data_manager.load_data_from_file(USERS_FILE, {"groups": {}, "all_users": {}})
        all_users = users_data.setdefault("all_users", {})

        if normalized_username not in all_users:
            return jsonify({"success": False, "error": "Пользователь не найден"}), 404

        now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        user_entry = all_users[normalized_username]

        if full_name:
            user_entry["full_name"] = full_name
        user_entry["last_seen"] = now_str

        if groups:
            user_entry["groups"] = sorted(set(groups))

        # Синхронизируем данные групп
        users_groups = users_data.setdefault("groups", {})
        for group_id in user_entry.get("groups", []):
            group_ref = users_groups.setdefault(group_id, {"title": f"Группа {group_id}", "users": {}, "created_at": now_str})
            group_users = group_ref.setdefault("users", {})
            group_users[normalized_username] = {
                "full_name": user_entry.get("full_name", normalized_username),
                "last_seen": now_str,
                "added_at": group_users.get(normalized_username, {}).get("added_at", now_str)
            }

        if data_manager.save_data_to_file(users_data, USERS_FILE):
            logging.info(f"✅ Пользователь {normalized_username} обновлен")
            return jsonify({"success": True, "user": user_entry})
        return jsonify({"success": False, "error": "Ошибка сохранения"}), 500
    except Exception as e:
        logging.error(f"❌ Ошибка обновления пользователя: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Получить статистику"""
    try:
        tasks_data = data_manager.load_data_from_file(TASKS_FILE, {"tasks": []})
        users_data = data_manager.load_data_from_file(USERS_FILE, {"groups": {}, "all_users": {}})
        
        all_tasks = tasks_data.get("tasks", [])
        active_tasks = [t for t in all_tasks if t.get('status') == 'active']
        completed_tasks = [t for t in all_tasks if t.get('status') == 'completed']
        overdue_tasks = [t for t in active_tasks if is_task_overdue(t.get('deadline', ''))]
        
        stats = {
            "total_tasks": len(all_tasks),
            "active_tasks": len(active_tasks),
            "completed_tasks": len(completed_tasks),
            "overdue_tasks": len(overdue_tasks),
            "total_users": len(users_data.get("all_users", {})),
            "total_groups": len(users_data.get("groups", {}))
        }
        
        return jsonify(stats)
    except Exception as e:
        logging.error(f"❌ Ошибка получения статистики: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Получить конфигурацию"""
    try:
        config_data = data_manager.load_data_from_file(CONFIG_FILE, {
            "group_chat_ids": [],
            "admins": [],
            "notifications": {
                "task_created": True,
                "task_completed": True,
                "task_deleted": True,
                "overdue_reminder": True
            }
        })
        return jsonify(config_data)
    except Exception as e:
        logging.error(f"❌ Ошибка получения конфигурации: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/config/notifications', methods=['PUT'])
def update_notifications():
    """Обновление настроек уведомлений"""
    try:
        payload = request.json or {}
        new_notifications = payload.get("notifications", {})

        config_data = data_manager.load_data_from_file(CONFIG_FILE, {
            "group_chat_ids": [],
            "admins": [],
            "notifications": {
                "task_created": True,
                "task_completed": True,
                "task_deleted": True,
                "overdue_reminder": True
            }
        })

        config_data["notifications"].update({
            "task_created": bool(new_notifications.get("task_created", config_data["notifications"].get("task_created", True))),
            "task_completed": bool(new_notifications.get("task_completed", config_data["notifications"].get("task_completed", True))),
            "task_deleted": bool(new_notifications.get("task_deleted", config_data["notifications"].get("task_deleted", True))),
            "overdue_reminder": bool(new_notifications.get("overdue_reminder", config_data["notifications"].get("overdue_reminder", True))),
        })

        if data_manager.save_data_to_file(config_data, CONFIG_FILE):
            logging.info("✅ Настройки уведомлений обновлены")
            return jsonify({"success": True, "notifications": config_data["notifications"]})
        return jsonify({"success": False, "error": "Ошибка сохранения"}), 500
    except Exception as e:
        logging.error(f"❌ Ошибка сохранения настроек уведомлений: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """Принудительное обновление данных (для веб-интерфейса)"""
    try:
        # Просто возвращаем успех - веб-интерфейс сам перезагрузит данные
        logging.info("🔄 Веб-интерфейс запросил обновление данных")
        return jsonify({"success": True, "message": "Данные будут обновлены"})
    except Exception as e:
        logging.error(f"❌ Ошибка обновления данных: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# Статические файлы
@app.route('/')
def index():
    return send_from_directory('web', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('web', path)

if __name__ == '__main__':
    # Создаем папку для веб-файлов
    os.makedirs('web', exist_ok=True)
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('web_api.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    print("🚀 Запуск веб-сервера...")
    print("📊 Веб-интерфейс будет доступен по адресу: http://localhost:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
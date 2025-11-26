# bot.py (исправленная версия с удаленными комментариями)
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import json
import os
import shutil 
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import html
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class TaskManagerBot:
    def reset_all_states(self):
        """Сбрасывает все состояния пользователей при перезапуске и логирует"""
        try:
            state_count = len(self.user_states)
            self.user_states.clear()
            logging.info(f"✅ Все состояния пользователей сброшены при перезапуске (было {state_count} состояний)")
            
            # Также сбрасываем последнюю очистку
            self.last_cleanup = datetime.now()
            
        except Exception as e:
            logging.error(f"❌ Ошибка сброса состояний: {e}")

    def __init__(self, token):
        self.token = token
        self.tasks_file = 'tasks.json'
        self.users_file = 'users.json'
        self.config_file = 'config.json'
        
        # Создаем папку для бэкапов
        self.backup_dir = 'backups'
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Состояния пользователей
        self.user_states = {}
        self.last_cleanup = datetime.now()
        
        # Создаем начальный бэкап
        self.create_backup()

    def is_private_chat(self, chat_type):
        """Проверяет, является ли чат личным"""
        return chat_type == "private"

    def load_data(self, filename, default_data):
        """Загружает данные из файла"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logging.warning(f"Файл {filename} не найден, создаем с данными по умолчанию")
                self.save_data(default_data, filename)
                return default_data.copy()
        except Exception as e:
            logging.error(f"Ошибка загрузки {filename}: {e}")
            return default_data.copy()

    def save_data(self, data, filename):
        """Сохраняет данные в файл"""
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
            logging.error(f"Ошибка сохранения {filename}: {e}")
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass
            return False

    def get_tasks(self):
        """Получает актуальные задачи из файла"""
        return self.load_data(self.tasks_file, {"tasks": []})

    def save_tasks(self, tasks_data):
        """Сохраняет задачи в файл"""
        return self.save_data(tasks_data, self.tasks_file)

    def get_users(self):
        """Получает актуальных пользователей из файла"""
        return self.load_data(self.users_file, {"groups": {}, "all_users": {}})

    def save_users(self, users_data):
        """Сохраняет пользователей в файл"""
        return self.save_data(users_data, self.users_file)

    def get_config(self):
        """Получает актуальную конфигурацию из файла"""
        return self.load_data(self.config_file, {
            "group_chat_ids": [],
            "admins": [],
            "notifications": {
                "task_created": True,
                "task_completed": True,
                "task_deleted": True,
                "overdue_reminder": True
            }
        })

    def save_config(self, config_data):
        """Сохраняет конфигурацию в файл"""
        return self.save_data(config_data, self.config_file)

    def create_backup(self):
        """Создает резервную копию данных"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            for filename in [self.tasks_file, self.users_file, self.config_file]:
                if os.path.exists(filename):
                    backup_name = os.path.join(self.backup_dir, f"{filename}.{timestamp}.bak")
                    shutil.copy2(filename, backup_name)
            
            # Удаляем старые бэкапы (оставляем последние 10)
            try:
                backups = []
                for f in os.listdir(self.backup_dir):
                    if f.endswith('.bak'):
                        filepath = os.path.join(self.backup_dir, f)
                        backups.append((filepath, os.path.getctime(filepath)))
                
                backups.sort(key=lambda x: x[1])
                
                for old_backup in backups[:-10]:
                    os.remove(old_backup[0])
                    
            except Exception as cleanup_error:
                logging.warning(f"Ошибка очистки старых бэкапов: {cleanup_error}")
                    
        except Exception as e:
            logging.error(f"Ошибка создания бэкапа: {e}")

    def cleanup_old_states(self):
        """Очищает устаревшие состояния пользователей"""
        try:
            current_time = datetime.now()
            expired_users = []
            
            for user_id, state in self.user_states.items():
                state_time = state.get('created_at', datetime.min)
                if (current_time - state_time) > timedelta(hours=1):
                    expired_users.append(user_id)
            
            for user_id in expired_users:
                del self.user_states[user_id]
                
            self.last_cleanup = current_time
            if expired_users:
                logging.info(f"Очищено {len(expired_users)} устаревших состояний")
            
        except Exception as e:
            logging.error(f"Ошибка очистки состояний: {e}")

    def get_next_task_id_batch(self, tasks_data, count):
        """Генерирует несколько уникальных ID для групповых задач"""
        try:
            existing_ids = [task.get('id', 0) for task in tasks_data.get("tasks", [])]
            current_max = max(existing_ids) if existing_ids else 0
            return [current_max + i + 1 for i in range(count)]
        except Exception as e:
            logging.error(f"Ошибка генерации ID задач: {e}")
            tasks_count = len(tasks_data.get("tasks", []))
            return [tasks_count + i + 1 for i in range(count)]

    def get_next_task_id(self):
        """Генерирует уникальный ID для задачи"""
        try:
            tasks_data = self.get_tasks()
            existing_ids = [task.get('id', 0) for task in tasks_data.get("tasks", [])]
            return max(existing_ids) + 1 if existing_ids else 1
        except Exception as e:
            logging.error(f"Ошибка генерации ID задачи: {e}")
            tasks_data = self.get_tasks()
            return len(tasks_data.get("tasks", [])) + 1

    def get_main_keyboard(self, is_admin=False, chat_type="private"):
        """Возвращает главную клавиатуру только для личных чатов"""
        if not self.is_private_chat(chat_type):
            return None
            
        if is_admin:
            keyboard = [
                ["📋 Мои задачи", "👑 Админ панель"]
            ]
        else:
            keyboard = [
                ["📋 Мои задачи"]
            ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_admin_keyboard(self, chat_type="private"):
        """Возвращает клавиатуру админ-панели только для личных чатов"""
        if not self.is_private_chat(chat_type):
            return None

        keyboard = [
            ["➕ Новая задача", "📋 Все задачи"],
            ["❌ Просроченные", "👥 Задачи по сотрудникам"],
            ["🏘 Задачи по группам", "🛠 Управление задачами"],
            ["⚙️ Настройки уведомлений", "👤 Управление пользователями"],
            ["👑 Управление администраторами", "🏠 Главное меню"]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_admin_management_keyboard(self, chat_type="private"):
        """Клавиатура для управления администраторами только для личных чатов"""
        if not self.is_private_chat(chat_type):
            return None
            
        keyboard = [
            ["➕ Добавить администратора", "🗑 Удалить администратора"],
            ["📋 Список администраторов", "🔙 Назад в админку"]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_task_management_keyboard(self, chat_type="private"):
        """Клавиатура для управления задачами только для личных чатов"""
        if not self.is_private_chat(chat_type):
            return None
            
        keyboard = [
            ["✏️ Изменить задачу", "✅ Завершить задачу"],
            ["🗑 Удалить задачу", "⏰ Изменить срок"],
            ["👤 Переназначить задачу", "🔙 Назад в админку"]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_task_filter_keyboard(self, chat_type="private"):
        """Клавиатура для фильтрации задач только для личных чатов"""
        if not self.is_private_chat(chat_type):
            return None
            
        keyboard = [
            ["🎯 Все задачи", "🟡 Активные"],
            ["🟢 Выполненные", "🔴 Просроченные"],
            ["📅 Сегодня", "📅 Завтра"],
            ["📅 Эта неделя", "📅 Этот месяц"],
            ["🔙 Назад к списку", "❌ Отмена"]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_users_management_keyboard(self, chat_type="private"):
        """Клавиатура для управления пользователями только для личных чатов"""
        if not self.is_private_chat(chat_type):
            return None
            
        keyboard = [
            ["➕ Добавить пользователя", "🗑 Удалить пользователя"],
            ["📋 Список пользователей", "🔙 Назад в админку"]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_my_tasks_keyboard(self, chat_type="private"):
        """Клавиатура для раздела Мои задачи"""
        if not self.is_private_chat(chat_type):
            return None
            
        keyboard = [
            ["📋 Текущие задачи", "✅ Выполненные задачи"],
            ["🏠 Главное меню"]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_task_actions_keyboard(self, task_id, is_completed=False):
        """Клавиатура действий для задачи"""
        if is_completed:
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Открыть заново", callback_data=f"reopen:{task_id}"),
                    InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{task_id}")
                ]
            ]
        else:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Завершить", callback_data=f"complete:{task_id}"),
                    InlineKeyboardButton("⏰ Изменить срок", callback_data=f"change_deadline:{task_id}")
                ]
            ]
        return InlineKeyboardMarkup(keyboard)

    async def safe_send_message(self, chat_id, text, bot, disable_notification=False, **kwargs):
        """Безопасная отправка сообщений с обработкой ошибок"""
        try:
            # Проверяем, что chat_id не пустой
            if not chat_id:
                logging.error(f"Пустой chat_id, невозможно отправить сообщение: {text[:100]}...")
                return False
                
            # Создаем безопасную копию kwargs
            safe_kwargs = kwargs.copy()
            
            # Всегда отключаем форматирование чтобы избежать ошибок парсинга
            safe_kwargs['parse_mode'] = None
            
            # Добавляем параметр отключения уведомлений
            safe_kwargs['disable_notification'] = disable_notification
            
            await bot.send_message(chat_id, text, **safe_kwargs)
            return True
        except Exception as e:
            logging.error(f"Ошибка отправки сообщения в чат {chat_id}: {e}")
            
            # Пытаемся отправить без форматирования и с укороченным текстом
            try:
                short_text = text[:1000] + "..." if len(text) > 1000 else text
                await bot.send_message(chat_id, short_text, disable_notification=disable_notification)
                return True
            except Exception as e2:
                logging.error(f"Ошибка при повторной отправке: {e2}")
                return False

    async def start(self, update: Update, context: CallbackContext):
        try:
            user = update.effective_user
            chat = update.effective_chat
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            await self.add_user_to_group(chat.id, username, user.full_name, chat.title if hasattr(chat, 'title') else "Личный чат")
            
            is_admin = self.is_admin(username)
            
            welcome_text = f"🤖 Бот управления задачами\n\n👋 Привет, {username}!"
            
            if chat.type in ["group", "supergroup"]:
                all_users = self.get_all_users()
                welcome_text += f"\n\n🏠 Группа: {chat.title}"
                welcome_text += f"\n👥 Всего пользователей в системе: {len(all_users)}"
            
            if is_admin:
                welcome_text += "\n\n👑 Вы администратор"
            
            welcome_text += "\n\nВыберите действие:"
            
            await self.safe_send_message(
                chat.id,
                welcome_text,
                context.bot,
                reply_markup=self.get_main_keyboard(is_admin, chat.type)
            )
        except Exception as e:
            logging.error(f"Ошибка в start: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при запуске бота", context.bot)

    async def add_user_to_group(self, chat_id, username, full_name, group_title="Неизвестно"):
        """Автоматически добавляет пользователя в список группы и общий список"""
        try:
            group_id = str(chat_id)
            
            if group_title is None:
                group_title = f"Группа {group_id}"
            
            users_data = self.get_users()
            
            if "groups" not in users_data:
                users_data["groups"] = {}
            if "all_users" not in users_data:
                users_data["all_users"] = {}
            
            if group_id not in users_data["groups"]:
                users_data["groups"][group_id] = {
                    "title": group_title,
                    "users": {},
                    "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                }
                logging.info(f"✅ Создана новая группа: {group_title} ({group_id})")
            
            current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            if username not in users_data["groups"][group_id]["users"]:
                users_data["groups"][group_id]["users"][username] = {
                    "full_name": full_name,
                    "added_at": current_time,
                    "last_seen": current_time
                }
                logging.info(f"✅ Добавлен пользователь {username} в группу {group_title}")
            else:
                users_data["groups"][group_id]["users"][username]["last_seen"] = current_time
            
            if username not in users_data["all_users"]:
                users_data["all_users"][username] = {
                    "full_name": full_name,
                    "first_seen": current_time,
                    "groups": [group_id],
                    "last_seen": current_time
                }
            else:
                if group_id not in users_data["all_users"][username]["groups"]:
                    users_data["all_users"][username]["groups"].append(group_id)
                users_data["all_users"][username]["last_seen"] = current_time
            
            self.save_users(users_data)
            
            config_data = self.get_config()
            if "group_chat_ids" not in config_data:
                config_data["group_chat_ids"] = []
            
            if group_id not in config_data["group_chat_ids"]:
                config_data["group_chat_ids"].append(group_id)
                self.save_config(config_data)
            
        except Exception as e:
            logging.error(f"Ошибка добавления пользователя: {e}")

    async def update_group_title(self, chat_id, title):
        """Обновляет название группы в базе"""
        try:
            group_id = str(chat_id)
            users_data = self.get_users()
            if "groups" in users_data and group_id in users_data["groups"]:
                if title is None:
                    title = f"Группа {group_id}"
                    
                old_title = users_data["groups"][group_id].get("title", "Неизвестно")
                users_data["groups"][group_id]["title"] = title
                self.save_users(users_data)
                if old_title != title:
                    logging.info(f"✅ Обновлено название группы {group_id}: {old_title} -> {title}")
        except Exception as e:
            logging.error(f"Ошибка обновления названия группы: {e}")

    def get_all_users(self):
        """Возвращает список всех пользователей системы"""
        try:
            users_data = self.get_users()
            all_users = users_data.get("all_users", {})
            # Фильтруем только строковые username
            return [username for username in all_users.keys() if isinstance(username, str)]
        except Exception as e:
            logging.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def get_user_full_name(self, username):
        """Возвращает полное имя пользователя по username"""
        try:
            # Обрабатываем случай, когда username является списком
            if isinstance(username, list):
                if username:
                    # Берем первый элемент и убираем лишние пробелы
                    username = str(username[0]).strip()
                else:
                    return "Неизвестный пользователь"
                    
            if not isinstance(username, str):
                logging.error(f"Некорректный тип username: {type(username)} - {username}")
                return str(username)
                
            users_data = self.get_users()
            user_data = users_data.get("all_users", {}).get(username)
            if user_data:
                return user_data.get("full_name", username)
            return username
        except Exception as e:
            logging.error(f"Ошибка получения полного имени для {username}: {e}")
            return str(username)

    def get_user_display_name(self, username):
        """Возвращает отображаемое имя пользователя (полное имя + username)"""
        try:
            # Обрабатываем случай, когда username является списком
            if isinstance(username, list):
                if username:
                    # Берем первый элемент и убираем лишние пробелы
                    username = str(username[0]).strip()
                else:
                    return "Неизвестный пользователь"
                    
            if not isinstance(username, str):
                logging.error(f"Некорректный тип username: {type(username)} - {username}")
                return str(username)
                
            full_name = self.get_user_full_name(username)
            if full_name == username:
                return username
            return f"{full_name} ({username})"
        except Exception as e:
            logging.error(f"Ошибка получения отображаемого имени для {username}: {e}")
            return str(username)

    async def show_my_tasks_menu(self, update: Update, context: CallbackContext):
        """Показывает меню Мои задачи"""
        try:
            # Определяем chat_id и chat_type в зависимости от типа update
            if update.callback_query:
                chat_id = update.callback_query.message.chat.id
                chat_type = update.callback_query.message.chat.type
            else:
                chat_id = update.effective_chat.id
                chat_type = update.effective_chat.type
            
            menu_text = "📋 Мои задачи\n\nВыберите тип задач для просмотра:"
            
            await self.safe_send_message(
                chat_id,
                menu_text,
                context.bot,
                reply_markup=self.get_my_tasks_keyboard(chat_type)
            )
        except Exception as e:
            logging.error(f"Ошибка в show_my_tasks_menu: {e}")
            # Пытаемся отправить сообщение любым способом
            try:
                if update.callback_query:
                    chat_id = update.callback_query.message.chat.id
                else:
                    chat_id = update.effective_chat.id
                await self.safe_send_message(
                    chat_id, 
                    "❌ Произошла ошибка при загрузке меню задач", 
                    context.bot
                )
            except Exception:
                pass

    async def show_my_active_tasks(self, update: Update, context: CallbackContext):
        """Показывает активные задачи пользователя"""
        try:
            user = update.effective_user
            chat = update.effective_chat
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            tasks_data = self.get_tasks()
            # Фильтруем только задачи текущего пользователя
            user_tasks = [task for task in tasks_data.get("tasks", []) 
                        if task.get("assigned_to") == username and task.get("status") == "active"]
            
            if not user_tasks:
                await self.safe_send_message(chat.id, "✅ У вас нет активных задач!", context.bot)
                return
            
            await self.safe_send_message(chat.id, f"📋 Ваши активные задачи ({len(user_tasks)}):", context.bot)
            
            for task in user_tasks:
                task_text = self.format_task_text(task)
                keyboard = self.get_task_actions_keyboard(task['id'], is_completed=False)
                
                await self.safe_send_message(
                    chat.id,
                    task_text,
                    context.bot,
                    reply_markup=keyboard
                )
        except Exception as e:
            logging.error(f"Ошибка в show_my_active_tasks: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке задач", context.bot)

    async def show_my_completed_tasks(self, update: Update, context: CallbackContext):
        """Показывает выполненные задачи пользователя"""
        try:
            user = update.effective_user
            chat = update.effective_chat
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            tasks_data = self.get_tasks()
            # Фильтруем только задачи текущего пользователя
            user_tasks = [task for task in tasks_data.get("tasks", []) 
                        if task.get("assigned_to") == username and task.get("status") == "completed"]
            
            if not user_tasks:
                await self.safe_send_message(chat.id, "📭 У вас нет выполненных задач!", context.bot)
                return
            
            await self.safe_send_message(chat.id, f"✅ Ваши выполненные задачи ({len(user_tasks)}):", context.bot)
            
            for task in user_tasks:
                task_text = self.format_task_text(task)
                keyboard = self.get_task_actions_keyboard(task['id'], is_completed=True)
                
                await self.safe_send_message(
                    chat.id,
                    task_text,
                    context.bot,
                    reply_markup=keyboard
                )
        except Exception as e:
            logging.error(f"Ошибка в show_my_completed_tasks: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке задач", context.bot)

    def format_task_text(self, task):
        """Форматирует текст задачи для отображения"""
        try:
            status_icon = "🟢" if task.get("status") == "completed" else "🟡"
            assigned_to = task.get('assigned_to', '')
            assigned_by = task.get('assigned_by', '')
            
            # Защита от некорректных данных
            if not isinstance(assigned_to, str):
                assigned_to = str(assigned_to)
            if not isinstance(assigned_by, str):
                assigned_by = str(assigned_by)
                
            assigned_to_display = self.get_user_display_name(assigned_to)
            assigned_by_display = self.get_user_display_name(assigned_by)
            
            if task.get("status") == "completed":
                return f"""🟢 Задача #{task.get('id', 'N/A')} (ВЫПОЛНЕНА)

📝 {task.get('task_text', '')}
⏰ Срок: {task.get('deadline', '')}
👤 Исполнитель: {assigned_to_display}
👑 Назначил: {assigned_by_display}
📅 Создана: {task.get('created_at', '')}
✅ Завершена: {task.get('completed_at', '')}
🏠 Группа: {self.get_group_name(task.get('group_id', ''))}"""
            else:
                return f"""🎯 Задача #{task.get('id', 'N/A')}

📝 {task.get('task_text', '')}
⏰ Срок: {task.get('deadline', '')}
👤 Исполнитель: {assigned_to_display}
👑 Назначил: {assigned_by_display}
📅 Создана: {task.get('created_at', '')}
🏠 Группа: {self.get_group_name(task.get('group_id', ''))}"""
        except Exception as e:
            logging.error(f"Ошибка форматирования задачи: {e}")
            return f"❌ Ошибка отображения задачи #{task.get('id', 'N/A')}"

    def get_group_name(self, group_id):
        """Возвращает название группы по ID"""
        try:
            users_data = self.get_users()
            if (users_data.get("groups") and 
                group_id in users_data["groups"] and
                "title" in users_data["groups"][group_id]):
                return users_data["groups"][group_id]["title"]
            return f"Группа {group_id}"
        except Exception:
            return f"Группа {group_id}"

    async def start_new_task(self, update: Update, context: CallbackContext):
        try:
            user = update.effective_user
            chat = update.effective_chat
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            all_users = self.get_all_users()
            
            if not all_users:
                await self.safe_send_message(
                    chat.id,
                    "❌ В системе еще нет пользователей.\n\n💡 Попросите участников написать любое сообщение в чат с ботом, чтобы они добавились в список",
                    context.bot
                )
                return
            
            display_users = []
            for user_username in all_users:
                display_text = self.get_user_display_name(user_username)
                display_users.append(display_text)
            
            # Инициализируем состояние правильно с пустым списком selected_users
            self.user_states[user.id] = {
                "step": 1, 
                "username": username,
                "chat_id": chat.id,
                "group_users": display_users,
                "group_users_usernames": all_users,
                "selected_users": [],  # Явно инициализируем пустой список
                "created_at": datetime.now()
            }
            
            logging.info(f"Инициализировано состояние для создания задачи. Пользователей доступно: {len(all_users)}")
            
            await self.show_users_keyboard(update, context, display_users, multi_select=True)
        except Exception as e:
            logging.error(f"Ошибка в start_new_task: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при создании задачи", context.bot)

    async def show_users_keyboard(self, update: Update, context: CallbackContext, users, multi_select=False):
        """Показывает клавиатуру с пользователями"""
        try:
            if not users:
                await self.safe_send_message(update.effective_chat.id, "❌ В системе нет пользователей в базе данных", context.bot)
                return
                
            keyboard = []
            
            for i in range(0, len(users), 2):
                row = []
                for j in range(2):
                    if i + j < len(users):
                        username = users[i + j]
                        row.append(username)
                if row:
                    keyboard.append(row)
            
            control_buttons = []
            if multi_select:
                control_buttons.append("✅ Завершить выбор")
            control_buttons.append("❌ Отмена")
            
            keyboard.append(control_buttons)
            
            message_text = f"👥 Выберите сотрудника из системы ({len(users)} пользователей):"
            
            # Добавляем информацию о выбранных пользователях
            if multi_select:
                user = update.effective_user
                if user.id in self.user_states:
                    selected_count = len(self.user_states[user.id].get("selected_users", []))
                    if selected_count > 0:
                        message_text = f"👥 Выберите сотрудников ({selected_count} выбрано):\n\n"
                        for selected_user in self.user_states[user.id].get("selected_users", []):
                            # Используем исправленную функцию для отображения
                            display_name = self.get_user_display_name(selected_user)
                            message_text += f"✅ {display_name}\n"
                        message_text += f"\nВсего выбрано: {selected_count}\nПродолжайте выбор или нажмите '✅ Завершить выбор'"
            
            await self.safe_send_message(
                update.effective_chat.id,
                message_text,
                context.bot,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True) if self.is_private_chat(update.effective_chat.type) else None
            )
        except Exception as e:
            logging.error(f"Ошибка в show_users_keyboard: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Ошибка при загрузке списка пользователей", context.bot)

    def get_filtered_tasks(self, task_filter='all', date_filter='all', group_id=None):
        """Возвращает отфильтрованные задачи"""
        try:
            tasks_data = self.get_tasks()
            all_tasks = tasks_data.get("tasks", [])
            filtered_tasks = []

            for task in all_tasks:
                if group_id is not None and str(task.get("group_id")) != str(group_id):
                    continue

                # Проверка статуса
                if task_filter == 'active' and task.get('status') != 'active':
                    continue
                elif task_filter == 'completed' and task.get('status') != 'completed':
                    continue
                elif task_filter == 'overdue':
                    if task.get('status') != 'active' or not self.is_task_overdue(task.get('deadline', '')):
                        continue
                
                # Проверка даты
                if date_filter != 'all':
                    task_date = self.parse_task_date(task.get('deadline', ''))
                    if not task_date:
                        continue
                    
                    today = datetime.now().date()
                    if date_filter == 'today' and task_date != today:
                        continue
                    elif date_filter == 'tomorrow' and task_date != today + timedelta(days=1):
                        continue
                    elif date_filter == 'week':
                        # Неделя с сегодняшнего дня до +6 дней
                        week_end = today + timedelta(days=6)
                        if not (today <= task_date <= week_end):
                            continue
                    elif date_filter == 'month':
                        # Текущий месяц
                        month_start = today.replace(day=1)
                        next_month = month_start.replace(month=month_start.month+1) if month_start.month < 12 else month_start.replace(year=month_start.year+1, month=1)
                        month_end = next_month - timedelta(days=1)
                        if not (month_start <= task_date <= month_end):
                            continue
                
                filtered_tasks.append(task)
            
            # Сортировка по дате (сначала ближайшие) и по ID
            filtered_tasks.sort(key=lambda x: (
                self.parse_task_date(x.get('deadline', '')) or datetime.max.date(),
                x.get('id', 0)
            ))
            
            return filtered_tasks
            
        except Exception as e:
            logging.error(f"Ошибка в get_filtered_tasks: {e}")
            return []

    def parse_task_date(self, date_str: str):
        """Парсит дату из строки, поддерживает форматы '%d.%m.%Y' и '%d.%m.%Y %H:%M:%S'"""
        try:
            # Пробуем разные форматы
            for fmt in ('%d.%m.%Y', '%d.%m.%Y %H:%M:%S'):
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    def parse_task_datetime(self, datetime_str: str):
        """Парсит дату и время из строки"""
        try:
            return datetime.strptime(datetime_str, '%d.%m.%Y %H:%M:%S')
        except Exception:
            try:
                return datetime.strptime(datetime_str, '%d.%m.%Y')
            except Exception:
                return None

    async def show_task_selection(self, update: Update, context: CallbackContext, action: str, title: str, group_id: Optional[str] = None):
        """Показывает выбор задачи с фильтрами"""
        try:
            user = update.effective_user
            chat = update.effective_chat

            self.user_states[user.id] = {
                "action": action,
                "tasks": [],
                "current_page": 0,
                "task_filter": 'all',
                "date_filter": 'all',
                "group_filter": group_id,
                "custom_title": title,
                "created_at": datetime.now()
            }

            await self.show_task_filters(update, context, title)

        except Exception as e:
            logging.error(f"Ошибка в show_task_selection: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке задач", context.bot)

    async def show_task_page(self, update: Update, context: CallbackContext, page: int, title: str):
        """Показывает страницу с задачами"""
        try:
            user = update.effective_user
            chat = update.effective_chat
            
            if user.id not in self.user_states:
                return
            
            state = self.user_states[user.id]
            tasks = state.get("tasks", [])
            
            if not tasks:
                await self.safe_send_message(chat.id, "📭 Нет задач для отображения с выбранными фильтрами", context.bot)
                return
            
            tasks_per_page = 5
            start_idx = page * tasks_per_page
            end_idx = start_idx + tasks_per_page
            page_tasks = tasks[start_idx:end_idx]
            
            total_pages = (len(tasks) + tasks_per_page - 1) // tasks_per_page
            
            message_text = f"📋 {title}\n\n"
            message_text += f"📄 Страница {page + 1} из {total_pages}\n"
            message_text += f"📊 Всего задач: {len(tasks)}\n\n"
            
            for i, task in enumerate(page_tasks, start_idx + 1):
                status_icon = "🟢" if task.get("status") == "completed" else "🟡"
                if task.get("status") == "active" and self.is_task_overdue(task.get('deadline', '')):
                    status_icon = "🔴"
                
                task_preview = task.get('task_text', '')[:50] + "..." if len(task.get('task_text', '')) > 50 else task.get('task_text', '')
                assigned_to_display = self.get_user_display_name(task.get('assigned_to', ''))
                message_text += f"{status_icon} {i}. #{task.get('id', 'N/A')} - {task_preview}\n"
                message_text += f"    👤 {assigned_to_display} | ⏰ {task.get('deadline', '')}\n\n"
            
            keyboard = []
            
            for i, task in enumerate(page_tasks, start_idx + 1):
                task_preview = task.get('task_text', '')[:20] + "..." if len(task.get('task_text', '')) > 20 else task.get('task_text', '')
                keyboard.append([f"{i}. #{task.get('id')} - {task_preview}"])
            
            nav_buttons = []
            if page > 0:
                nav_buttons.append("◀️ Предыдущая")
            if end_idx < len(tasks):
                nav_buttons.append("Следующая ▶️")
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            filter_buttons = ["🎛 Фильтры", "❌ Отмена"]
            keyboard.append(filter_buttons)
            
            await self.safe_send_message(
                chat.id,
                message_text,
                context.bot,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True) if self.is_private_chat(chat.type) else None
            )
            
            state["current_page"] = page
            
        except Exception as e:
            logging.error(f"Ошибка в show_task_page: {e}")

    async def show_task_filters(self, update: Update, context: CallbackContext, title="Фильтры задач"):
        """Показывает меню фильтров"""
        try:
            user = update.effective_user
            state = self.user_states.get(user.id, {})
            
            current_task_filter = state.get('task_filter', 'all')
            current_date_filter = state.get('date_filter', 'all')
            title = state.get('custom_title', title)

            filter_text = f"🎛 {title}\n\n"
            filter_text += f"📊 Статус: {self.get_filter_display_name(current_task_filter)}\n"
            filter_text += f"📅 Период: {self.get_filter_display_name(current_date_filter)}\n\n"
            filter_text += "Выберите фильтры:"
            
            await self.safe_send_message(
                update.effective_chat.id,
                filter_text,
                context.bot,
                reply_markup=self.get_task_filter_keyboard(update.effective_chat.type)
            )
        except Exception as e:
            logging.error(f"Ошибка в show_task_filters: {e}")

    def get_filter_display_name(self, filter_value):
        """Возвращает отображаемое имя фильтра"""
        filter_names = {
            'all': 'Все',
            'active': 'Активные',
            'completed': 'Выполненные',
            'overdue': 'Просроченные',
            'today': 'Сегодня',
            'tomorrow': 'Завтра',
            'week': 'Эта неделя',
            'month': 'Этот месяц'
        }
        return filter_names.get(filter_value, 'Все')

    async def apply_task_filter(self, update: Update, context: CallbackContext, task_filter: str, date_filter: str):
        """Применяет фильтры и обновляет список задач"""
        try:
            user = update.effective_user
            
            if user.id not in self.user_states:
                return
            
            state = self.user_states[user.id]
            group_filter = state.get("group_filter")
            state["tasks"] = self.get_filtered_tasks(task_filter, date_filter, group_filter)
            state["task_filter"] = task_filter
            state["date_filter"] = date_filter
            state["current_page"] = 0

            action = state.get("action", "")
            title = state.get("custom_title") or self.get_action_title(action)
            await self.show_task_page(update, context, 0, f"{title} - {self.get_filter_display_name(task_filter)}")

        except Exception as e:
            logging.error(f"Ошибка в apply_task_filter: {e}")

    def get_action_title(self, action: str) -> str:
        """Возвращает заголовок для действия"""
        titles = {
            "edit_task": "✏️ Редактирование задач",
            "complete_task": "✅ Завершение задач", 
            "delete_task": "🗑 Удаление задач",
            "change_deadline": "⏰ Изменение сроков",
            "reassign_task": "👤 Переназначение задач",
            "view_all_tasks": "📋 Все задачи системы",
            "view_group_tasks": "🏠 Задачи группы"
        }
        return titles.get(action, "📋 Выберите задачу")

    async def start_edit_task(self, update: Update, context: CallbackContext):
        """Начинает процесс изменения задачи с выбора из списка"""
        await self.show_task_selection(update, context, "edit_task", "✏️ Выберите задачу для редактирования")

    async def start_complete_task(self, update: Update, context: CallbackContext):
        """Начинает процесс завершения задачи с выбора из списка"""
        await self.show_task_selection(update, context, "complete_task", "✅ Выберите задачу для завершения")

    async def start_delete_task(self, update: Update, context: CallbackContext):
        """Начинает процесс удаления задачи с выбора из списка"""
        await self.show_task_selection(update, context, "delete_task", "🗑 Выберите задачу для удаления")

    async def start_change_deadline(self, update: Update, context: CallbackContext):
        """Начинает процесс изменения срока задачи с выбора из списка"""
        await self.show_task_selection(update, context, "change_deadline", "⏰ Выберите задачу для изменения срока")

    async def start_reassign_task(self, update: Update, context: CallbackContext):
        """Начинает процесс переназначения задачи с выбора из списка"""
        await self.show_task_selection(update, context, "reassign_task", "👤 Выберите задачу для переназначения")

    async def show_all_tasks_with_filters(self, update: Update, context: CallbackContext):
        """Показывает все задачи с фильтрами"""
        await self.show_task_selection(update, context, "view_all_tasks", "📋 Все задачи системы")

    async def handle_message(self, update: Update, context: CallbackContext):
        try:
            # Логирование для отладки
            user = update.effective_user
            chat = update.effective_chat
            text = update.message.text
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            logging.info(f"Обработка сообщения от {user.id}: '{text}', состояние: {self.user_states.get(user.id)}")
            
            if (datetime.now() - self.last_cleanup) > timedelta(minutes=30):
                self.cleanup_old_states()

            if chat.type in ["group", "supergroup"]:
                await self.update_group_title(chat.id, chat.title)
            
            await self.add_user_to_group(chat.id, username, user.full_name, chat.title if hasattr(chat, 'title') else "Личный чат")
            
            # Получаем состояние пользователя если оно есть
            state = self.user_states.get(user.id)
            
            # Обработка добавления пользователя вручную
            if state and state.get("action") == "add_user_manually":
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_users_management(update, context)
                    return
                
                if state.get("step") == 1:
                    if not text.startswith('@'):
                        await self.safe_send_message(chat.id, "❌ Username должен начинаться с @. Попробуйте еще раз:", context.bot)
                        return
                    
                    state["new_username"] = text
                    state["step"] = 2
                    await self.safe_send_message(
                        chat.id, 
                        "Введите полное имя пользователя:",
                        context.bot,
                        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True) if self.is_private_chat(chat.type) else None
                    )
                    return
                
                elif state.get("step") == 2:
                    full_name = text
                    new_username = state["new_username"]
                    
                    # Добавляем пользователя
                    users_data = self.get_users()
                    
                    if "all_users" not in users_data:
                        users_data["all_users"] = {}
                    if "groups" not in users_data:
                        users_data["groups"] = {}
                    
                    # Добавляем в общий список пользователей
                    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                    users_data["all_users"][new_username] = {
                        "full_name": full_name,
                        "first_seen": current_time,
                        "groups": [str(chat.id)],
                        "last_seen": current_time
                    }
                    
                    # Добавляем в текущую группу
                    group_id = str(chat.id)
                    if group_id not in users_data["groups"]:
                        users_data["groups"][group_id] = {
                            "title": chat.title if hasattr(chat, 'title') else "Личный чат",
                            "users": {},
                            "created_at": current_time
                        }
                    
                    users_data["groups"][group_id]["users"][new_username] = {
                        "full_name": full_name,
                        "added_at": current_time,
                        "last_seen": current_time
                    }
                    
                    if self.save_users(users_data):
                        await self.safe_send_message(
                            chat.id, 
                            f"✅ Пользователь {new_username} ({full_name}) успешно добавлен!",
                            context.bot
                        )
                    else:
                        await self.safe_send_message(chat.id, "❌ Ошибка при сохранении пользователя", context.bot)
                    
                    del self.user_states[user.id]
                    await self.show_users_management(update, context)
                    return

            # Если состояние не установлено - обработка основных команд
            if not state:
                if text == "📋 Мои задачи":
                    await self.show_my_tasks_menu(update, context)
                elif text == "📋 Текущие задачи":
                    await self.show_my_active_tasks(update, context)
                elif text == "✅ Выполненные задачи":
                    await self.show_my_completed_tasks(update, context)
                
                elif self.is_admin(username):
                    if text == "👑 Админ панель":
                        await self.show_admin_panel(update, context)
                    elif text == "➕ Новая задача":
                        await self.start_new_task(update, context)
                    elif text == "🏠 Главное меню":
                        await self.show_main_menu(update, context)
                    elif text == "📋 Все задачи":
                        await self.show_all_tasks_with_filters(update, context)
                    elif text == "❌ Просроченные":
                        await self.show_overdue_tasks(update, context)
                    elif text == "👥 Задачи по сотрудникам":
                        await self.show_tasks_by_users(update, context)
                    elif text == "🏘 Задачи по группам":
                        await self.show_group_tasks_overview(update, context)
                    elif text == "⚙️ Настройки уведомлений":
                        await self.show_notification_settings(update, context)
                    elif text == "👤 Управление пользователями":
                        await self.show_users_management(update, context)
                    elif text == "🛠 Управление задачами":
                        await self.show_task_management(update, context)
                    elif text == "👑 Управление администраторами":
                        await self.show_admin_management(update, context)
                    elif text == "✏️ Изменить задачу":
                        await self.start_edit_task(update, context)
                    elif text == "✅ Завершить задачу":
                        await self.start_complete_task(update, context)
                    elif text == "🗑 Удалить задачу":
                        await self.start_delete_task(update, context)
                    elif text == "⏰ Изменить срок":
                        await self.start_change_deadline(update, context)
                    elif text == "👤 Переназначить задачу":
                        await self.start_reassign_task(update, context)
                    elif text == "🔙 Назад в админку":
                        await self.show_admin_panel(update, context)
                    elif text == "➕ Добавить пользователя":
                        await self.start_add_user_manually(update, context)
                    elif text == "🗑 Удалить пользователя":
                        await self.start_remove_user(update, context)
                    elif text == "📋 Список пользователей":
                        await self.show_all_users(update, context)
                    elif text == "➕ Добавить администратора":
                        await self.start_add_admin(update, context)
                    elif text == "🗑 Удалить администратора":
                        await self.start_remove_admin(update, context)
                    elif text == "📋 Список администраторов":
                        await self.show_admin_list(update, context)
                    elif text.startswith("/add_user"):
                        await self.add_user_manually(update, context)
                return

            # Если мы дошли сюда, значит state существует
            current_action = state.get("action", "")
            
            # Обработка управления администраторами
            if current_action == "add_admin":
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_admin_management(update, context)
                    return
                
                if state.get("step") == 1:
                    if not text.startswith('@'):
                        await self.safe_send_message(chat.id, "❌ Username должен начинаться с @. Попробуйте еще раз:", context.bot)
                        return
                    
                    new_admin = text
                    config_data = self.get_config()
                    if "admins" not in config_data:
                        config_data["admins"] = []
                    
                    if new_admin in config_data["admins"]:
                        await self.safe_send_message(chat.id, f"✅ {new_admin} уже администратор", context.bot)
                    else:
                        config_data["admins"].append(new_admin)
                        if self.save_config(config_data):
                            await self.safe_send_message(chat.id, f"✅ {new_admin} добавлен как администратор", context.bot)
                        else:
                            await self.safe_send_message(chat.id, "❌ Ошибка сохранения", context.bot)
                    
                    del self.user_states[user.id]
                    await self.show_admin_management(update, context)
                return

            elif current_action == "remove_admin":
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_admin_management(update, context)
                    return
                
                removable_admins = state.get("removable_admins", [])
                if text in removable_admins:
                    config_data = self.get_config()
                    if text in config_data.get("admins", []):
                        config_data["admins"].remove(text)
                        if self.save_config(config_data):
                            await self.safe_send_message(chat.id, f"✅ {text} удален из администраторов", context.bot)
                        else:
                            await self.safe_send_message(chat.id, "❌ Ошибка сохранения", context.bot)
                    else:
                        await self.safe_send_message(chat.id, "❌ Администратор не найден в конфиге", context.bot)
                else:
                    await self.safe_send_message(chat.id, "❌ Администратор не найден. Выберите из списка:", context.bot)
                    return
                
                del self.user_states[user.id]
                await self.show_admin_management(update, context)
                return

            # Обработка выбора задач с фильтрами
            if current_action in ["edit_task", "complete_task", "delete_task", "change_deadline", "reassign_task", "view_all_tasks", "view_group_tasks"]:
                if text == "🎛 Фильтры":
                    title = state.get("custom_title") or self.get_action_title(current_action)
                    await self.show_task_filters(update, context, title)
                    return
                elif text == "◀️ Предыдущая":
                    title = state.get("custom_title") or self.get_action_title(current_action)
                    await self.show_task_page(update, context, state["current_page"] - 1, title)
                    return
                elif text == "Следующая ▶️":
                    title = state.get("custom_title") or self.get_action_title(current_action)
                    await self.show_task_page(update, context, state["current_page"] + 1, title)
                    return
                elif text == "🔙 Назад к списку":
                    title = state.get("custom_title") or self.get_action_title(current_action)
                    await self.show_task_page(update, context, 0, title)
                    return
                elif text == "❌ Отмена":
                    del self.user_states[user.id]
                    if current_action in ["view_all_tasks", "view_group_tasks"]:
                        await self.show_admin_panel(update, context)
                    else:
                        await self.show_task_management(update, context)
                    return
                
                elif text in ["🎯 Все задачи", "🟡 Активные", "🟢 Выполненные", "🔴 Просроченные"]:
                    task_filter_map = {
                        "🎯 Все задачи": "all",
                        "🟡 Активные": "active", 
                        "🟢 Выполненные": "completed",
                        "🔴 Просроченные": "overdue"
                    }
                    current_date_filter = state.get('date_filter', 'all')
                    await self.apply_task_filter(update, context, task_filter_map[text], current_date_filter)
                    return
                
                elif text in ["📅 Сегодня", "📅 Завтра", "📅 Эта неделя", "📅 Этот месяц"]:
                    date_filter_map = {
                        "📅 Сегодня": "today",
                        "📅 Завтра": "tomorrow", 
                        "📅 Эта неделя": "week",
                        "📅 Этот месяц": "month"
                    }
                    current_task_filter = state.get('task_filter', 'all')
                    await self.apply_task_filter(update, context, current_task_filter, date_filter_map[text])
                    return
                
                elif text.startswith(tuple(str(i) for i in range(1, 100))) and '.' in text:
                    try:
                        task_num = int(text.split('.')[0])
                        tasks = state.get("tasks", [])
                        current_page = state.get("current_page", 0)
                        tasks_per_page = 5
                        start_idx = current_page * tasks_per_page
                        
                        if 1 <= task_num <= len(tasks):
                            actual_index = task_num - 1
                            selected_task = tasks[actual_index]
                            task_id = selected_task.get('id')
                            
                            if current_action == "edit_task":
                                await self.start_edit_task_description(update, context, task_id)
                            elif current_action == "complete_task":
                                await self.complete_task_direct(update, context, task_id)
                                del self.user_states[user.id]  # Удаляем состояние только после завершения
                            elif current_action == "delete_task":
                                await self.delete_task_direct(update, context, task_id)
                                del self.user_states[user.id]  # Удаляем состояние только после завершения
                            elif current_action == "change_deadline":
                                await self.start_change_deadline_for_task(update, context, task_id)
                            elif current_action == "reassign_task":
                                await self.start_reassign_task_for_task(update, context, task_id)
                            elif current_action == "view_all_tasks":
                                await self.show_task_details(update, context, task_id)
                            elif current_action == "view_group_tasks":
                                await self.show_task_details(update, context, task_id)
                                # Для view_all_tasks состояние не удаляем, чтобы можно было посмотреть другие задачи
                                
                    except (ValueError, IndexError) as e:
                        await self.safe_send_message(chat.id, "❌ Неверный номер задачи. Выберите из списка:", context.bot)
                    return

            current_step = state.get("step")
            
            # Создание новой задачи
            if current_step == 1:
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_main_menu(update, context)
                elif text == "✅ Завершить выбор":
                    logging.info(f"Завершение выбора пользователей. Текущий selected_users: {state.get('selected_users', [])}")
                    if not state.get("selected_users"):
                        await self.safe_send_message(chat.id, "❌ Вы не выбрали ни одного сотрудника. Выберите хотя бы одного:", context.bot)
                        await self.show_users_keyboard(update, context, state["group_users"], multi_select=True)
                    else:
                        state["step"] = 2
                        await self.safe_send_message(
                            chat.id,
                            "📝 Введите описание задачи:",
                            context.bot,
                            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True) if self.is_private_chat(chat.type) else None
                        )
                else:
                    selected_username = None
                    logging.info(f"Поиск пользователя по тексту: '{text}'")
                    for i, display_user in enumerate(state["group_users"]):
                        if text == display_user:
                            selected_username = state["group_users_usernames"][i]
                            logging.info(f"Найден пользователь: {display_user} -> {selected_username}")
                            break
                    
                    if selected_username:
                        if "selected_users" not in state:
                            state["selected_users"] = []
                            logging.info("Инициализирован пустой список selected_users")
                        
                        if selected_username in state["selected_users"]:
                            state["selected_users"].remove(selected_username)
                            logging.info(f"Удален пользователь из выбора: {selected_username}. Текущий выбор: {state['selected_users']}")
                        else:
                            state["selected_users"].append(selected_username)
                            logging.info(f"Добавлен пользователь в выбор: {selected_username}. Текущий выбор: {state['selected_users']}")
                        
                        await self.show_users_keyboard(update, context, state["group_users"], multi_select=True)
                    else:
                        logging.warning(f"Пользователь не найден по тексту: '{text}'")
                        await self.safe_send_message(chat.id, "❌ Пользователь не найден. Выберите из списка:", context.bot)
                        await self.show_users_keyboard(update, context, state["group_users"], multi_select=True)
            
            elif current_step == 2:
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_main_menu(update, context)
                    return
                else:
                    state["task_text"] = text
                    state["step"] = 3
                    
                    groups = self.get_all_groups()
                    if groups and len(groups) > 1:
                        await self.show_groups_selection(update, context, groups)
                    else:
                        state["selected_group"] = list(groups.keys())[0] if groups else str(chat.id)
                        await self.show_deadline_selection(update, context)
            
            elif current_step == 3:
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_main_menu(update, context)
                else:
                    title_to_id_map = state.get("title_to_id_map", {})
                    selected_group_id = title_to_id_map.get(text)
                    
                    if selected_group_id:
                        state["selected_group"] = selected_group_id
                        await self.show_deadline_selection(update, context)
                    else:
                        await self.safe_send_message(chat.id, "❌ Группа не найдена. Выберите из списка:", context.bot)
            
            elif current_step == 4:
                deadline_map = {
                    "⏰ Сегодня": (datetime.now()).strftime("%d.%m.%Y"),
                    "⏰ Завтра": (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y"),
                    "⏰ Через 3 дня": (datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y"),
                    "⏰ Через неделю": (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
                }
                
                if text in deadline_map:
                    await self.create_task(update, context, state, deadline_map[text])
                    del self.user_states[user.id]
                elif text == "📅 Указать свою дату":
                    state["step"] = 5
                    await self.safe_send_message(
                        chat.id, 
                        "📅 Введите дату в формате ДД.ММ.ГГГГ:\nНапример: 25.12.2024", 
                        context.bot,
                        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True) if self.is_private_chat(chat.type) else None
                    )
                elif text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_main_menu(update, context)
                else:
                    await self.safe_send_message(chat.id, "❌ Неверный срок. Выберите из списка:", context.bot)
            
            elif current_step == 5:
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_main_menu(update, context)
                elif self.is_valid_date(text):
                    await self.create_task(update, context, state, text)
                    del self.user_states[user.id]
                else:
                    await self.safe_send_message(chat.id, "❌ Неверный формат даты или дата в прошлом. Введите в формате ДД.ММ.ГГГГ:", context.bot)
            
            # Обработка редактирования описания задачи
            elif state.get("action") == "edit_task_description":
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_task_management(update, context)
                    return
                
                task_id = state.get("task_id")
                task = self.find_task_by_id(task_id)
                
                if task:
                    tasks_data = self.get_tasks()
                    task_to_update = self.find_task_by_id_in_data(tasks_data, task_id)
                    
                    if task_to_update:
                        old_text = task_to_update.get("task_text", "")
                        task_to_update["task_text"] = text
                        
                        if self.save_tasks(tasks_data):
                            await self.safe_send_message(
                                chat.id,
                                f"✅ Описание задачи #{task_id} обновлено!\n\nБыло: {old_text}\nСтало: {text}",
                                context.bot
                            )
                            
                            config_data = self.get_config()
                            if config_data.get("notifications", {}).get("task_created", True):
                                await self.safe_send_message(
                                    task.get("group_id"),
                                    f"📝 Задача обновлена!\n\n🆔 #{task_id}\n📝 Новое описание: {text}\n👤 Исполнитель: {self.get_user_display_name(task.get('assigned_to', ''))}",
                                    context.bot
                                )
                        else:
                            await self.safe_send_message(chat.id, "❌ Ошибка сохранения изменений", context.bot)
                
                del self.user_states[user.id]
                await self.show_task_management(update, context)
            
            # Обработка изменения срока задачи (стандартные сроки)
            elif state.get("action") == "change_deadline_for_task":
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_task_management(update, context)
                    return
                
                deadline_map = {
                    "⏰ Сегодня": (datetime.now()).strftime("%d.%m.%Y"),
                    "⏰ Завтра": (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y"),
                    "⏰ Через 3 дня": (datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y"),
                    "⏰ Через неделю": (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
                }
                
                if text in deadline_map:
                    task_id = state.get("task_id")
                    await self.change_deadline_direct(update, context, task_id, deadline_map[text])
                elif text == "📅 Указать свою дату":
                    state["step"] = 1
                    await self.safe_send_message(
                        chat.id, 
                        "📅 Введите дату в формате ДД.ММ.ГГГГ:\nНапример: 25.12.2024", 
                        context.bot,
                        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True) if self.is_private_chat(chat.type) else None
                    )
                else:
                    await self.safe_send_message(chat.id, "❌ Неверный срок. Выберите из списка:", context.bot)
            
            # Обработка ввода пользовательской даты для изменения срока
            elif state.get("action") == "change_deadline_for_task" and state.get("step") == 1:
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_task_management(update, context)
                elif self.is_valid_date(text):
                    task_id = state.get("task_id")
                    await self.change_deadline_direct(update, context, task_id, text)
                else:
                    await self.safe_send_message(chat.id, "❌ Неверный формат даты или дата в прошлом. Введите в формате ДД.ММ.ГГГГ:", context.bot)
            
            # Обработка удаления пользователя
            elif state.get("action") == "remove_user":
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_users_management(update, context)
                    return
                
                selected_username = None
                for i, display_user in enumerate(state.get("available_users", [])):
                    if text == display_user:
                        selected_username = state["available_usernames"][i]
                        break
                
                if selected_username:
                    users_data = self.get_users()
                    if selected_username in users_data.get("all_users", {}):
                        del users_data["all_users"][selected_username]
                        for group_id, group_info in users_data.get("groups", {}).items():
                            if selected_username in group_info.get("users", {}):
                                del group_info["users"][selected_username]
                        
                        self.save_users(users_data)
                        await self.safe_send_message(chat.id, f"✅ Пользователь {selected_username} удален из системы!", context.bot)
                    else:
                        await self.safe_send_message(chat.id, "❌ Пользователь не найден в системе", context.bot)
                else:
                    await self.safe_send_message(chat.id, "❌ Пользователь не найден. Выберите из списка:", context.bot)
                    await self.show_users_keyboard(update, context, state.get("available_users", []))
                    return
                
                del self.user_states[user.id]
                await self.show_users_management(update, context)
            
            # Обработка переназначения задачи
            elif state.get("action") == "reassign_task_for_task":
                if text == "❌ Отмена":
                    del self.user_states[user.id]
                    await self.show_task_management(update, context)
                    return
                elif text == "✅ Завершить выбор":
                    if not state.get("selected_users"):
                        await self.safe_send_message(chat.id, "❌ Вы не выбрали ни одного сотрудника. Выберите хотя бы одного:", context.bot)
                        await self.show_users_keyboard(update, context, state.get("available_users", []), multi_select=True)
                    else:
                        task_id = state.get("task_id")
                        selected_users = state.get("selected_users", [])
                        username = state.get("username")
                        
                        task = self.find_task_by_id(task_id)
                        if task:
                            tasks_data = self.get_tasks()
                            old_user = task.get("assigned_to", "")
                            
                            # Удаляем оригинальную задачу
                            tasks_data["tasks"] = [t for t in tasks_data.get("tasks", []) if t.get("id") != task_id]
                            
                            created_count = 0
                            for new_user in selected_users:
                                new_task_id = self.get_next_task_id()
                                new_task = task.copy()
                                new_task["id"] = new_task_id
                                new_task["assigned_to"] = new_user
                                new_task["assigned_by"] = username
                                new_task["created_at"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                                new_task["status"] = "active"
                                new_task["completed_at"] = ""
                                
                                tasks_data["tasks"].append(new_task)
                                created_count += 1
                            
                            if self.save_tasks(tasks_data):
                                await self.safe_send_message(
                                    chat.id,
                                    f"✅ Задача #{task_id} переназначена на {created_count} пользователей!",
                                    context.bot
                                )
                                
                                config_data = self.get_config()
                                if config_data.get("notifications", {}).get("task_created", True):
                                    assigned_users = ", ".join([self.get_user_display_name(user) for user in selected_users])
                                    await self.safe_send_message(
                                        task.get("group_id"),
                                        f"👤 Задача переназначена!\n\n🆔 #{task_id} (и копии)\n📝 {task.get('task_text', '')}\n⏰ Срок: {task.get('deadline', '')}\n👤 Новые исполнители: {assigned_users}",
                                        context.bot
                                    )
                            else:
                                await self.safe_send_message(chat.id, "❌ Ошибка сохранения изменений", context.bot)
                        
                        del self.user_states[user.id]
                        await self.show_task_management(update, context)
                else:
                    selected_username = None
                    for i, display_user in enumerate(state.get("available_users", [])):
                        if text == display_user:
                            selected_username = state["available_usernames"][i]
                            break
                    
                    if selected_username:
                        if "selected_users" not in state:
                            state["selected_users"] = []
                        
                        if selected_username in state["selected_users"]:
                            state["selected_users"].remove(selected_username)
                            await self.safe_send_message(chat.id, f"❌ {selected_username} удален из выбора", context.bot)
                        else:
                            state["selected_users"].append(selected_username)
                            await self.safe_send_message(chat.id, f"✅ {selected_username} добавлен в выбор", context.bot)
                        
                        # Обновляем клавиатуру с текущим состоянием выбора
                        await self.show_users_keyboard(update, context, state.get("available_users", []), multi_select=True)
                    else:
                        await self.safe_send_message(chat.id, "❌ Пользователь не найден. Выберите из списка:", context.bot)
                        await self.show_users_keyboard(update, context, state.get("available_users", []), multi_select=True)
            
        except Exception as e:
            logging.error(f"Ошибка в handle_message: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при обработке сообщения", context.bot)

    async def start_edit_task_description(self, update: Update, context: CallbackContext, task_id: int):
        """Начинает процесс изменения описания задачи"""
        try:
            task = self.find_task_by_id(task_id)
            if not task:
                await self.safe_send_message(update.effective_chat.id, "❌ Задача не найдена", context.bot)
                await self.show_task_management(update, context)
                return

            # Очищаем предыдущие состояния
            user_id = update.effective_user.id
            if user_id in self.user_states:
                del self.user_states[user_id]

            # Устанавливаем новое состояние для редактирования
            self.user_states[user_id] = {
                "action": "edit_task_description",
                "task_id": task_id,
                "created_at": datetime.now()
            }
            
            # Логирование для отладки
            logging.info(f"Установлено состояние редактирования для пользователя {user_id}, задача #{task_id}")
            
            await self.safe_send_message(
                update.effective_chat.id,
                f"✏️ Редактирование задачи #{task_id}\n\nТекущее описание: {task.get('task_text', '')}\n\nВведите новое описание:",
                context.bot,
                reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True) if self.is_private_chat(update.effective_chat.type) else None
            )
        except Exception as e:
            logging.error(f"Ошибка в start_edit_task_description: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка", context.bot)

    async def start_change_deadline_for_task(self, update: Update, context: CallbackContext, task_id: int):
        """Начинает процесс изменения срока для конкретной задачи"""
        try:
            task = self.find_task_by_id(task_id)
            if not task:
                await self.safe_send_message(update.effective_chat.id, "❌ Задача не найдена", context.bot)
                await self.show_task_management(update, context)
                return

            # Очищаем предыдущие состояния
            user_id = update.effective_user.id
            if user_id in self.user_states:
                del self.user_states[user_id]

            self.user_states[user_id] = {
                "action": "change_deadline_for_task",
                "task_id": task_id,
                "created_at": datetime.now()
            }
            
            deadline_keyboard = [
                ["⏰ Сегодня", "⏰ Завтра"],
                ["⏰ Через 3 дня", "⏰ Через неделю"],
                ["📅 Указать свою дату"],
                ["❌ Отмена"]
            ]
            
            await self.safe_send_message(
                update.effective_chat.id,
                f"⏰ Изменение срока для задачи #{task_id}\n\nТекущий срок: {task.get('deadline', '')}\n\nВыберите новый срок:",
                context.bot,
                reply_markup=ReplyKeyboardMarkup(deadline_keyboard, resize_keyboard=True) if self.is_private_chat(update.effective_chat.type) else None
            )
        except Exception as e:
            logging.error(f"Ошибка в start_change_deadline_for_task: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка", context.bot)

    async def complete_task_safe(self, task_id: int, username: str, bot):
        """Безопасное завершение задачи"""
        try:
            tasks_data = self.get_tasks()
            task_to_complete = self.find_task_by_id_in_data(tasks_data, task_id)
            
            if not task_to_complete:
                return False
                
            task_to_complete["status"] = "completed"
            task_to_complete["completed_at"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            if not self.save_tasks(tasks_data):
                return False
            
            # Отправляем уведомление в группу если нужно
            config_data = self.get_config()
            if (task_to_complete.get("group_id") and 
                config_data.get("notifications", {}).get("task_completed", True)):
                await self.safe_send_message(
                    task_to_complete["group_id"],
                    f"✅ Задача выполнена!\n\n👤 {self.get_user_display_name(username)} завершил(а) задачу:\n📝 {task_to_complete.get('task_text', '')}",
                    bot
                )
            
            return True
        except Exception as e:
            logging.error(f"Ошибка в complete_task_safe: {e}")
            return False

    async def complete_task_direct(self, update: Update, context: CallbackContext, task_id: int):
        """Непосредственно завершает задачу"""
        user = update.effective_user
        username = f"@{user.username}" if user.username else f"user_{user.id}"
        
        success = await self.complete_task_safe(task_id, username, context.bot)
        
        if success:
            await self.safe_send_message(
                update.effective_chat.id,
                f"✅ Задача #{task_id} завершена!",
                context.bot
            )
        else:
            await self.safe_send_message(update.effective_chat.id, "❌ Ошибка сохранения изменений", context.bot)
        
        # Показываем меню управления задачами
        await self.show_task_management(update, context)

    async def reopen_task_direct(self, update: Update, context: CallbackContext, task_id: int):
        """Открывает завершенную задачу заново"""
        task = self.find_task_by_id(task_id)
        if task:
            tasks_data = self.get_tasks()
            task_to_reopen = self.find_task_by_id_in_data(tasks_data, task_id)
            
            if task_to_reopen:
                task_to_reopen["status"] = "active"
                task_to_reopen["completed_at"] = ""
                
                if self.save_tasks(tasks_data):
                    await self.safe_send_message(
                        update.effective_chat.id,
                        f"🔄 Задача #{task_id} открыта заново!",
                        context.bot
                    )
                    
                    config_data = self.get_config()
                    if config_data.get("notifications", {}).get("task_created", True):
                        await self.safe_send_message(
                            task.get("group_id"),
                            f"🔄 Задача открыта заново!\n\n🆔 #{task_id}\n📝 {task.get('task_text', '')}\n👤 Исполнитель: {self.get_user_display_name(task.get('assigned_to', ''))}",
                            context.bot
                        )
                else:
                    await self.safe_send_message(update.effective_chat.id, "❌ Ошибка сохранения изменений", context.bot)
            
            await self.show_my_tasks_menu(update, context)

    async def delete_task_direct(self, update: Update, context: CallbackContext, task_id: int):
        """Непосредственно удаляет задачу"""
        task = self.find_task_by_id(task_id)
        if task:
            tasks_data = self.get_tasks()
            tasks_data["tasks"] = [t for t in tasks_data.get("tasks", []) if t.get("id") != task_id]
            
            if self.save_tasks(tasks_data):
                await self.safe_send_message(
                    update.effective_chat.id,
                    f"🗑 Задача #{task_id} удалена!",
                    context.bot
                )
                
                config_data = self.get_config()
                if config_data.get("notifications", {}).get("task_deleted", True):
                    await self.safe_send_message(
                        task.get("group_id"),
                        f"🗑 Задача удалена!\n\nАдминистратор удалил задачу:\n📝 {task.get('task_text', '')}",
                        context.bot
                    )
            else:
                await self.safe_send_message(update.effective_chat.id, "❌ Ошибка сохранения изменений", context.bot)
        
        await self.show_my_tasks_menu(update, context)

    async def change_deadline_direct(self, update: Update, context: CallbackContext, task_id: int, new_deadline: str):
        """Непосредственно изменяет срок задачи"""
        try:
            task = self.find_task_by_id(task_id)
            if not task:
                await self.safe_send_message(update.effective_chat.id, "❌ Задача не найдена", context.bot)
                # Удаляем состояние если задача не найдена
                if update.effective_user.id in self.user_states:
                    del self.user_states[update.effective_user.id]
                await self.show_task_management(update, context)
                return

            old_deadline = task.get("deadline", "")
            
            tasks_data = self.get_tasks()
            task_to_update = self.find_task_by_id_in_data(tasks_data, task_id)
            
            if not task_to_update:
                await self.safe_send_message(update.effective_chat.id, "❌ Задача не найдена для обновления", context.bot)
                # Удаляем состояние если задача не найдена
                if update.effective_user.id in self.user_states:
                    del self.user_states[update.effective_user.id]
                await self.show_task_management(update, context)
                return
            
            task_to_update["deadline"] = new_deadline
            
            if not self.save_tasks(tasks_data):
                await self.safe_send_message(update.effective_chat.id, "❌ Ошибка сохранения изменений", context.bot)
                # Удаляем состояние при ошибке сохранения
                if update.effective_user.id in self.user_states:
                    del self.user_states[update.effective_user.id]
                await self.show_task_management(update, context)
                return
            
            # Успешное обновление
            success_message = f"✅ Срок задачи #{task_id} изменен!\n\nБыло: {old_deadline}\nСтало: {new_deadline}"
            await self.safe_send_message(update.effective_chat.id, success_message, context.bot)
            
            # Отправляем уведомление в группу если нужно
            config_data = self.get_config()
            if (task.get("group_id") and 
                config_data.get("notifications", {}).get("task_created", True)):
                notification_text = (
                    f"⏰ Срок задачи изменен!\n\n"
                    f"🆔 #{task_id}\n"
                    f"📝 {task.get('task_text', '')}\n"
                    f"👤 Исполнитель: {self.get_user_display_name(task.get('assigned_to', ''))}\n"
                    f"⏰ Новый срок: {new_deadline}"
                )
                await self.safe_send_message(task.get("group_id"), notification_text, context.bot)
            
            # Удаляем состояние пользователя
            if update.effective_user.id in self.user_states:
                del self.user_states[update.effective_user.id]
                
        except Exception as e:
            logging.error(f"Ошибка в change_deadline_direct: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при изменении срока", context.bot)
        finally:
            # Всегда показываем меню управления задачами
            await self.show_task_management(update, context)

    async def start_reassign_task_for_task(self, update: Update, context: CallbackContext, task_id: int):
        """Начинает процесс переназначения для конкретной задачи с множественным выбором"""
        try:
            task = self.find_task_by_id(task_id)
            if not task:
                await self.safe_send_message(update.effective_chat.id, "❌ Задача не найдена", context.bot)
                await self.show_task_management(update, context)
                return

            users_data = self.get_users()
            all_users = list(users_data.get("all_users", {}).keys())
            display_users = []
            for username in all_users:
                display_text = self.get_user_display_name(username)
                display_users.append(display_text)
            
            # Очищаем предыдущие состояния
            user_id = update.effective_user.id
            if user_id in self.user_states:
                del self.user_states[user_id]

            self.user_states[user_id] = {
                "action": "reassign_task_for_task",
                "task_id": task_id,
                "available_users": display_users,
                "available_usernames": all_users,
                "selected_users": [],
                "username": f"@{update.effective_user.username}" if update.effective_user.username else f"user_{update.effective_user.id}",
                "created_at": datetime.now()
            }
            
            if all_users:
                await self.show_users_keyboard(update, context, display_users, multi_select=True)
            else:
                await self.safe_send_message(
                    update.effective_chat.id,
                    "❌ В системе нет пользователей для переназначения",
                    context.bot
                )
        except Exception as e:
            logging.error(f"Ошибка в start_reassign_task_for_task: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка", context.bot)

    async def show_task_details(self, update: Update, context: CallbackContext, task_id: int):
        """Показывает детали задачи"""
        task = self.find_task_by_id(task_id)
        if task:
            task_text = self.format_task_text(task)
            await self.safe_send_message(
                update.effective_chat.id,
                task_text,
                context.bot
            )

    def find_task_by_id(self, task_id):
        """Находит задачу по ID"""
        tasks_data = self.get_tasks()
        return self.find_task_by_id_in_data(tasks_data, task_id)

    def find_task_by_id_in_data(self, tasks_data, task_id):
        """Находит задачу по ID в данных"""
        for task in tasks_data.get("tasks", []):
            if task.get("id") == task_id:
                return task
        return None

    async def show_task_management(self, update: Update, context: CallbackContext):
        """Показывает меню управления задачами"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            management_text = "🛠 Управление задачами\n\nВыберите действие:"
            await self.safe_send_message(
                update.effective_chat.id,
                management_text,
                context.bot,
                reply_markup=self.get_task_management_keyboard(update.effective_chat.type)
            )
        except Exception as e:
            logging.error(f"Ошибка в show_task_management: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке управления задачами", context.bot)

    async def show_groups_selection(self, update: Update, context: CallbackContext, groups):
        """Показывает выбор группы для уведомления, исключая личные чаты кроме текущего"""
        try:
            if not groups:
                await self.safe_send_message(
                    update.effective_chat.id,
                    "❌ В системе нет групп. Используется текущий чат для уведомлений.",
                    context.bot
                )
                return

            current_chat_id = str(update.effective_chat.id)
            keyboard = []

            # Фильтруем группы: оставляем только текущий чат (если он личный) и групповые чаты
            filtered_groups = {}
            for group_id, group_info in groups.items():
                # Если это текущий чат, оставляем
                if group_id == current_chat_id:
                    filtered_groups[group_id] = group_info
                # Иначе оставляем только групповые чаты (с отрицательным ID)
                elif int(group_id) < 0:
                    filtered_groups[group_id] = group_info

            if not filtered_groups:
                state = self.user_states[update.effective_user.id]
                state["selected_group"] = current_chat_id
                await self.show_deadline_selection(update, context)
                return

            # Сортируем группы по названию
            sorted_groups = sorted(filtered_groups.items(), key=lambda x: x[1].get("title", "").lower())

            title_to_id_map = {}
            for group_id, group_info in sorted_groups:
                group_title = group_info.get("title", f"Группа {group_id}")
                if group_title is None:
                    group_title = f"Группа {group_id}"

                if len(group_title) > 30:
                    display_title = group_title[:27] + "..."
                else:
                    display_title = group_title

                if not isinstance(display_title, str):
                    display_title = str(display_title)

                keyboard.append([display_title])
                title_to_id_map[display_title] = group_id

            keyboard.append(["❌ Отмена"])

            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True) if self.is_private_chat(update.effective_chat.type) else None

            await self.safe_send_message(
                update.effective_chat.id,
                "🌐 Выберите группу для отправки уведомления:",
                context.bot,
                reply_markup=reply_markup
            )

            if update.effective_user.id in self.user_states:
                self.user_states[update.effective_user.id]["title_to_id_map"] = title_to_id_map
                self.user_states[update.effective_user.id]["step"] = 3

        except Exception as e:
            logging.error(f"Ошибка в show_groups_selection: {e}")
            await self.safe_send_message(
                update.effective_chat.id,
                "❌ Ошибка при загрузке списка групп",
                context.bot
            )

    async def show_deadline_selection(self, update: Update, context: CallbackContext):
        """Показывает выбор срока выполнения"""
        try:
            deadline_keyboard = [
                ["⏰ Сегодня", "⏰ Завтра"],
                ["⏰ Через 3 дня", "⏰ Через неделю"],
                ["📅 Указать свою дату"],
                ["❌ Отмена"]
            ]
            
            await self.safe_send_message(
                update.effective_chat.id,
                "⏰ Выберите срок выполнения задачи:",
                context.bot,
                reply_markup=ReplyKeyboardMarkup(deadline_keyboard, resize_keyboard=True) if self.is_private_chat(update.effective_chat.type) else None
            )
            
            if update.effective_user.id in self.user_states:
                self.user_states[update.effective_user.id]["step"] = 4
        except Exception as e:
            logging.error(f"Ошибка в show_deadline_selection: {e}")

# В функции create_task в bot.py исправляем следующее:

        async def create_task(self, update: Update, context: CallbackContext, state: dict, deadline: str):
            """Создает задачу с уникальными ID для каждой"""
            try:
                # Проверяем, что есть выбранные пользователи
                selected_users = state.get("selected_users", [])
                if not selected_users:
                    await self.safe_send_message(update.effective_chat.id, "❌ Не выбраны пользователи для назначения задачи", context.bot)
                    return
                    
                tasks_data = self.get_tasks()
                
                created_count = 0
                
                for selected_user in selected_users:
                    # ГЕНЕРИРУЕМ УНИКАЛЬНЫЙ ID ДЛЯ КАЖДОЙ ЗАДАЧИ
                    task_id = self.get_next_task_id()
                    
                    new_task = {
                        "id": task_id,  # Уникальный ID для каждой задачи
                        "assigned_to": selected_user,
                        "assigned_by": state["username"],
                        "task_text": state["task_text"],
                        "deadline": deadline,
                        "status": "active",
                        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                        "completed_at": "",
                        "group_id": state["selected_group"]
                    }
                    
                    if "tasks" not in tasks_data:
                        tasks_data["tasks"] = []
                    tasks_data["tasks"].append(new_task)
                    created_count += 1
                
                if not self.save_tasks(tasks_data):
                    await self.safe_send_message(update.effective_chat.id, "❌ Ошибка сохранения задач", context.bot)
                    return
                
                # Остальной код без изменений...
                config_data = self.get_config()
                if config_data.get("notifications", {}).get("task_created", True):
                    # Формируем список исполнителей с username
                    assigned_users_list = []
                    for user in selected_users:
                        assigned_users_list.append(self.get_user_display_name(user))
                    
                    assigned_users = ", ".join(assigned_users_list)
                    assigned_by_display = self.get_user_display_name(state['username'])
                    
                    group_msg = f"""🎯 Новая задача!

        👥 Исполнители: {assigned_users}
        📝 Задача: {state['task_text']}
        ⏰ Срок: {deadline}
        👑 Назначил: {assigned_by_display}

        Не забудьте выполнить задачу! ✅"""
                    
                    await self.safe_send_message(
                        state["selected_group"],
                        group_msg,
                        context.bot
                    )
                
                await self.safe_send_message(
                    update.effective_chat.id,
                    f"✅ Создано {created_count} задач!" + (" Уведомление отправлено в группу!" if config_data.get("notifications", {}).get("task_created", True) else ""),
                    context.bot,
                    reply_markup=self.get_main_keyboard(self.is_admin(state["username"]), update.effective_chat.type)
                )
            except Exception as e:
                logging.error(f"Ошибка в create_task: {e}")
                await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при создании задач", context.bot)
        
        def is_valid_date(self, date_str):
            """Проверяет корректность даты и что она не в прошлом"""
            try:
                date_obj = datetime.strptime(date_str, '%d.%m.%Y')
                today = datetime.now()
                deadline = deadline.replace(hour=0, minute=0, second=0, microsecond=0)
                today = today.replace(hour=0, minute=0, second=0, microsecond=0)
                return date_obj >= today
            except ValueError:
                return False

    async def handle_callback(self, update: Update, context: CallbackContext):
        try:
            query = update.callback_query
            await query.answer()
            
            callback_data = query.data
            user = query.from_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            is_admin_user = self.is_admin(username)
            
            if callback_data.startswith('complete:'):
                task_id = int(callback_data.split(':')[1])
                task = self.find_task_by_id(task_id)
                
                if not task:
                    await query.edit_message_text("❌ Задача не найдена!")
                    return
                    
                # Проверка прав: пользователь может завершать только свои задачи
                if task.get("assigned_to") != username and not is_admin_user:
                    await query.edit_message_text("❌ Вы можете завершать только свои задачи!")
                    return
                
                success = await self.complete_task_safe(task_id, username, context.bot)
                
                if success:
                    updated_task = self.find_task_by_id(task_id)
                    if updated_task:
                        task_text = self.format_task_text(updated_task)
                        keyboard = self.get_task_actions_keyboard(task_id, is_completed=True)
                        await query.edit_message_text(task_text, reply_markup=keyboard)
                    else:
                        await query.edit_message_text(f"✅ Задача #{task_id} завершена!")
                    
                    await self.show_my_tasks_menu(update, context)
                else:
                    await query.edit_message_text("❌ Ошибка при завершении задачи")
            
            elif callback_data.startswith('reopen:'):
                task_id = int(callback_data.split(':')[1])
                task = self.find_task_by_id(task_id)
                
                if not task:
                    await query.edit_message_text("❌ Задача не найдена!")
                    return
                
                # Проверка прав: пользователь может открывать заново только свои задачи
                if task.get("assigned_to") != username and not is_admin_user:
                    await query.edit_message_text("❌ Вы можете открывать заново только свои задачи!")
                    return
                
                if task:
                    tasks_data = self.get_tasks()
                    task_to_reopen = self.find_task_by_id_in_data(tasks_data, task_id)
                    
                    if task_to_reopen:
                        task_to_reopen["status"] = "active"
                        task_to_reopen["completed_at"] = ""
                        
                        if self.save_tasks(tasks_data):
                            await query.edit_message_text(f"🔄 Задача #{task_id} открыта заново!")
                            
                            config_data = self.get_config()
                            if config_data.get("notifications", {}).get("task_created", True):
                                await self.safe_send_message(
                                    task.get("group_id"),
                                    f"🔄 Задача открыта заново!\n\n🆔 #{task_id}\n📝 {task.get('task_text', '')}\n👤 Исполнитель: {self.get_user_display_name(task.get('assigned_to', ''))}",
                                    context.bot
                                )
                        else:
                            await query.edit_message_text("❌ Ошибка сохранения изменений")
                    
                    await self.show_my_tasks_menu(update, context)
            
            elif callback_data.startswith('delete:'):
                task_id = int(callback_data.split(':')[1])
                task = self.find_task_by_id(task_id)
                
                if not task:
                    await query.edit_message_text("❌ Задача не найдена!")
                    return
                
                # Проверка прав: только администраторы могут удалять задачи
                if not is_admin_user:
                    await query.edit_message_text("❌ У вас нет прав для удаления задач!")
                    return
                
                await self.delete_task_direct(update, context, task_id)
            
            elif callback_data.startswith('change_deadline:'):
                task_id = int(callback_data.split(':')[1])
                task = self.find_task_by_id(task_id)

                if not task:
                    await query.edit_message_text("❌ Задача не найдена!")
                    return
                
                # Проверка прав: пользователь может менять срок только своих задач
                if task.get("assigned_to") != username and not is_admin_user:
                    await query.edit_message_text("❌ Вы можете менять срок только своих задач!")
                    return

                await self.start_change_deadline_for_task(update, context, task_id)

            elif callback_data.startswith('view_group_tasks:'):
                group_id = callback_data.split(':')[1]
                await self.start_group_task_view(update, context, group_id)

            elif callback_data == "back_to_admin":
                await self.show_admin_panel(update, context)

        except Exception as e:
            logging.error(f"Ошибка в handle_callback: {e}")
            try:
                await query.edit_message_text("❌ Произошла ошибка при обработке запроса")
            except Exception:
                pass

    def is_admin(self, username):
        """Проверка прав администратора"""
        config_data = self.get_config()
        hardcoded_admins = ["@admin", "@poznarev"]
        config_admins = config_data.get("admins", [])
        return username in hardcoded_admins + config_admins

    async def show_all_users(self, update: Update, context: CallbackContext):
        try:
            chat = update.effective_chat
            
            all_users = self.get_all_users()
            
            if not all_users:
                await self.safe_send_message(
                    chat.id,
                    "👥 В системе пока нет пользователей\n\n💡 Попросите участников написать любое сообствие в чат с ботом, чтобы они добавились в список",
                    context.bot
                )
                return
            
            users_text = "👥 Все сотрудники системы:\n\n"
            for user in all_users:
                display_name = self.get_user_display_name(user)
                users_text += f"• {display_name}\n"
            
            users_text += f"\nИтого: {len(all_users)} сотрудников"
            await self.safe_send_message(chat.id, users_text, context.bot)
        except Exception as e:
            logging.error(f"Ошибка в show_all_users: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке списка пользователей", context.bot)

    async def show_tasks_by_users(self, update: Update, context: CallbackContext):
        """Показывает невыполненные задачи по каждому сотруднику"""
        try:
            chat = update.effective_chat
            
            users_data = self.get_users()
            all_users = users_data.get("all_users", {})
            
            if not all_users:
                await self.safe_send_message(chat.id, "👥 В системе нет пользователей", context.bot)
                return
            
            tasks_data = self.get_tasks()
            user_tasks = {}
            for user in all_users.keys():
                user_active_tasks = [task for task in tasks_data.get("tasks", []) if task.get("assigned_to") == user and task.get("status") == "active"]
                user_completed_tasks = [task for task in tasks_data.get("tasks", []) if task.get("assigned_to") == user and task.get("status") == "completed"]
                user_tasks[user] = {
                    "active": user_active_tasks,
                    "completed": user_completed_tasks
                }
            
            report_text = "👥 Задачи по сотрудникам:\n\n"
            
            for user, tasks in user_tasks.items():
                display_name = self.get_user_display_name(user)
                report_text += f"🔹 {display_name}\n"
                report_text += f"   🟡 Активных: {len(tasks['active'])} | 🟢 Выполнено: {len(tasks['completed'])}\n"
                
                if tasks['active']:
                    report_text += "   📋 Невыполненные задачи:\n"
                    for task in tasks['active']:
                        days_left = self.get_days_until_deadline(task.get('deadline', ''))
                        status_icon = "🚨" if days_left < 0 else "⏰"
                        task_preview = task.get('task_text', '')[:50] + "..." if len(task.get('task_text', '')) > 50 else task.get('task_text', '')
                        report_text += f"      {status_icon} #{task.get('id', '')}: {task_preview}\n"
                        deadline_status = "ПРОСРОЧЕНО" if days_left < 0 else f"осталось {days_left} дн."
                        report_text += f"         Срок: {task.get('deadline', '')} ({deadline_status})\n"
                else:
                    report_text += "   ✅ Все задачи выполнены!\n"
                
                report_text += "\n"
            
            await self.safe_send_message(chat.id, report_text, context.bot)
        except Exception as e:
            logging.error(f"Ошибка в show_tasks_by_users: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке задач по сотрудникам", context.bot)

    async def show_group_tasks_overview(self, update: Update, context: CallbackContext):
        """Показывает групповые задачи с суммарной статистикой и кнопками выбора"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"

            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return

            groups = self.get_all_groups()
            tasks_data = self.get_tasks()

            if not groups:
                await self.safe_send_message(update.effective_chat.id, "❌ В системе нет групп", context.bot)
                return

            overview_text = "🏘 Групповые задачи\n\nВыберите группу, чтобы увидеть задачи и управлять ими:\n\n"
            keyboard = []

            for group_id, group_info in sorted(groups.items(), key=lambda x: x[1].get("title", "")):
                group_tasks = [t for t in tasks_data.get("tasks", []) if str(t.get("group_id")) == str(group_id)]
                active_count = len([t for t in group_tasks if t.get("status") == "active"])
                completed_count = len([t for t in group_tasks if t.get("status") == "completed"])
                overdue_count = len([t for t in group_tasks if t.get("status") == "active" and self.is_task_overdue(t.get("deadline", ""))])

                title = group_info.get("title") or f"Группа {group_id}"
                overview_text += f"🏠 {title}\n   🟡 Активные: {active_count} | 🟢 Выполнено: {completed_count} | 🔴 Просрочено: {overdue_count}\n\n"

                button_text = f"{title} ({len(group_tasks)})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_group_tasks:{group_id}")])

            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")])

            await self.safe_send_message(
                update.effective_chat.id,
                overview_text,
                context.bot,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logging.error(f"Ошибка в show_group_tasks_overview: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке групповых задач", context.bot)

    async def start_group_task_view(self, update: Update, context: CallbackContext, group_id: str):
        """Открывает список задач конкретной группы с фильтрами"""
        try:
            groups = self.get_all_groups()
            group_title = groups.get(str(group_id), {}).get("title") or f"Группа {group_id}"

            title = f"🏠 Задачи группы: {group_title}"
            await self.show_task_selection(update, context, "view_group_tasks", title, group_id=str(group_id))
            await self.apply_task_filter(update, context, 'all', 'all')
        except Exception as e:
            logging.error(f"Ошибка в start_group_task_view: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Не удалось открыть задачи группы", context.bot)

    def get_days_until_deadline(self, deadline_str):
        """Возвращает количество дней до дедлайна (отрицательное если просрочено)"""
        try:
            deadline = datetime.strptime(deadline_str, '%d.%m.%Y')
            today = datetime.now()
            deadline = deadline.replace(hour=0, minute=0, second=0, microsecond=0)
            today = today.replace(hour=0, minute=0, second=0, microsecond=0)
            return (deadline - today).days
        except ValueError:
            return 0

    async def show_admin_panel(self, update: Update, context: CallbackContext):
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            admin_text = "👑 Панель администратора\n\nВыберите действие:"
            await self.safe_send_message(
                update.effective_chat.id,
                admin_text,
                context.bot,
                reply_markup=self.get_admin_keyboard(update.effective_chat.type)
            )
        except Exception as e:
            logging.error(f"Ошибка в show_admin_panel: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке админ-панели", context.bot)

    async def show_overdue_tasks(self, update: Update, context: CallbackContext):
        try:
            chat = update.effective_chat
            
            tasks_data = self.get_tasks()
            overdue_tasks = [
                task for task in tasks_data.get("tasks", []) 
                if task.get("status") == "active" 
                and self.is_task_overdue(task.get("deadline", ""))
            ]
            
            if not overdue_tasks:
                await self.safe_send_message(chat.id, "✅ Нет просроченных задач!", context.bot)
                return
            
            await self.safe_send_message(chat.id, f"❌ Просроченные задачи ({len(overdue_tasks)}):", context.bot)
            
            for task in overdue_tasks:
                assigned_to_display = self.get_user_display_name(task.get('assigned_to', ''))
                task_text = f"""🚨 ПРОСРОЧЕНО #{task.get('id', 'N/A')}

📝 {task.get('task_text', '')}
👤 Исполнитель: {assigned_to_display}
⏰ Был срок: {task.get('deadline', '')}
👑 Назначил: {self.get_user_display_name(task.get('assigned_by', ''))}
🏠 Группа: {self.get_group_name(task.get('group_id', ''))}"""
                
                await self.safe_send_message(chat.id, task_text, context.bot)
        except Exception as e:
            logging.error(f"Ошибка в show_overdue_tasks: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке просроченных задач", context.bot)

    def is_task_overdue(self, deadline_str):
        """Проверяет, просрочена ли задача"""
        try:
            deadline = datetime.strptime(deadline_str, '%d.%m.%Y')
            today = datetime.now()
            deadline = deadline.replace(hour=23, minute=59, second=59)
            return deadline < today
        except ValueError:
            return False

    async def show_notification_settings(self, update: Update, context: CallbackContext, edit=False):
        """Показывает настройки уведомлений"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            config_data = self.get_config()
            notifications = config_data.get("notifications", {})
            
            settings_text = "⚙️ Настройки уведомлений\n\n"
            settings_text += f"🔔 Создание задач: {'ВКЛ' if notifications.get('task_created', True) else 'ВЫКЛ'}\n"
            settings_text += f"✅ Завершение задач: {'ВКЛ' if notifications.get('task_completed', True) else 'ВЫКЛ'}\n"
            settings_text += f"🗑 Удаление задач: {'ВКЛ' if notifications.get('task_deleted', True) else 'ВЫКЛ'}\n"
            settings_text += f"⏰ Напоминания о просрочке: {'ВКЛ' if notifications.get('overdue_reminder', True) else 'ВЫКЛ'}\n\n"
            settings_text += "Нажмите на кнопку, чтобы переключить настройку:"
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        f"{'🔔' if notifications.get('task_created', True) else '🔕'} Создание задач", 
                        callback_data="toggle_notification:task_created"
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"{'✅' if notifications.get('task_completed', True) else '❌'} Завершение задач", 
                        callback_data="toggle_notification:task_completed"
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"{'🗑' if notifications.get('task_deleted', True) else '📥'} Удаление задач", 
                        callback_data="toggle_notification:task_deleted"
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"{'⏰' if notifications.get('overdue_reminder', True) else '⏳'} Напоминания о просрочке", 
                        callback_data="toggle_notification:overdue_reminder"
                    )
                ],
                [
                    InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")
                ]
            ])
            
            if edit:
                await update.callback_query.edit_message_text(settings_text, reply_markup=keyboard)
            else:
                await self.safe_send_message(
                    update.effective_chat.id,
                    settings_text,
                    context.bot,
                    reply_markup=keyboard
                )
        except Exception as e:
            logging.error(f"Ошибка в show_notification_settings: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке настроек", context.bot)

    def get_all_groups(self):
        """Возвращает список всех групп с исправленными названиями"""
        try:
            users_data = self.get_users()
            if "groups" in users_data and users_data["groups"]:
                for group_id, group_info in users_data["groups"].items():
                    if group_info.get("title") is None:
                        group_info["title"] = f"Группа {group_id}"
                return users_data["groups"]
            
            return {}
            
        except Exception as e:
            logging.error(f"Ошибка получения списка групп: {e}")
            return {}

    async def show_users_management(self, update: Update, context: CallbackContext):
        """Показывает управление пользователями"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            management_text = "👤 Управление пользователями\n\nВыберите действие:"
            await self.safe_send_message(
                update.effective_chat.id,
                management_text,
                context.bot,
                reply_markup=self.get_users_management_keyboard(update.effective_chat.type)
            )
        except Exception as e:
            logging.error(f"Ошибка в show_users_management: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке управления пользователями", context.bot)

    async def start_add_user_manually(self, update: Update, context: CallbackContext):
        """Начинает процесс ручного добавления пользователя"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            # Очищаем предыдущие состояния
            user_id = update.effective_user.id
            if user_id in self.user_states:
                del self.user_states[user_id]

            self.user_states[user_id] = {
                "action": "add_user_manually",
                "step": 1,
                "username": username,
                "chat_id": update.effective_chat.id,
                "created_at": datetime.now()
            }
            
            await self.safe_send_message(
                update.effective_chat.id,
                "Введите username пользователя (например, @username):",
                context.bot,
                reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True) if self.is_private_chat(update.effective_chat.type) else None
            )
        except Exception as e:
            logging.error(f"Ошибка в start_add_user_manually: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка", context.bot)

    async def start_remove_user(self, update: Update, context: CallbackContext):
        """Начинает процесс удаления пользователя"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            all_users = self.get_all_users()
            if not all_users:
                await self.safe_send_message(update.effective_chat.id, "❌ В системе нет пользователей для удаления", context.bot)
                return
            
            display_users = []
            for username in all_users:
                display_text = self.get_user_display_name(username)
                display_users.append(display_text)
            
            # Очищаем предыдущие состояния
            user_id = update.effective_user.id
            if user_id in self.user_states:
                del self.user_states[user_id]

            self.user_states[user_id] = {
                "action": "remove_user",
                "available_users": display_users,
                "available_usernames": all_users,
                "created_at": datetime.now()
            }
            
            await self.show_users_keyboard(update, context, display_users)
            
        except Exception as e:
            logging.error(f"Ошибка в start_remove_user: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка", context.bot)

    async def add_user_manually(self, update: Update, context: CallbackContext):
        """Добавляет пользователя вручную"""
        try:
            user = update.effective_user
            chat = update.effective_chat
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            if not context.args:
                await self.safe_send_message(
                    update.effective_chat.id,
                    "❌ Использование: /add_user @username [полное_имя]\n\nПример: /add_user @ivanov Иван Иванов",
                    context.bot
                )
                return
            
            target_username = context.args[0]
            if not target_username.startswith('@'):
                target_username = f"@{target_username}"
            
            full_name = " ".join(context.args[1:]) if len(context.args) > 1 else "Добавлен вручную"
            
            all_users = self.get_all_users()
            if target_username in all_users:
                await self.safe_send_message(
                    update.effective_chat.id,
                    f"✅ Пользователь {target_username} уже есть в системе",
                    context.bot
                )
                return
            
            await self.add_user_to_group(chat.id, target_username, full_name, chat.title if hasattr(chat, 'title') else "Личный чат")
            
            await self.safe_send_message(
                update.effective_chat.id,
                f"✅ Пользователь {target_username} ({full_name}) добавлен в систему!",
                context.bot
            )
        except Exception as e:
            logging.error(f"Ошибка в add_user_manually: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при добавлении пользователя", context.bot)

    async def show_main_menu(self, update: Update, context: CallbackContext):
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            await self.safe_send_message(
                update.effective_chat.id,
                "🏠 Главное меню",
                context.bot,
                reply_markup=self.get_main_keyboard(self.is_admin(username), update.effective_chat.type)
            )
        except Exception as e:
            logging.error(f"Ошибка в show_main_menu: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при переходе в главное меню", context.bot)

    async def get_chat_id(self, update: Update, context: CallbackContext):
        try:
            chat_id = update.effective_chat.id
            chat_title = getattr(update.effective_chat, 'title', 'Личный чат')
            
            if update.effective_chat.type in ["group", "supergroup"]:
                await self.add_user_to_group(chat_id, f"@system", "System", chat_title)
            
            response_text = f"📋 Информация о чате:\n\n"
            response_text += f"🏠 Название: {chat_title}\n"
            response_text += f"📍 ID чата: {chat_id}\n"
            response_text += f"🔰 Тип: {update.effective_chat.type}\n"
            
            if update.effective_chat.type in ["group", "supergroup"]:
                all_users = self.get_all_users()
                response_text += f"👥 Пользователей в системе: {len(all_users)}\n"
                tasks_data = self.get_tasks()
                response_text += f"📋 Задач в группе: {len([t for t in tasks_data.get('tasks', []) if t.get('group_id') == str(chat_id)])}"
            
            await self.safe_send_message(update.effective_chat.id, response_text, context.bot)
        except Exception as e:
            logging.error(f"Ошибка в get_chat_id: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при получении chat ID", context.bot)

    # Методы для управления администраторами
    async def show_admin_management(self, update: Update, context: CallbackContext):
        """Показывает управление администраторами"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            config_data = self.get_config()
            admins = config_data.get("admins", [])
            hardcoded_admins = ["@admin", "@poznarev"]
            all_admins = hardcoded_admins + admins
            
            admin_text = "👑 Управление администраторами\n\n"
            admin_text += "Текущие администраторы:\n"
            for admin in all_admins:
                admin_text += f"• {admin}\n"
            
            admin_text += "\nВыберите действие:"
            
            await self.safe_send_message(
                update.effective_chat.id,
                admin_text,
                context.bot,
                reply_markup=self.get_admin_management_keyboard(update.effective_chat.type)
            )
        except Exception as e:
            logging.error(f"Ошибка в show_admin_management: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке управления администраторами", context.bot)

    async def start_add_admin(self, update: Update, context: CallbackContext):
        """Начинает процесс добавления администратора"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            # Очищаем предыдущие состояния
            user_id = update.effective_user.id
            if user_id in self.user_states:
                del self.user_states[user_id]

            self.user_states[user_id] = {
                "action": "add_admin",
                "step": 1,
                "created_at": datetime.now()
            }
            
            await self.safe_send_message(
                update.effective_chat.id,
                "Введите username нового администратора (например, @username):",
                context.bot,
                reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True) if self.is_private_chat(update.effective_chat.type) else None
            )
        except Exception as e:
            logging.error(f"Ошибка в start_add_admin: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка", context.bot)

    async def start_remove_admin(self, update: Update, context: CallbackContext):
        """Начинает процесс удаления администратора"""
        try:
            user = update.effective_user
            username = f"@{user.username}" if user.username else f"user_{user.id}"
            
            if not self.is_admin(username):
                await self.safe_send_message(update.effective_chat.id, "❌ У вас нет прав администратора", context.bot)
                return
            
            config_data = self.get_config()
            admins = config_data.get("admins", [])
            hardcoded_admins = ["@admin", "@poznarev"]
            # Нельзя удалять жестко заданных администраторов
            removable_admins = [admin for admin in admins if admin not in hardcoded_admins]
            
            if not removable_admins:
                await self.safe_send_message(update.effective_chat.id, "❌ Нет администраторов для удаления", context.bot)
                return
            
            keyboard = []
            for admin in removable_admins:
                keyboard.append([admin])
            
            keyboard.append(["❌ Отмена"])
            
            # Очищаем предыдущие состояния
            user_id = update.effective_user.id
            if user_id in self.user_states:
                del self.user_states[user_id]

            self.user_states[user_id] = {
                "action": "remove_admin",
                "removable_admins": removable_admins,
                "created_at": datetime.now()
            }
            
            await self.safe_send_message(
                update.effective_chat.id,
                "Выберите администратора для удаления:",
                context.bot,
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True) if self.is_private_chat(update.effective_chat.type) else None
            )
        except Exception as e:
            logging.error(f"Ошибка в start_remove_admin: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка", context.bot)

    async def show_admin_list(self, update: Update, context: CallbackContext):
        """Показывает список администраторов"""
        try:
            config_data = self.get_config()
            admins = config_data.get("admins", [])
            hardcoded_admins = ["@admin", "@poznarev"]
            all_admins = hardcoded_admins + admins
            
            admin_text = "👑 Список администраторов:\n\n"
            admin_text += "🔹 Жестко заданные (нельзя удалить):\n"
            for admin in hardcoded_admins:
                admin_text += f"• {admin}\n"
            
            if admins:
                admin_text += "\n🔹 Добавленные вручную:\n"
                for admin in admins:
                    admin_text += f"• {admin}\n"
            
            admin_text += f"\nВсего администраторов: {len(all_admins)}"
            
            await self.safe_send_message(
                update.effective_chat.id,
                admin_text,
                context.bot
            )
        except Exception as e:
            logging.error(f"Ошибка в show_admin_list: {e}")
            await self.safe_send_message(update.effective_chat.id, "❌ Произошла ошибка при загрузке списка администраторов", context.bot)

def main():
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8366638655:AAH19tYpe_6Wjbe1S9VbFmScU02VftgXSdU')
    
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logging.error("Токен бота не найден! Установите переменную окружения TELEGRAM_BOT_TOKEN")
        return
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        bot_instance = TaskManagerBot(BOT_TOKEN)
        
        # Сбрасываем состояния при запуске
        bot_instance.reset_all_states()
        
        application.add_handler(CommandHandler("start", bot_instance.start))
        application.add_handler(CommandHandler("getid", bot_instance.get_chat_id))
        application.add_handler(CommandHandler("add_user", bot_instance.add_user_manually))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance.handle_message))
        application.add_handler(CallbackQueryHandler(bot_instance.handle_callback))
        
        job_queue = application.job_queue
        if job_queue:
            job_queue.run_repeating(
                lambda context: bot_instance.cleanup_old_states(),
                interval=1800,
                first=10
            )
        
        logging.info("🤖 Бот запущен...")
        
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logging.error(f"Ошибка запуска бота: {e}")

if __name__ == '__main__':
    main()
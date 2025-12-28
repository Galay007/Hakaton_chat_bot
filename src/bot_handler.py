from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from io import BytesIO
from typing import Dict

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    AIORateLimiter,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .data_processor import DataProcessor
from .excel_generator import ExcelGenerator
from .file_manager import FileManager
from .models import SessionData

LOGGER = logging.getLogger(__name__)
BATCH_KEY = "PENDING_DOCUMENTS_BATCH"

class BotHandler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.file_manager = FileManager()
        self.data_processor = DataProcessor()
        self.excel_generator = ExcelGenerator()
        self.sessions: Dict[int, SessionData] = {}
        self.application = (
            ApplicationBuilder()
            .token(settings.token)
            .rate_limiter(AIORateLimiter())
            .build()
        )
        self._register_handlers()

    # Application setup ---------------------------------------------------
    def _register_handlers(self) -> None:
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("reset", self.reset))
        self.application.add_handler(CommandHandler("export", self.export))
        self.application.add_handler(
            MessageHandler(filters.Document.ALL, self.handle_document)
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if BATCH_KEY in context.chat_data:
            del context.chat_data[BATCH_KEY]
        session = self._get_session(update.effective_user.id)
        session.reset()
        await update.message.reply_text(
            "Привет! Отправьте файл или файлы экспорта в JSON формате. Размер файла не более {size:.1f} Мб. "
            "После загрузки используйте команду /export, чтобы получить результат. "
            "Можно в любой момент ввести /reset, чтобы начать заново.".format(
                size=self.settings.max_size / (1024 * 1024)
            )
        )

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "1. Пришлите один или несколько файлов экспорта чата JSON формата.\n"
            "2. Размер каждого файла не должен превышать {size:.1f} Мб.\n"
            "3. Введите /export, чтобы получить список участников.\n"
            "4. Для сброса присланных файлов отправьте /reset, чтобы начать заново.".format(
                size=self.settings.max_size / (1024 * 1024)
            )
            )


    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if BATCH_KEY in context.chat_data:
            del context.chat_data[BATCH_KEY]
        session = self._get_session(update.effective_user.id)
        session.reset()
        await update.message.reply_text("Сессия очищена. Можно отправлять файлы заново.")


    async def handle_document(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        message = update.message

        if not message or not message.document or not update.effective_user:
            return

        session = self._get_session(update.effective_user.id)

        document = message.document
        if not self.file_manager.is_supported(document):
            await message.reply_text(
                "Файл {name} не поддерживается. Нужен файл формата JSON.".format(
                    name=document.file_name
                )
            )
            return
        size_limit = self.settings.max_size
        file_size = document.file_size
        if file_size > size_limit:
            await message.reply_text(
                "Файл {name} не поддерживается. Его размер превышает {size:.1f} Мб. "
                .format(name=document.file_name,size=size_limit / (1024 * 1024))
            )
            return

        context.chat_data.setdefault(BATCH_KEY, {
            'messages': [],
            'task': None,
            'first_message': message
        })

        group_data = context.chat_data[BATCH_KEY]

        group_data['messages'].append(message)
        session.files_received += 1

        current_task = group_data.get('task')
        if current_task:
            current_task.cancel()

        loop = asyncio.get_event_loop()
        scheduled_task = loop.create_task(self._finalize_and_process_batch(context,session))
        group_data['task'] = scheduled_task

    async def _finalize_and_process_batch(self, context: ContextTypes.DEFAULT_TYPE, session):
        group_data = context.chat_data.get(BATCH_KEY)
        if not group_data:
            return

        all_messages = group_data['messages']
        first_message = group_data['first_message']

        all_docs = [msg.document for msg in all_messages if msg.document]
        count = len(all_docs)

        if not all_docs:
            del context.chat_data[BATCH_KEY]
            return

        await first_message.reply_text(
            f"Всего получено {count} файл(а)/(ов) нужного формата.\nДля обработки отправьте /export, для сброса /reset."
        )

    async def export(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.effective_user or not update.message:
            return
        session = self._get_session(update.effective_user.id)

        group_data = context.chat_data.get(BATCH_KEY)
        if not group_data:
            await update.message.reply_text(
                "Нет файлов для обработки. Отправьте один или несколько файлов экспорта."
            )
            return

        await self._run_parser_job(update,group_data,context,session)

        total = len(session.participants)
        files_received = session.files_received

        if total == 0 and files_received > 0:
            await update.message.reply_text(
                "Нет данных о переписке. Отправьте файл, где есть участники чата."
            )
            if BATCH_KEY in context.chat_data:
                del context.chat_data[BATCH_KEY]
            session.reset()
            return

        if total < self.settings.min_inline_response:
            await self._send_inline_response(update.message, session)
        else:
            await self._send_excel(update.message, session)

        if BATCH_KEY in context.chat_data:
            del context.chat_data[BATCH_KEY]
        session.reset()

    # Output helpers ------------------------------------------------------
    async def _send_inline_response(self, message, session: SessionData) -> None:
        rows = list(session.participants.values())
        rows.sort(key=lambda rec: (rec.username or rec.full_name or "").lower())
        lines = [
            "{index}. {label}".format(
                index=index + 1,
                label=self._format_label(record),
            )
            for index, record in enumerate(rows)
        ]
        await message.reply_text(
            "Уникальные участники ({total}):\n{payload}".format(
                total=len(rows), payload="\n".join(lines)
            )
        )

    async def _run_parser_job(self,update: Update, group_data, context,session):
        all_messages = group_data['messages']

        all_docs = [msg.document for msg in all_messages if msg.document]
        if len(all_docs) > 0:
            await update.message.reply_text(
                "Обрабатываю данные..."
            )
            await update.effective_chat.send_action(ChatAction.TYPING)

            for doc in all_docs:
                payload = await self.file_manager.fetch_file_bytes(
                    context.bot, doc.file_id
                )
                await update.effective_chat.send_action(ChatAction.TYPING)
                parsed = self.data_processor.parse_document(doc.file_name, payload)
                session.merge(parsed)

    async def _send_excel(
        self,
        message,
        session: SessionData,
    ) -> None:
        tables = session.as_rows()
        excel_bytes = self.excel_generator.build_workbook(tables)
        timestamp = (session.last_exported_at or datetime.utcnow()).strftime(
            "%Y%m%d_%H%M%S"
        )
        file_name = f"participants_{timestamp}.xlsx"
        await message.reply_document(
            document=BytesIO(excel_bytes),
            filename=file_name,
            caption="Excel-файл с участниками, упоминаниями и каналами.",
        )

    # Utilities -----------------------------------------------------------
    def run(self) -> None:
        LOGGER.info("Bot starting...")
        self.application.run_polling(close_loop=False)

    def _get_session(self, user_id: int) -> SessionData:
        if user_id not in self.sessions:
            self.sessions[user_id] = SessionData()
        return self.sessions[user_id]

    @staticmethod
    def _format_label(record) -> str:
        if record.username:
            return "{username} ({name})".format(
                username=record.username, name=record.full_name or "без имени"
            )
        return record.full_name or record.identifier

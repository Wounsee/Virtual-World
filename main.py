import os
import logging
from dotenv import load_dotenv
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask
import threading

load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Flask app для health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Bot is running!"

@app.route('/health')
def health():
    return "OK"

# Данные о номерах с флагами
NUMBERS_DATA = {
    'usa': {'name': '⁺¹ Америка 🇺🇸 [вирт]', 'price': 55, 'code': '+1', 'type': 'вирт', 'country': 'Америка', 'flag': '🇺🇸 '},
    'myanmar': {'name': '⁺⁹⁵ Мьянма 🇲🇲 [вирт]', 'price': 50, 'code': '+95', 'type': 'вирт', 'country': 'Мьянма', 'flag': '🇲🇲 '},
    'india': {'name': '⁺⁹¹ Индия 🇮🇳 [вирт]', 'price': 50, 'code': '+91', 'type': 'вирт', 'country': 'Индия', 'flag': '🇮🇳 '},
    'mexico': {'name': '⁺⁵² Мексика 🇲🇽 [вирт]', 'price': 50, 'code': '+52', 'type': 'вирт', 'country': 'Мексика', 'flag': '🇲🇽 '},
    'argentina': {'name': '⁺⁵⁴ Аргентина 🇦🇷 [вирт]', 'price': 50, 'code': '+54', 'type': 'вирт', 'country': 'Аргентина', 'flag': '🇦🇷 '},
    'bangladesh': {'name': '⁺⁸⁸⁰ Бангладеш 🇧🇩 [вирт]', 'price': 65, 'code': '+880', 'type': 'вирт', 'country': 'Бангладеш', 'flag': '🇧🇩 '},
    'ukraine': {'name': '⁺³⁸⁰ Украина 🇺🇦 [физ]', 'price': 100, 'code': '+380', 'type': 'физ', 'country': 'Украина', 'flag': '🇺🇦 '},
    'belarus': {'name': '⁺³⁷⁵ Беларусь 🇧🇾 [физ]', 'price': 110, 'code': '+375', 'type': 'физ', 'country': 'Беларусь', 'flag': '🇧🇾 '},
    'tajikistan': {'name': '⁺⁹⁹² Таджикистан 🇹🇯 [физ]', 'price': 150, 'code': '+992', 'type': 'физ', 'country': 'Таджикистан', 'flag': '🇹🇯 '},
    'uzbekistan': {'name': '⁺⁹⁹⁸ Узбекистан 🇺🇿 [физ]', 'price': 100, 'code': '+998', 'type': 'физ', 'country': 'Узбекистан', 'flag': '🇺🇿 '}
}

# Хранилище активных номеров и заказов
active_numbers = {}
pending_orders = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    keyboard = []
    
    # Создаем кнопки для выбора страны
    for key, data in NUMBERS_DATA.items():
        keyboard.append([InlineKeyboardButton(data['name'] + f" - {data['price']}₽", callback_data=key)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "📞 *Выберите страну для получения номера:*")
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик выбора номера"""
    query = update.callback_query
    await query.answer()
    
    selected_country = query.data
    country_data = NUMBERS_DATA[selected_country]
    
    # Сохраняем выбранную страну в контексте пользователя
    context.user_data['selected_country'] = selected_country
    
    # Сообщение о поиске номера
    processing_text = (
        f"🔍 *Ищем доступный номер для {country_data['country']}...*\n"
    )
    
    processing_message = await query.edit_message_text(processing_text, parse_mode='Markdown')
    
    # Задержка 1 секунда
    await asyncio.sleep(1)
    
    # Генерация случайного номера
    phone_number = generate_phone_number(country_data['code'])
    
    # Сохраняем номер для пользователя
    user_id = query.from_user.id
    order_id = f"order_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    pending_orders[order_id] = {
        'user_id': user_id,
        'number': phone_number,
        'country': selected_country,
        'price': country_data['price'],
        'status': 'pending',
        'created_at': datetime.now(),
        'chat_id': query.message.chat_id,
        'message_id': query.message.message_id
    }
    
    # Формируем текст с номером и кнопкой оплаты
    number_text = (
        f"⌁ *Номер:* `{phone_number}`\n"
        f"⌁ {country_data['flag']}*{country_data['country']}*\n\n"
        f"☛ [К оплате {country_data['price']:.2f}₽](https://platega.io)"
    )
    
    # Создаем кнопки для оплаты и возврата
    payment_keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url="https://platega.io")],
        [InlineKeyboardButton("◀️ Меню", callback_data="back_to_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(payment_keyboard)
    
    await query.edit_message_text(number_text, reply_markup=reply_markup, parse_mode='Markdown', disable_web_page_preview=True)
    
    # Запускаем автоматическую проверку оплаты через 3 секунды
    if context.application.job_queue:
        context.application.job_queue.run_once(
            check_payment_auto, 
            3, 
            data={'order_id': order_id}
        )
    else:
        # Если JobQueue не доступен, просто ждем 3 секунды и обрабатываем
        await asyncio.sleep(15)
        await process_payment_success(context.bot, order_id)

async def check_payment_auto(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Автоматическая проверка оплаты через 3 секунды"""
    job_data = context.job.data
    order_id = job_data['order_id']
    
    await process_payment_success(context.bot, order_id)

async def process_payment_success(bot, order_id: str) -> None:
    """Обработка успешной оплаты"""
    if order_id in pending_orders:
        order_data = pending_orders[order_id]
        
        # Автоматически считаем оплату завершенной через 3 секунды
        user_id = order_data['user_id']
        phone_number = order_data['number']
        country_data = NUMBERS_DATA[order_data['country']]
        
        # Активируем номер
        active_numbers[user_id] = {
            'number': phone_number,
            'country': order_data['country'],
            'expires_at': datetime.now() + timedelta(hours=1)
        }
        
        # Текст после успешной оплаты
        success_text = (
            "✅ *Оплата прошла успешно!*\n\n"
            f"☛ *Ваш номер:* `{phone_number}`\n"
            f"⌁ {country_data['flag']}*{country_data['country']}*\n\n"
            "*Номер будет активен в течение 1 часа.*\n"
            "_После этого сообщения на него поступать не смогут._\n\n"
        )
        
        # Отправляем сообщение об успешной оплате
        await bot.edit_message_text(
            chat_id=order_data['chat_id'],
            message_id=order_data['message_id'],
            text=success_text,
            parse_mode='Markdown'
        )
        
        # Запускаем отправку сообщения с кодом через 4 секунды
        await asyncio.sleep(4)
        await send_telegram_code_message(bot, order_data['chat_id'])
        
        # Удаляем заказ из ожидания
        del pending_orders[order_id]

async def send_telegram_code_message(bot, chat_id: int) -> None:
    """Отправка сообщения с кодом от Telegram"""
    # Генерируем случайный 5-значный код
    code = ''.join([str(random.randint(0, 9)) for _ in range(5)])
    
    code_message = (
        "_Новое сообщение от:_ `Telegram`\n\n"
        f"*Код для входа в Telegram: {code}.* Не давайте код никому, даже если его требуют от имени Telegram!"
    )
    
    await bot.send_message(
        chat_id=chat_id,
        text=code_message,
        parse_mode='Markdown'
    )

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик возврата в меню"""
    query = update.callback_query
    
    # Проверяем, не устарел ли запрос
    try:
        await query.answer()
    except Exception:
        # Если запрос устарел, просто игнорируем
        return
    
    # Показываем меню выбора стран
    keyboard = []
    for key, data in NUMBERS_DATA.items():
        keyboard.append([InlineKeyboardButton(data['name'] + f" - {data['price']}₽", callback_data=key)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    menu_text = "*Выберите страну для получения номера:*"
    
    await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')

def generate_phone_number(country_code: str) -> str:
    """Генерация случайного номера телефона"""
    # Генерируем случайную часть номера
    if country_code == '+1':  # США
        number = ''.join([str(random.randint(0, 9)) for _ in range(10)])
    elif country_code == '+380':  # Украина
        number = '97' + ''.join([str(random.randint(0, 9)) for _ in range(7)])
    elif country_code == '+375':  # Беларусь
        number = '29' + ''.join([str(random.randint(0, 9)) for _ in range(7)])
    elif country_code == '+998':  # Узбекистан
        number = '99' + ''.join([str(random.randint(0, 9)) for _ in range(7)])
    elif country_code == '+992':  # Таджикистан
        number = '98' + ''.join([str(random.randint(0, 9)) for _ in range(7)])
    else:  # Остальные страны
        number = ''.join([str(random.randint(0, 9)) for _ in range(9)])
    
    return f"{country_code}{number}"

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = (
        "🤖 *Бот для покупки виртуальных номеров*\n\n"
    )

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

def run_bot():
    """Запуск Telegram бота"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(handle_back, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(handle_selection))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()

def main() -> None:
    """Основная функция запуска"""
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота в основном потоке
    run_bot()

if __name__ == "__main__":
    main()

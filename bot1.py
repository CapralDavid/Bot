import telebot
import schedule
import time
from threading import Thread, Lock
from datetime import datetime, timedelta
import logging

# Встановлюємо рівень логування
logging.basicConfig(level=logging.DEBUG)

# Замість 'YOUR_BOT_TOKEN' вставте токен вашого бота
bot = telebot.TeleBot('7238371402:AAEvizojibQlBT2JMoVo2Z4-46899erjvDc')

# Змінні для збереження даних користувача
user_data = {}
jobs = {}
locks = {}  # Словник для зберігання блокувань для кожного користувача

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Вітаю! Я Ваш асистент, який буде нагадувати вчасно змінювати елайнерів. Як я можу до Вас звертатись?")
    bot.register_next_step_handler(message, ask_name)

def ask_name(message):
    user_data[message.chat.id] = {'name': message.text}
    locks[message.chat.id] = Lock()  # Створюємо блокування для кожного користувача
    bot.send_message(message.chat.id, f"Радий познайомитись, {message.text}! Яка загальна кількість елайнерів у Вашому плані лікування?")
    bot.register_next_step_handler(message, ask_aligners_count)

def ask_aligners_count(message):
    try:
        aligners_count = int(message.text)
        user_data[message.chat.id]['aligners_count'] = aligners_count
        bot.send_message(message.chat.id, "На якому елайнері Ви зараз знаходитесь?")
        bot.register_next_step_handler(message, ask_aligner_number)
    except ValueError:
        bot.send_message(message.chat.id, "Будь ласка, введіть число.")
        bot.register_next_step_handler(message, ask_aligners_count)

def ask_aligner_number(message):
    try:
        current_aligner = int(message.text)
        aligners_count = user_data[message.chat.id]['aligners_count']
        if 1 <= current_aligner <= aligners_count:
            user_data[message.chat.id]['current_aligner'] = current_aligner
            bot.send_message(message.chat.id, "Яку кількість днів Вам рекомендує носити кожен елайнер?")
            bot.register_next_step_handler(message, ask_days_to_wear)
        else:
            bot.send_message(message.chat.id, f"Будь ласка, введіть правильний номер елайнера (від 1 до {aligners_count}).")
            bot.register_next_step_handler(message, ask_aligner_number)
    except ValueError:
        aligners_count = user_data[message.chat.id]['aligners_count']
        bot.send_message(message.chat.id, f"Будь ласка, введіть правильний номер елайнера (від 1 до {aligners_count}).")
        bot.register_next_step_handler(message, ask_aligner_number)

def ask_days_to_wear(message):
    try:
        days_to_wear = int(message.text)
        user_data[message.chat.id]['days_to_wear'] = days_to_wear
        bot.send_message(message.chat.id, "Будь ласка, виберіть час нагадування у форматі ГГ:ХХ (24-годинний формат).")
        bot.register_next_step_handler(message, ask_reminder_time)
    except ValueError:
        bot.send_message(message.chat.id, "Будь ласка, введіть число.")
        bot.register_next_step_handler(message, ask_days_to_wear)

def ask_reminder_time(message):
    try:
        reminder_time = datetime.strptime(message.text, '%H:%M').time()
        user_data[message.chat.id]['reminder_time'] = reminder_time
        bot.send_message(message.chat.id, "Дякую! Тепер я буду нагадувати Вам про заміну елайнерів.")
        schedule_aligners_reminder(message.chat.id)
        bot.send_message(message.chat.id, "Щоб отримати список дат для кожного елайнера, натисніть кнопку нижче.", reply_markup=generate_dates_button())
    except ValueError:
        bot.send_message(message.chat.id, "Будь ласка, введіть час у форматі ГГ:ХХ.")
        bot.register_next_step_handler(message, ask_reminder_time)

def send_reminder(chat_id):
    with locks[chat_id]:  # Використовуємо блокування для запобігання повторному виконанню
        current_aligner = user_data[chat_id]['current_aligner']
        if current_aligner < user_data[chat_id]['aligners_count']:
            current_aligner += 1
            user_data[chat_id]['current_aligner'] = current_aligner
            bot.send_message(chat_id, f"Вітаю! Час одягнути елайнер №{current_aligner}. Дружнє нагадування: не викидайте старі елайнери :)")
            schedule_next_reminder(chat_id)
        else:
            bot.send_message(chat_id, "Вітаю! Ви закінчили носіння всіх елайнерів у Вашому плані лікування.")
            if chat_id in jobs:
                schedule.cancel_job(jobs[chat_id])  # Видаляємо завдання для користувача
                del jobs[chat_id]  # Видаляємо завдання з словника
        logging.info(f"Відправлено нагадування користувачу {chat_id} про заміну елайнерів")

def schedule_next_reminder(chat_id):
    # Очищаємо попередні задачі для даного користувача
    if chat_id in jobs:
        schedule.cancel_job(jobs[chat_id])
        logging.debug(f"Видалено попередню задачу для {chat_id}")

    days_to_wear = user_data[chat_id]['days_to_wear']
    reminder_time = user_data[chat_id]['reminder_time']
    next_run = datetime.combine(datetime.now() + timedelta(days=days_to_wear), reminder_time)
    jobs[chat_id] = schedule.every().day.at(next_run.strftime('%H:%M')).do(send_reminder, chat_id=chat_id)
    logging.debug(f"Заплановано наступну задачу для {chat_id} через {days_to_wear} днів о {reminder_time}")

def schedule_aligners_reminder(chat_id):
    schedule_next_reminder(chat_id)

def generate_dates_button():
    markup = telebot.types.InlineKeyboardMarkup()
    button = telebot.types.InlineKeyboardButton("Отримати список дат", callback_data="get_dates")
    markup.add(button)
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "get_dates")
def send_dates_list(call):
    chat_id = call.message.chat.id
    days_to_wear = user_data[chat_id]['days_to_wear']
    reminder_time = user_data[chat_id]['reminder_time']
    current_date = datetime.now()
    dates_list = []

    for aligner_number in range(1, user_data[chat_id]['aligners_count'] + 1):
        current_date += timedelta(days=days_to_wear)
        dates_list.append(f"Елайнер №{aligner_number} - {current_date.strftime('%Y-%m-%d')}")

    dates_message = "\n".join(dates_list)
    bot.send_message(chat_id, f"Ваші дати заміни елайнерів:\n{dates_message}")
    logging.info(f"Надіслано список дат заміни елайнерів користувачу {chat_id}")

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Запускаємо планувальник в окремому потоці
schedule_thread = Thread(target=run_schedule)
schedule_thread.start()

# Запускаємо бота
bot.polling(none_stop=True)

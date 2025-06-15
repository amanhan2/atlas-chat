import os
import sqlite3
import subprocess
import json
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from sentence_transformers import SentenceTransformer, util

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7292283989:AAEE5X0_x7DFigP8Q_yD4ZX-gOZIgdrD37A'
DB_FILE = 'products.db'
RELEVANCE_THRESHOLD = 0.3
GEMMA_MODEL = 'gemma3:1b'

# === ИНИЦИАЛИЗАЦИЯ МОДЕЛИ ===
model = SentenceTransformer('all-MiniLM-L6-v2')

# === СОСТОЯНИЯ ДЛЯ ConversationHandler ===
NAME, PRICE, DESCRIPTION, ADDRESS, CATEGORY, PHOTO = range(6)

# === СОЗДАНИЕ БД ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            price TEXT,
            description TEXT,
            address TEXT,
            category TEXT,
            photo_path TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

# === РЕГИСТРАЦИЯ ===
def start(update: Update, context: CallbackContext):
    user = update.message.from_user
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
                   (user.id, user.username, user.first_name))
    conn.commit()
    conn.close()
    update.message.reply_text("Добро пожаловать! Напиши /add чтобы добавить товар.")

# === ДОБАВЛЕНИЕ ТОВАРА ===
def start_add(update: Update, context: CallbackContext):
    update.message.reply_text("📝 Введите название товара:")
    return NAME

def handle_name(update: Update, context: CallbackContext):
    context.user_data['name'] = update.message.text
    update.message.reply_text("💰 Введите цену:")
    return PRICE

def handle_price(update: Update, context: CallbackContext):
    context.user_data['price'] = update.message.text
    update.message.reply_text("📄 Введите описание:")
    return DESCRIPTION

def handle_description(update: Update, context: CallbackContext):
    context.user_data['description'] = update.message.text
    update.message.reply_text("📍 Укажите адрес:")
    return ADDRESS

def handle_address(update: Update, context: CallbackContext):
    context.user_data['address'] = update.message.text
    update.message.reply_text("🏷 Укажите категорию:")
    return CATEGORY

def handle_category(update: Update, context: CallbackContext):
    context.user_data['category'] = update.message.text
    update.message.reply_text("📷 Пришлите фото:")
    return PHOTO

def handle_photo(update: Update, context: CallbackContext):
    user = update.message.from_user
    photo_file = update.message.photo[-1].get_file()
    os.makedirs("photos", exist_ok=True)
    photo_path = f'photos/{photo_file.file_id}.jpg'
    photo_file.download(photo_path)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (user.id,))
    row = cursor.fetchone()

    if row is None:
        update.message.reply_text("⚠️ Сначала зарегистрируйтесь с помощью /start.")
        return ConversationHandler.END

    user_id = row[0]
    cursor.execute("""
        INSERT INTO products (user_id, name, price, description, address, category, photo_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        context.user_data['name'],
        context.user_data['price'],
        context.user_data['description'],
        context.user_data['address'],
        context.user_data['category'],
        photo_path
    ))
    conn.commit()
    conn.close()

    update.message.reply_text("✅ Товар успешно добавлен.")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("🚫 Добавление отменено.")
    return ConversationHandler.END

# === ПОИСК ТОВАРОВ ===
def search_products(query):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.name, p.price, p.description, p.address, p.category, p.photo_path, u.username, u.first_name
        FROM products p JOIN users u ON p.user_id = u.id
    """)
    results = cursor.fetchall()
    conn.close()

    if not results:
        return []

    corpus = [f"{r[0]} {r[1]} {r[2]} {r[3]} {r[4]}" for r in results]
    query_embedding = model.encode(query, convert_to_tensor=True)
    corpus_embeddings = model.encode(corpus, convert_to_tensor=True)
    hits = util.semantic_search(query_embedding, corpus_embeddings, top_k=5)[0]

    filtered = [results[hit['corpus_id']] + (hit['score'],) for hit in hits if hit['score'] >= RELEVANCE_THRESHOLD]
    return filtered

# === ВСТРАИВАНИЕ GEMMA 3B (Ollama) ===
def explain_with_gemma(query, results):
    product_names = ', '.join([r[0] for r in results])
    prompt = f"Пользователь ищет: '{query}'. Он получил следующие товары: {product_names}. Объясни, почему эти товары были выбраны на основе запроса."

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gemma:3",
                "prompt": prompt,
                "stream": False
            }
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("response", "🤖 Нет объяснения от модели.")
        else:
            return f"⚠️ Ошибка от Gemini: {response.status_code} — {response.text}"
    except Exception as e:
        return f"⚠️ Ошибка подключения к Gemini: {e}"
    
# === ОБРАБОТКА ПОИСКА С ОБЪЯСНЕНИЕМ ===
def handle_message(update: Update, context: CallbackContext):
    query = update.message.text.strip()
    results = search_products(query)

    if not results:
        update.message.reply_text("😕 Ничего не найдено.")
        return

    for name, price, description, address, category, photo_path, username, first_name, score in results:
        contact = f"@{username}" if username else first_name
        caption = f"📦 {name}\n💰 {price}\n📄 {description}\n📍 {address}\n📁 {category}\n📞 Продавец: {contact}\n🎯 Релевантность: {round(score, 2)}"
        if os.path.exists(photo_path):
            update.message.reply_photo(open(photo_path, 'rb'), caption=caption)
        else:
            update.message.reply_text(caption)

    explanation = explain_with_gemma(query, results)
    update.message.reply_text(f"🤖 Объяснение от Gemini:\n\n{explanation}")

# === ОСНОВНАЯ ФУНКЦИЯ ===
def main():
    init_db()
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', start_add)],
        states={
            NAME: [MessageHandler(Filters.text & ~Filters.command, handle_name)],
            PRICE: [MessageHandler(Filters.text & ~Filters.command, handle_price)],
            DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, handle_description)],
            ADDRESS: [MessageHandler(Filters.text & ~Filters.command, handle_address)],
            CATEGORY: [MessageHandler(Filters.text & ~Filters.command, handle_category)],
            PHOTO: [MessageHandler(Filters.photo, handle_photo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(conv_handler)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from sentence_transformers import SentenceTransformer, util

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '7292283989:AAEE5X0_x7DFigP8Q_yD4ZX-gOZIgdrD37A'
DB_FILE = 'products.db'
RELEVANCE_THRESHOLD = 0.4

# === ИНИЦИАЛИЗАЦИЯ ===
model = SentenceTransformer('all-MiniLM-L6-v2')

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

# === СОСТОЯНИЯ ===
REGISTER, NAME, PRICE, DESCRIPTION, ADDRESS, CATEGORY, PHOTO = range(7)

# === РЕГИСТРАЦИЯ ===
def start(update: Update, context: CallbackContext):
    print("==> /start вызван")  # Отладка
    user = update.message.from_user
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
                   (user.id, user.username, user.first_name))
    conn.commit()
    conn.close()
    update.message.reply_text("Добро пожаловать в Atlas Chat! Напишите /add чтобы добавить товар.")

# === НАЧАЛО ДОБАВЛЕНИЯ ===
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
    update.message.reply_text("🏷 Укажите категорию (например: техника, одежда, книги):")
    return CATEGORY

def handle_category(update: Update, context: CallbackContext):
    context.user_data['category'] = update.message.text
    update.message.reply_text("📷 Пришлите фото товара:")
    return PHOTO

def handle_photo(update: Update, context: CallbackContext):
    user = update.message.from_user
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Проверка регистрации пользователя
    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (user.id,))
    row = cursor.fetchone()
    if row is None:
        update.message.reply_text("⚠️ Пожалуйста, сначала зарегистрируйтесь командой /start.")
        conn.close()
        return ConversationHandler.END

    user_id = row[0]

    photo_file = update.message.photo[-1].get_file()
    photo_path = f'photos/{photo_file.file_id}.jpg'
    os.makedirs('photos', exist_ok=True)
    photo_file.download(photo_path)

    context.user_data['photo_path'] = photo_path

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
        context.user_data['photo_path']
    ))
    conn.commit()
    conn.close()

    update.message.reply_text("✅ Товар успешно добавлен!")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("🚫 Добавление товара отменено.")
    return ConversationHandler.END

# === ПОИСК ===
def search_products(query):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.name, p.price, p.description, p.address, p.category, p.photo_path, u.username, u.first_name
        FROM products p
        JOIN users u ON p.user_id = u.id
    """)
    results = cursor.fetchall()
    conn.close()

    if not results:
        return []

    corpus = ["{} {} {} {} {}".format(*row[:5]) for row in results]
    query_embedding = model.encode(query, convert_to_tensor=True)
    corpus_embeddings = model.encode(corpus, convert_to_tensor=True)

    hits = util.semantic_search(query_embedding, corpus_embeddings, top_k=5)[0]
    filtered_hits = [results[hit['corpus_id']] + (hit['score'],) for hit in hits if hit['score'] >= RELEVANCE_THRESHOLD]

    return filtered_hits
def explain_with_gemma(query, results):
    product_names = ', '.join([r[0] for r in results])
    prompt = f"Пользователь ищет: '{query}'. Он получил следующие товары: {product_names}. Объясни, почему эти товары были выбраны на основе запроса."
    
    try:
        result = subprocess.run(
            ["ollama", "run", GEMMA_MODEL],
            input=prompt.encode(),
            capture_output=True,
            timeout=30
        )
        return result.stdout.decode().strip()
    except Exception as e:
        return f"⚠️ Не удалось получить объяснение от Gemini: {e}"

# === ОБРАБОТКА ПОИСКА ===
def handle_message(update: Update, context: CallbackContext):
    query = update.message.text.lower()
    results = search_products(query)

    if not results:
        update.message.reply_text("😕 Ничего не найдено.")
        return

    for name, price, description, address, category, photo_path, username, first_name, score in results:
        contact = f"@{username}" if username else first_name
        caption = f"📦 {name}\n💰 {price}\n📄 {description}\n📍 {address}\n📁 {category}\n📞 Продавец: {contact}\n🎯 Релевантность: {round(score, 2)}"
        if photo_path and os.path.exists(photo_path):
            update.message.reply_photo(open(photo_path, 'rb'), caption=caption)
        else:
            update.message.reply_text(caption)

# === ЗАПУСК ===
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
            PHOTO: [MessageHandler(Filters.photo, handle_photo)]
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



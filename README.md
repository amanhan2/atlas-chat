AtlasChat — Telegram bot for searching and adding AI - enabled products
> 📦 Add products | 🔍 Search by meaning | 🤖 Get explanations from AI (Gemma 3B)
---
🚀 Features
- Add products with description, photo, price and category.
- Automatic user registration.
- Semantic product search via 'sentence-transformers'.
- Connect the local AI model **Gemma 3B** via [Ollama](https://ollama.com ) for explanations.
- Work without Internet and clouds — everything is local.
---
, Dependencies
```bash
pip install python-telegram-bot==13.15
pip install sentence-transformers
pip install requests
``
> ⚠️ 'python-telegram-bot < v20' is used, as the project was created on `Updater/Dispatcher`.
---
> 🏗 Project structure
```
project/
,── bot.py # The main bot
├── products.db # SQLite product database
├── photos/            # Folder with product photos
,── README.md # This file
, Launching Gemma via Ollama
1. Install Ollama: https://ollama.com
2. Download the model:
   ```bash
   ollama pull gemma:3b
   ```
3. Make sure it works:
``bash
ollama run gemma:3b
   ```
⚙️ Configuration
Make sure that the `bot.py ` specified:
```python
OLLAMA_URL = 'http://127.0.0.1:11434/api/generate'
MODEL_NAME = 'gemma3:1b'
```
And that the gemma3:1b model is running locally.
---
, Examples
User: Find me some wireless headphones  
Bot:  
📦 AirPods Pro  
💰 12000  
, Address: Bishkek, Togolok Moldo  
, Contact: @username  
, Explanation from AI:  
> This product belongs to the "audio" category, the name and description mention wireless headphones, which is as appropriate as possible.
---
📜 License
MIT is free to use, modify, distribute.

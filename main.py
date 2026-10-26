import os
import json
import requests
from vkbottle.bot import Bot, Message

# ==================== Конфигурация ====================
# Ключи вставлены напрямую. Репозиторий на GitHub должен быть ПРИВАТНЫМ!
VK_TOKEN = "vk1.a.sb-LCc9im1WDE3NZtO0yH86ZScgTdX88FS5kmj71oSVpz58I2KtgniksnnBKQ6pjVuIrsYe5l7p7q4cPHouTOquw3zZW5TeG0w6Q386hIqvZfc9rFxs_ikiWEJEd2vcf-HtfvtdG9kh9KkRRBRKpZqqnFDS05JzQbutwCwAm9z6o3nZMjKvQfX6rd2zRXNBGWslLywgYlRUicg4pDszL0A"
DEEPSEEK_KEY = "sk-aitunnel-RQFsYV5hGsb1pHXjZdqhxp1RGLLhdi49"
ROSPATENT_KEY = "4c954b74eab24338a3d5bce208919470"

# AITunnel — это OpenAI-совместимый агрегатор. Base URL именно такой.
DEEPSEEK_URL = "https://api.aitunnel.ru/v1/chat/completions"
ROSPATENT_URL = "https://searchplatform.rospatent.gov.ru/patsearch/v0.2/search"

if not all([VK_TOKEN, DEEPSEEK_KEY, ROSPATENT_KEY]):
    raise ValueError("Не заданы ключи: VK_TOKEN, DEEPSEEK_KEY или ROSPATENT_KEY")

bot = Bot(token=VK_TOKEN)


def ask_deepseek(prompt: str, system: str = "") -> str:
    """Универсальный вызов DeepSeek через AITunnel"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    resp = requests.post(
        DEEPSEEK_URL,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
        json={
            # Если эта модель не работает, попробуйте "deepseek-v4-flash-0731" или "deepseek-v4-pro"
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.3,
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def extract_keywords(product_text: str) -> str:
    """Извлечение технических ключевых слов для патентного поиска"""
    return ask_deepseek(
        f"Из описания товара выдели 3-7 технических ключевых слов для патентного поиска. "
        f"Верни только список через запятую, без пояснений.\n\nТовар: {product_text}",
        system="Ты патентный аналитик. Отвечай кратко и по делу."
    )


def search_rospatent(query: str, limit: int = 5) -> dict:
    """
    Поиск в API Роспатента.
    Используем параметр q (или qn) согласно документации.
    """
    resp = requests.post(
        ROSPATENT_URL,
        headers={
            "Authorization": f"Bearer {ROSPATENT_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "q": query,          # В некоторых версиях API используется q, а не qn
            "limit": limit,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def generate_report(product_text: str, patents_json: dict) -> str:
    """Генерация отчёта: анализ рисков + предложения по доработке для патентования"""
    
    patents_str = json.dumps(patents_json, ensure_ascii=False)[:4000]
    
    prompt = f"""Ты патентный аналитик. На основе описания товара пользователя и результатов поиска патентов Роспатента выполни следующее:

1. **Анализ совпадений**: кратко опиши, какие технические признаки данного товара уже встречаются в найденных патентах.
2. **Оценка риска**: высокий/средний/низкий/не найден.
3. **Направления доработки (для патентования)**: предложи 2-3 конкретных технических усовершенствования, которые:
   - не покрываются существующими патентами;
   - обладают технической новизной (изменение конструкции/способа/материала/параметров, а не маркетинговые улучшения);
   - по возможности соответствуют критериям полезной модели (только новизна и промышленная применимость, без проверки изобретательского уровня).
   Для каждого направления укажи: что изменить, какую техническую проблему решает, почему может быть неочевидным.

Товар пользователя: {product_text}

Результаты патентного поиска (JSON): {patents_str}

Отвечай на русском языке, структурированно и кратко."""
    
    return ask_deepseek(
        prompt, 
        system="Ты патентный аналитик. Не давай юридических гарантий, только технический анализ."
    )


@bot.on.message()
async def handle(message: Message):
    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("Пожалуйста, отправьте название или описание товара.")
        return

    try:
        keywords = extract_keywords(user_text)
    except Exception as e:
        await message.answer(f"Ошибка при обращении к DeepSeek: {e}")
        return

    try:
        patents = search_rospatent(keywords, limit=5)
    except Exception as e:
        await message.answer(
            f"Ключевые слова: {keywords}\n\n"
            f"Ошибка при поиске в Роспатенте: {e}"
        )
        return

    total = patents.get("total", 0) if isinstance(patents, dict) else 0
    if total == 0:
        await message.answer(
            f"Ключевые слова: {keywords}\n\n"
            f"По вашему запросу не найдено связанных патентов. "
            f"Возможно, товар обладает новизной, но рекомендуется провести более глубокий поиск с патентным поверенным."
        )
        return

    try:
        report = generate_report(user_text, patents)
    except Exception as e:
        await message.answer(f"Ошибка при генерации отчёта: {e}")
        return

    full_response = (
        f"🔍 **Ключевые слова для поиска**: {keywords}\n"
        f"📊 **Найдено патентов**: {total}\n\n"
        f"{report}\n\n"
        f"---\n"
        f"⚠️ Отчёт сгенерирован ИИ на основе открытых данных и носит справочный характер. "
        f"Для принятия решений о патентовании проконсультируйтесь с патентным поверенным."
    )
    await message.answer(full_response[:4000])


if __name__ == "__main__":
    bot.run_forever()

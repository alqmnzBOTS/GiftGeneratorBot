import os
import logging
import json
import random
import asyncio
from datetime import datetime

import openai
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from dotenv import load_dotenv
from pyexpat.errors import messages
from wheel.macosx_libfile import build_version_command_fields

# Кофигурация и настройка
load_dotenv()

# Константа с именем создателя
CREATOR_GITHUB = "alqmnzBOTS"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

# Инициализация OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# База Данных (JSON-файл)
FAVORITES_FILE = "favorites.json"

def load_favorites():
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_favorites(favorites):
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)

def add_to_favorites(user_id, gift):
    favorites = load_favorites()
    user_id = str(user_id)

    if user_id not in favorites:
        favorites[user_id] = []

    # Добавляем только уникальные подарки
    if gift not in favorites[user_id]:
        favorites[user_id].append(gift)
        save_favorites(favorites)
        return True
    return False

def remove_from_favorites(user_id, gift_index):
    favorites = load_favorites()
    user_id = str(user_id)

    if user_id in favorites and 0 <= gift_index < len(favorites[user_id]):
        removed = favorites[user_id].pop(gift_index)
        save_favorites(favorites)
        return removed
    return None

def get_user_favorites(user_id):
    favorites = load_favorites()
    user_id = str(user_id)
    return favorites.get(user_id, [])

# Finite State Machine для генерации подарков
class GiftGeneration(StatesGroup):
    GENDER = State()
    AGE = State()
    BUDGET = State()
    INTERESTS = State()

# Вспомогательные функции
async def generate_gift_ideas(gender: str, age: int, budget: int, interests: str) -> list:
    """Генерирует идеи подарков с помощью OpenAI"""
    prompt = (
        f"Сгенерируй 5 креативных идей подарков для {gender}, {age} лет, "
        f"с бюджетом {budget} рублей. Интересы: {interests}. "
        "Подарки должны быть практичными и соответствовать возрасту. "
        "Формат: 1. Название подарка (примерная цена в рублях) - краткое описание"
    )

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты помощник по выбору подарков"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )

        ideas = response.choices[0].message.content.strip().split("\n")
        return [idea for idea in ideas if idea.strip()]
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return []

async def generate_random_gift() -> str:
    """Генерирует случайную идею подарка"""
    categories = ["техника", "книги", "искусство", "спорт", "косметика", "игры", "кухня"]
    interests = random.sample(categories, 2)

    gender = random.choice(["мужчины", "женщины"])
    age = random.randint(18, 65)
    budget = random.randint(500, 10000)

    ideas = await generate_gift_ideas(gender, age, budget, ", ".join(interests))
    return random.choice(ideas) if ideas else "К сожалению, не удалось сгенерировать идею"

# Обработчики команд
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    """Приветственное сообщение"""
    welcome_text = (
        f"🎁 Привет, {message.from_user.first_name}!\n"
        "Я помогу подобрать идеальный подарок для любого случая!\n\n"
        "✨ Просто укажи:\n"
        "- Пол получателя\n"
        "- Возраст\n"
        "- Бюджет\n"
        "- Интересы\n\n"
        f"⚠️ Бот создан для некоммерческого использования\n"
        f"Создатель: github.com/{CREATOR_GITHUB}\n\n"
        "Используй команды:\n"
        "/gift - подобрать подарок\n"
        "/random - случайная идея подарка\n"
        "/favorites - мои сохранённые идеи"
    )
    await message.answer(welcome_text)

@dp.message(F.text == "/gift")
async def cmd_gift(message: types.Message, state: FSMContext):
    """Начало процесса генерации подарка"""
    # Клавиатура для выбора пола
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Мужчине"))
    builder.add(types.KeyboardButton(text="Женщине"))
    builder.add(types.KeyboardButton(text="Не важно"))
    builder.adjust(2)

    await message.answer(
        "👤 Для кого выбираем подарок?",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await state.set_state(GiftGeneration.GENDER)

@dp.message(GiftGeneration.GENDER)
async def process_gender(message: types.Message, state: FSMContext):
    """Обработка пола получателя"""
    gender_map = {
        "мужчине": "мужчину",
        "женщине": "женщину",
        "не важно": "человека"
    }

    gender = next((k for k in gender_map if message.text.lower().startswith(k[:3])), None)

    if not gender:
        await message.answer("Пожалуйста, выбери вариант из клавиатуры")
        return

    await  state.update_data(gender=gender_map[gender])
    await message.answer(
        "🔢 Сколько лет получателю?",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(GiftGeneration.AGE)

@dp.message(GiftGeneration.AGE)
async def process_age(message: types.Message, state: FSMContext):
    """Обработка возраста получателя"""
    try:
        age = int(message.text)
        if age < 1 or age > 120:
            raise ValueError
        await state .update_data(age=age)
        await message.answer("💰 Какой у тебя бюджет на подарок (в рублях)?")
        await state.set_state(GiftGeneration.BUDGET)
    except ValueError:
        await message.answer("Пожалуйста, введи корректный возраст (число от 1 до 120):")

@dp.message(GiftGeneration.BUDGET)
async def process_budget(message: types.Message, state: FSMContext):
    """Обработка бюджета"""
    try:
        budget = int(message.text)
        if budget < 10:
            raise ValueError
        await state.update_data(budget=budget)
        await message.answer("🎯 Какие интересы у получателя?\n(например: музыка, спорт, книги, технологии)")
        await state.set_state(GiftGeneration.INTERESTS)
    except ValueError:
        await message.answer("Пожалуйста, введи корректную сумму (число больше 10):")

@dp.message(GiftGeneration.INTERESTS)
async def process_interests(message: types.Message, state: FSMContext):
    """Обработка интересов и генерация подарка"""
    interests = message.text
    data = await state.get_data()

    # Показываем анимацию загрузки
    loading_msg = await message.answer("✨ Генерирую идеи...")

    # Генерируем идеи подарков
    ideas = await generate_gift_ideas(
        data['gender'],
        data['age'],
        data['budget'],
        interests
    )

    await bot.delete_message(message.chat.id, loading_msg.message_id)

    if not ideas:
        await message.answer("К сожалению, не удалось сгенерировать идеи. Попробуй ещё раз.")
        await state.clear()
        return

    response = "🎁 Вот несколько идей для подарка:\n\n" + "\n\n".join(ideas[:5])

    # Добавляем кнопки для сохранения
    builder = InlineKeyboardBuilder()
    for idx, idea in enumerate(ideas[:3]):
        builder.add(InlineKeyboardButton(
            text=f"⭐ Сохранить идею {idx+1}",
            callback_data=f"save_{idx}"
        ))
    builder.adjust(1)

    await state.update_data(ideas=ideas)
    await message.answer(response, reply_markup=builder.as_markup())
    await state.set_state(None) # Сбрасываем состояние

@dp.message(F.text == "/random")
async def cmd_random(message: types.Message):
    """Генерация случайного подарка"""
    loading_msg = await message.answer("✨ Генерирую случайную идею...")
    idea = await generate_random_gift()
    await bot.delete_message(message.chat.id, loading_msg.message_id)

    if idea:
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(
            text="⭐ Сохранить эту идею",
            callback_data="save_random"
        ))
        await message.answer(f"🎲 Случайная идея подарка:\n\n{idea}", reply_markup=builder.as_markup())
    else:
        await message.answer("Не удалось сгенерировать идею. Попробуй ещё раз.")

@dp.callback_query(F.data.startswith("save_"))
async def save_gift_idea(callback: types.CallbackQuery, state: FSMContext):
    """Сохранение идеи в избранное"""
    action = callback.data.split("_")[1]
    data = await state.get_data()

    if action == "random":
        gift_text = callback.message.text.split("\n\n")[-1]
    else:
        idx = int(action)
        ideas = data.get("ideas", [])
        if idx < len(ideas):
            gift_text = ideas[idx]
        else:
            await callback.answer("Идея не найдена", show_alert=True)
            return

    user_id = callback.from_user.id
    if add_to_favorites(user_id, gift_text):
        await callback.answer("✅ Идея сохранена в избранное!")
    else:
        await callback.answer("⚠️ Эта идея уже в избранном")

@dp.message(F.text == "/favorites")
async def cmd_favorites(message: types.Message):
    """Показывает сохраненные идеи"""
    favorites = get_user_favorites(message.from_user.id)
    if not favorites:
        await message.answer("У тебя пока нет сохраненный идей")
        return

    response = "⭐ Твои сохранённые идеи подарков:\n\n"
    for idx, gift in enumerate(favorites, 1):
        response += f"{idx}. {gift}\n\n"

    # Кнопка для удаления
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🗑️ Удалить идею",
        callback_data="delete_favorite"
    ))

    await message.answer(response, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "delete favorite")
async def delete_favorite_start(callback: types.CallbackQuery):
    """Начинает процесс удаления из избранного"""
    favorites = get_user_favorites(callback.from_user.id)
    if not favorites:
        await callback.answer("Нет сохранённых идей для удаления", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for idx in range(len(favorites)):
        builder.add(InlineKeyboardButton(
            text=f"❌ Удалить {idx + 1}",
            callback_data=f"remove_{idx}"
        ))
    builder.adjust(3)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("remove_"))
async def remove_favorite(callback: types.CallbackQuery):
    """Удаляет идею из избранного"""
    idx = int(callback.data.split("_")[1])
    removed = remove_from_favorites(callback.from_user.id, idx)

    if removed:
        await callback.message.edit_text("✅ Идея удалена из избранного!")
    else:
        await callback.answer("Не удалось удалить идею", show_alert=True)

# Партнерские ссылки
dp.message(F.text.contains("купить"))
async def handle_buy_request(message: types.Message):
    """Предлагает партнёрские ссылки"""
    await message.answer(
        "🛒 Хочешь купить этот подарок? Вот проверенные магазины:\n\n"
        "• Ozon: https://ozon.ru\n"
        "• Wildberries: https://wildberries.ru\n"
        "• Яндекс.Маркет: https://market.yandex.ru\n\n"
        "Приятных покупок! 😊"
    )

# Запуск приложения
async def main():
    logger.info("Starting Gift Generator Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())




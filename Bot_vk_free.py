# =============================================
# 1. ТОКЕН СООБЩЕСТВА ВК
VK_TOKEN = ""
# =============================================
# 2. КЛЮЧ OpenRouter (используется и для текста, и для фото)
DEEPSEEK_API_KEY = ""
DEEPSEEK_BASE_URL = "https://openrouter.ai/api/v1"
DEEPSEEK_MODEL = "deepseek/deepseek-chat"
# 3. Модель для распознавания фото (vision) — через OpenRouter
VISION_MODEL = ""
PHOTO_DAILY_LIMIT = 15
# =============================================

import random, time, asyncio, json, math, sympy as sp, aiohttp, re
from math import comb, factorial
from vkbottle import Bot, Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import Message

# ---------- Визуальные константы ----------
SEP = "━━━━━━━━━━━━━━━━━━━━━━"
HDR = "✨ ━━━━━━━━━━━━━━━━━━ ✨"


def progress_bar(done: int, total: int, width: int = 10) -> str:
    """Прогресс-бар ▰▰▰▱▱▱▱▱▱▱"""
    if total <= 0:
        return "▱" * width
    filled = max(0, min(width, int(round(done / total * width))))
    return "▰" * filled + "▱" * (width - filled)


def score_feedback(correct: int, total: int) -> str:
    """Текстовая мотивашка по результату"""
    if total == 0:
        return ""
    ratio = correct / total
    if ratio == 1.0:
        return "🏆 Идеально! Ты просто гений!"
    if ratio >= 0.8:
        return "🌟 Отличный результат!"
    if ratio >= 0.6:
        return "👍 Неплохо, продолжай в том же духе!"
    if ratio >= 0.4:
        return "💪 Есть над чем поработать!"
    return "📚 Стоит ещё потренироваться!"


# ---------- Состояния ----------
user_states = {}
STATE_AI_TEXT = "ai_text"
STATE_AI_PHOTO = "ai_photo"
STATE_AI_GEN_DESCR = "ai_gen_descr"
STATE_AI_GEN_ANSWER = "ai_gen_answer"
STATE_SOLVE = "solve"


def get_state(peer_id): return user_states.get(peer_id)


def set_state(peer_id, state): user_states[peer_id] = state


def clear_state(peer_id): user_states.pop(peer_id, None)


# ---------- DeepSeek ----------
AI_TEXT_AVAILABLE = False
openai_client = None
if DEEPSEEK_API_KEY:
    try:
        from openai import AsyncOpenAI

        openai_client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            default_headers={
                "HTTP-Referer": "ссылка на ваше сообщество во ВКонтакте",
                "X-Title": "MathBot"
            }
        )
        AI_TEXT_AVAILABLE = True
        print(f"🤖 DeepSeek подключён ({DEEPSEEK_MODEL})")
    except ImportError:
        print("⚠️ pip install openai")

AI_PHOTO_AVAILABLE = AI_TEXT_AVAILABLE
if AI_PHOTO_AVAILABLE:
    print(f"📷 Фото-помощь подключена ({VISION_MODEL})")

bot = Bot(token=VK_TOKEN)
sessions = {}
photo_usage = {}

# ---------- Последнее сообщение бота (для удаления) ----------
last_bot_msg: dict[int, int] = {}


async def send_clean(message, text: str, keyboard=None, delete_prev: bool = True):
    """Отправляет сообщение, удаляя предыдущее сообщение бота в этом диалоге."""
    peer_id = message.peer_id

    if delete_prev:
        prev_id = last_bot_msg.get(peer_id)
        if prev_id:
            try:
                await message.ctx_api.messages.delete(
                    message_ids=[prev_id],
                    delete_for_all=True,
                )
            except Exception as e:
                print(f"⚠️ Не удалось удалить сообщение {prev_id}: {e}")

    sent = None
    try:
        sent = await message.answer(text, keyboard=keyboard)
    except Exception as e:
        print(f"⚠️ Ошибка отправки с клавиатурой: {e}")
        try:
            sent = await message.answer(text)
        except Exception as e2:
            print(f"⚠️ Повторная ошибка отправки: {e2}")
            return None

    if isinstance(sent, int):
        msg_id = sent
    elif isinstance(sent, dict):
        msg_id = sent.get("message_id")
    else:
        msg_id = getattr(sent, "message_id", None)

    if msg_id:
        last_bot_msg[peer_id] = msg_id
    return sent


# ---------- Лидеры ----------
import os

LEADERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leaders.json")


def load_leaders() -> dict:
    if not os.path.exists(LEADERS_FILE):
        return {}
    try:
        with open(LEADERS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {int(k): v for k, v in raw.items()}
    except Exception as e:
        print(f"⚠️ Не удалось загрузить таблицу лидеров: {e}")
        return {}


def save_leaders():
    try:
        with open(LEADERS_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in leaders.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Не удалось сохранить таблицу лидеров: {e}")


leaders = load_leaders()
print(f"🏆 Таблица лидеров загружена: {len(leaders)} записей")


# ---------- Клавиатуры ----------
def main_menu():
    return (Keyboard(one_time=False, inline=True)
            .add(Text("🧠 Помощь ИИ", payload={"cmd": "ai"}), color=KeyboardButtonColor.POSITIVE)
            .row()
            .add(Text("📝 Генератор примеров", payload={"cmd": "gen"}), color=KeyboardButtonColor.PRIMARY)
            .row()
            .add(Text("🤖 Генератор примеров ИИ", payload={"cmd": "ai_gen"}), color=KeyboardButtonColor.POSITIVE)
            .row()
            .add(Text("🏆 Таблица лидеров", payload={"cmd": "leaders"}), color=KeyboardButtonColor.SECONDARY)
            .get_json())


def cancel_keyboard():
    return (Keyboard(one_time=False, inline=True)
            .add(Text("⛔ Отмена", payload={"cmd": "menu"}), color=KeyboardButtonColor.NEGATIVE)
            .get_json())


def ai_mode_menu():
    kb = Keyboard(one_time=False, inline=True)
    if AI_TEXT_AVAILABLE:
        kb.add(Text("📝 Текстовый вопрос", payload={"cmd": "ai_text"}), color=KeyboardButtonColor.PRIMARY)
    if AI_PHOTO_AVAILABLE:
        kb.row()
        kb.add(Text("📷 Вопрос по фото", payload={"cmd": "ai_photo"}), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text("⬅ Назад", payload={"cmd": "menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def class_menu():
    kb = Keyboard(one_time=False, inline=True)
    for cls in [5, 6]:
        kb.add(Text(f"{cls} класс", payload={"cmd": f"class_{cls}"}))
    kb.row()
    kb.add(Text("⬅ Назад", payload={"cmd": "menu"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def subject_menu_for_class(cls):
    kb = Keyboard(one_time=False, inline=True)
    if cls in [5, 6]:
        kb.add(Text("📚 Математика", payload={"cmd": f"cat_{cls}_math"}), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text("⬅ Назад", payload={"cmd": "gen"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def count_menu():
    return (Keyboard(one_time=False, inline=True)
            .add(Text("5 примеров", payload={"cmd": "cnt_5"}))
            .add(Text("10 примеров", payload={"cmd": "cnt_10"}))
            .add(Text("20 примеров", payload={"cmd": "cnt_20"}))
            .row()
            .add(Text("⬅ Назад", payload={"cmd": "gen"}), color=KeyboardButtonColor.SECONDARY)
            .get_json())


def mode_menu():
    return (Keyboard(one_time=False, inline=True)
            .add(Text("🧠 Мини-игра", payload={"cmd": "mode_game"}), color=KeyboardButtonColor.POSITIVE)
            .add(Text("📝 Тренировка", payload={"cmd": "mode_train"}))
            .row()
            .add(Text("⬅ Назад", payload={"cmd": "menu"}), color=KeyboardButtonColor.SECONDARY)
            .get_json())


def back_button():
    return (Keyboard(one_time=False, inline=True)
            .add(Text("⬅ В меню", payload={"cmd": "menu"}), color=KeyboardButtonColor.SECONDARY)
            .get_json())


def train_keyboard():
    return (Keyboard(one_time=False, inline=True)
            .add(Text("🆘 Помощь с решением", payload={"cmd": "help_solve"}), color=KeyboardButtonColor.POSITIVE)
            .row()
            .add(Text("⬅ В меню", payload={"cmd": "menu"}), color=KeyboardButtonColor.SECONDARY)
            .get_json())


def game_keyboard():
    return (Keyboard(one_time=False, inline=True)
            .add(Text("🆘 Помощь с решением", payload={"cmd": "help_solve"}), color=KeyboardButtonColor.POSITIVE)
            .row()
            .add(Text("⬅ В меню", payload={"cmd": "menu"}), color=KeyboardButtonColor.SECONDARY)
            .get_json())


def game_end():
    return (Keyboard(one_time=False, inline=True)
            .add(Text("🏆 Таблица лидеров", payload={"cmd": "leaders"}))
            .row()
            .add(Text("🚪 В меню", payload={"cmd": "menu"}), color=KeyboardButtonColor.SECONDARY)
            .get_json())


# ============================================================
#  ГЕНЕРАТОР ПРИМЕРОВ (Не полный код)
# ============================================================
def generate_problem(category):
    parts = category.split('_')
    cls = int(parts[0])
    subject = parts[1]

    # ---------- 5-6 классы: Математика ----------
    if cls in [5, 6] and subject == "math":
        t = random.choice(['arithm', 'fraction', 'percent', 'equation', 'motion', 'area_vol',
                           'part_of_number', 'number_by_part', 'mean', 'compare',
                           'percent_from_number', 'percent_relation', 'ratio', 'scale'])
        if t == 'arithm':
            a = random.randint(1, 100);
            b = random.randint(1, 100);
            op = random.choice(['+', '-', '*', '/'])
            if op == '+':
                ans = a + b; expr = f"{a} + {b} = ?"; sol = f"Сложение: {a} + {b} = {ans}"; diff = 1
            elif op == '-':
                if a < b: a, b = b, a
                ans = a - b;
                expr = f"{a} - {b} = ?";
                sol = f"Вычитание: {a} - {b} = {ans}";
                diff = 1
            elif op == '*':
                if cls == 6:
                    a = random.randint(10, 99); b = random.randint(10, 99)
                else:
                    a = random.randint(2, 9); b = random.randint(2, 9)
                ans = a * b;
                expr = f"{a} * {b} = ?";
                sol = f"Умножение: {a} · {b} = {ans}";
                diff = 2 if cls == 6 else 1
            else:
                if cls == 6:
                    b = random.randint(2, 20); a = b * random.randint(2, 10)
                else:
                    b = random.randint(2, 9); a = b * random.randint(2, 9)
                ans = a // b;
                expr = f"{a} : {b} = ?";
                sol = f"Деление: {a} ÷ {b} = {ans}";
                diff = 2 if cls == 6 else 1
        elif t == 'fraction':
            den = random.randint(2, 12);
            num1 = random.randint(1, den - 2) if den > 2 else 1
            max_num2 = den - num1;
            num2 = random.randint(1, max_num2);
            op = random.choice(['+', '-'])
            if op == '+':
                ans_num = num1 + num2;
                expr = f"{num1}/{den} + {num2}/{den} = ?"
                sol = f"Сложение: ({num1}+{num2})/{den} = {ans_num}/{den}"
                ans = "1" if ans_num == den else f"{ans_num}/{den}";
                diff = 2
            else:
                if num1 < num2: num1, num2 = num2, num1
                ans_num = num1 - num2;
                expr = f"{num1}/{den} - {num2}/{den} = ?"
                sol = f"Вычитание: ({num1}-{num2})/{den} = {ans_num}/{den}"
                ans = "0" if ans_num == 0 else f"{ans_num}/{den}";
                diff = 2
        elif t == 'percent':
            total = random.randint(100, 500);
            perc = random.randint(10, 90)
            ans = total * perc / 100;
            expr = f"Сколько будет {perc}% от {total}?"
            sol = f"{perc}% от {total} = {total} * {perc} / 100 = {ans}";
            diff = 3
        elif t == 'equation':
            a = random.randint(1, 30);
            b = random.randint(a + 1, a + 50)
            expr = f"Решите уравнение: x + {a} = {b}";
            ans = b - a;
            sol = f"x = {b} - {a} = {ans}";
            diff = 2
        elif t == 'motion':
            v = random.randint(10, 60);
            t_val = random.randint(2, 5);
            ans = v * t_val
            expr = f"Расстояние за {t_val} ч со скоростью {v} км/ч?";
            sol = f"S = {v} * {t_val} = {ans} км";
            diff = 2
        elif t == 'area_vol':
            if random.random() > 0.5:
                a = random.randint(2, 15);
                b = random.randint(2, 15);
                ans = a * b
                expr = f"Площадь прямоугольника {a}×{b} см?";
                sol = f"S = {a}*{b} = {ans} см²";
                diff = 2
            else:
                a = random.randint(2, 8);
                b = random.randint(2, 8);
                c = random.randint(2, 8);
                ans = a * b * c
                expr = f"Объём параллелепипеда {a}×{b}×{c} см?";
                sol = f"V = {a}*{b}*{c} = {ans} см³";
                diff = 3
        elif t == 'part_of_number':
            total = random.randint(20, 100);
            num = random.randint(1, 10);
            den = random.randint(2, 10)
            ans = total * num / den
            ans = int(ans) if float(ans).is_integer() else round(ans, 2)
            expr = f"Найдите {num}/{den} от числа {total}";
            sol = f"{num}/{den} * {total} = {ans}";
            diff = 3
        elif t == 'number_by_part':
            num = random.randint(1, 5);
            den = random.randint(2, 6)
            part_val = random.randint(10, 30) * den // num;
            total = part_val * den // num
            expr = f"Число, если {num}/{den} его равны {part_val}";
            ans = total
            sol = f"{num}/{den} * x = {part_val} => x = {ans}";
            diff = 3
        elif t == 'mean':
            count = random.randint(3, 5);
            numbers = [random.randint(1, 20) for _ in range(count)]
            ans = round(sum(numbers) / count, 2)
            expr = f"Среднее: {', '.join(map(str, numbers))}";
            sol = f"({'+'.join(map(str, numbers))}) / {count} = {ans}";
            diff = 2
        elif t == 'compare':
            a = random.randint(1, 10);
            b = random.randint(1, 10);
            c = random.randint(1, 10);
            d = random.randint(1, 10)
            val1 = a * b;
            val2 = c + d;
            ans = ">" if val1 > val2 else ("<" if val1 < val2 else "=")
            expr = f"Сравните: {a} * {b} ? {c} + {d}";
            sol = f"{val1} {ans} {val2}";
            diff = 1
        elif t == 'percent_from_number':
            total = random.randint(100, 500);
            perc = random.randint(10, 90);
            ans = total * perc / 100
            expr = f"Найдите {perc}% от числа {total}";
            sol = f"{total} * {perc}/100 = {ans}";
            diff = 2
        elif t == 'percent_relation':
            a = random.randint(10, 50);
            b = random.randint(10, 50)
            if a == b: b += random.randint(1, 5)
            ans = round(a / b * 100, 2)
            expr = f"Сколько % составляет {a} от {b}?";
            sol = f"{a}/{b} * 100 = {ans}%";
            diff = 3
        elif t == 'ratio':
            a = random.randint(1, 10);
            b = random.randint(1, 10)
            expr = f"Отношение {a} к {b}";
            ans = f"{a}:{b}";
            sol = f"Отношение = {a}:{b}";
            diff = 1
        elif t == 'scale':
            real = random.randint(100, 1000);
            scale = random.choice([100, 200, 500, 1000])
            map_len = real / scale
            expr = f"На карте 1:{scale} расстояние {map_len} см. Расстояние на местности?"
            ans = real;
            sol = f"{map_len} * {scale} = {real} см";
            diff = 2
        return {"expr": expr, "answer": str(ans), "solution": sol, "difficulty": diff}

def check_answer(user_answer, correct_answer):
    user = str(user_answer).strip().replace(" ", "")
    if isinstance(correct_answer, list):
        try:
            user_parts = user.replace(",", " ").split()
            user_vals = []
            for p in user_parts:
                try:
                    user_vals.append(round(float(eval(p)), 3))
                except:
                    user_vals.append(p.lower())
            corr_vals = []
            for c in correct_answer:
                try:
                    corr_vals.append(round(float(eval(str(c))), 3))
                except:
                    corr_vals.append(str(c).lower())
            return set(user_vals) == set(corr_vals)
        except:
            return user.lower() == ",".join(str(c) for c in correct_answer).lower()
    else:
        ca = str(correct_answer)
        if any(ch in ca for ch in ["x=", "y=", "(", "∪", "∈", "нет", "R"]):
            return user.lower().replace(" ", "") == ca.lower().replace(" ", "")
        try:
            return abs(round(float(eval(user.replace(",", "."))), 3) - round(float(eval(ca)), 3)) < 0.011
        except:
            return user.lower().replace(" ", "") == ca.lower().replace(" ", "")


# ============================================================
#  ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: имя пользователя
# ============================================================
async def get_user_name(ctx_api, user_id: int) -> str:
    try:
        users = await ctx_api.users.get(user_ids=[user_id])
        if users:
            u = users[0]
            return f"{u.first_name} {u.last_name}"
    except Exception as e:
        print(f"⚠️ Не удалось получить имя пользователя {user_id}: {e}")
    return f"id{user_id}"


# ============================================================
#  ЛИМИТ ФОТО-ЗАПРОСОВ НА ПОЛЬЗОВАТЕЛЯ (в сутки)
# ============================================================
def get_photo_usage_today(peer_id: int) -> int:
    today = time.strftime("%Y-%m-%d")
    rec = photo_usage.get(peer_id)
    if not rec or rec.get("date") != today:
        return 0
    return rec.get("count", 0)


def increment_photo_usage(peer_id: int):
    today = time.strftime("%Y-%m-%d")
    rec = photo_usage.get(peer_id)
    if not rec or rec.get("date") != today:
        photo_usage[peer_id] = {"date": today, "count": 1}
    else:
        rec["count"] += 1


# ============================================================
#  ГЕНЕРАЦИЯ ПРИМЕРОВ ЧЕРЕЗ DeepSeek (несколько сразу)
# ============================================================
async def generate_ai_examples(description: str, count: int):
    """Генерирует count примеров. Возвращает список [{'example':..., 'answer':...}, ...]"""
    if not openai_client:
        return []
    try:
        response = await openai_client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": (
                    f"Ты — генератор математических примеров. Пользователь опишет, какие примеры он хочет. "
                    f"Сгенерируй РОВНО {count} примеров и дай правильные ответы. "
                    f"Ответь СТРОГО в формате JSON-массива без лишнего текста и без markdown: "
                    f'[{{"example": "текст примера", "answer": "правильный ответ"}}, ...] '
                    "Примеры должны быть понятными, без LaTeX, дроби через /, степени через ^. "
                    "Все примеры должны быть разными."
                )},
                {"role": "user", "content": description}
            ],
            max_tokens=2500,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        # Иногда модель заворачивает в ```json ... ```
        content = re.sub(r'^```(?:json)?\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE).strip()
        # на всякий случай — вырезаем всё до первой [ и после последней ]
        l = content.find('[')
        r = content.rfind(']')
        if l != -1 and r != -1 and r > l:
            content = content[l:r + 1]
        data = json.loads(content)
        if isinstance(data, dict):
            data = [data]
        result = []
        for d in data:
            if isinstance(d, dict):
                ex = str(d.get("example", "")).strip()
                ans = str(d.get("answer", "")).strip()
                if ex and ans:
                    result.append({"example": ex, "answer": ans})
        return result[:count]
    except Exception as e:
        print(f"Ошибка генерации примеров: {e}")
        return []


# ============================================================
#  ЕДИНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ============================================================
@bot.on.private_message()
async def handle_message(message: Message):
    peer_id = message.peer_id
    state = get_state(peer_id)

    # ---------- Обработка кнопок (payload) ----------
    if message.payload:
        if state in (STATE_AI_TEXT, STATE_AI_PHOTO, STATE_AI_GEN_DESCR, STATE_AI_GEN_ANSWER):
            clear_state(peer_id)

        try:
            payload = json.loads(message.payload) if isinstance(message.payload, str) else message.payload
        except:
            payload = {}
        cmd = payload.get("cmd", "")

        if cmd == "menu":
            await send_clean(
                message,
                f"{HDR}\n   🏠 ГЛАВНОЕ МЕНЮ\n{HDR}\n\n"
                "Выбери, чем хочешь заняться 👇",
                keyboard=main_menu()
            )
        elif cmd == "gen":
            await send_clean(
                message,
                f"{HDR}\n   📚 ВЫБОР КЛАССА\n{HDR}\n\n"
                "Для какого класса готовим примеры?",
                keyboard=class_menu()
            )
        elif cmd == "ai_gen":
            if not AI_TEXT_AVAILABLE:
                await send_clean(message, "❌ ИИ временно недоступен.", keyboard=main_menu())
                return
            set_state(peer_id, STATE_AI_GEN_DESCR)
            await send_clean(
                message,
                f"{HDR}\n   🤖 ГЕНЕРАТОР ИИ\n{HDR}\n\n"
                "📝 Опиши, какие примеры ты хочешь.\n"
                "Можно указать количество — например:\n"
                "   • «5 примеров на проценты»\n"
                "   • «3 квадратных уравнения»\n"
                "   • «10 задач на производные»\n\n"
                "Если число не укажешь — сгенерирую 1 пример.\n"
                "Максимум — 10 за раз.\n\n"
                "✍️ Напиши свой запрос:",
                keyboard=cancel_keyboard()
            )
        elif cmd == "leaders":
            try:
                def get_score(v):
                    if isinstance(v, dict):
                        try:
                            return int(v.get("score", 0))
                        except (TypeError, ValueError):
                            return 0
                    try:
                        return int(v)
                    except (TypeError, ValueError):
                        return 0

                def get_name(uid, data):
                    if isinstance(data, dict):
                        return str(data.get("name") or f"id{uid}")
                    return f"id{uid}"

                if not leaders:
                    await send_clean(
                        message,
                        f"{HDR}\n   🏆 ТАБЛИЦА ЛИДЕРОВ\n{HDR}\n\n"
                        "Пока пусто... 😢\n\n"
                        "🎮 Сыграй в мини-игру, чтобы попасть в топ!",
                        keyboard=main_menu(),
                    )
                else:
                    sorted_l = sorted(
                        leaders.items(),
                        key=lambda x: get_score(x[1]),
                        reverse=True,
                    )

                    medals = ["🥇", "🥈", "🥉"]
                    lines = [
                        f"{HDR}",
                        "   🏆 ТОП-10 ЛИДЕРОВ",
                        f"{HDR}",
                        "",
                    ]
                    for i, (uid, data) in enumerate(sorted_l[:10], 1):
                        prefix = medals[i - 1] if i <= 3 else f"  {i}."
                        lines.append(
                            f"{prefix} {get_name(uid, data)} — {get_score(data)} ⭐"
                        )

                    if peer_id in leaders:
                        my_score = get_score(leaders[peer_id])
                        my_name = get_name(peer_id, leaders[peer_id])
                        place = sum(
                            1 for v in leaders.values() if get_score(v) > my_score
                        ) + 1
                        lines.append("")
                        lines.append(SEP)
                        lines.append(
                            f"🔹 Ты: {my_name}\n"
                            f"    Место: {place} • Очки: {my_score} ⭐"
                        )

                    text = "\n".join(lines)
                    await send_clean(message, text, keyboard=main_menu())

            except Exception as e:
                import traceback
                traceback.print_exc()
                await send_clean(
                    message,
                    f"⚠️ Ошибка таблицы лидеров: {e}",
                    keyboard=main_menu(),
                )
        elif cmd.startswith("class_"):
            cls = int(cmd.split("_")[1])
            sessions[peer_id] = {"class": cls}
            await send_clean(
                message,
                f"{HDR}\n   ✅ {cls} КЛАСС\n{HDR}\n\n"
                "Теперь выбери предмет 👇",
                keyboard=subject_menu_for_class(cls)
            )
        elif cmd.startswith("cat_"):
            parts = cmd.split("_")
            cls = int(parts[1]);
            subject = parts[2]
            sessions.setdefault(peer_id, {})["category"] = f"{cls}_{subject}"
            names = {"math": "Математика 📚", "alg": "Алгебра 📐",
                     "geom": "Геометрия 📏", "stat": "Вероятность и статистика 📊"}
            await send_clean(
                message,
                f"{HDR}\n   🎯 {names.get(subject, subject).upper()}\n{HDR}\n\n"
                "Выбери режим 👇",
                keyboard=mode_menu()
            )
        elif cmd == "mode_game":
            session = sessions.get(peer_id)
            if not session or "category" not in session:
                await send_clean(message, "Сначала выберите предмет.", keyboard=class_menu())
            else:
                session["mode"] = "game"
                session["score"] = 0
                await send_clean(
                    message,
                    f"{HDR}\n   🎮 МИНИ-ИГРА\n{HDR}\n\n"
                    "За правильные ответы — очки ⭐\n"
                    "Чем сложнее пример — тем больше очков!\n\n"
                    "Сколько примеров сыграем? 👇",
                    keyboard=count_menu()
                )
        elif cmd == "mode_train":
            session = sessions.get(peer_id)
            if not session or "category" not in session:
                await send_clean(message, "Сначала выберите предмет.", keyboard=class_menu())
            else:
                session["mode"] = "train"
                session["score"] = 0
                await send_clean(
                    message,
                    f"{HDR}\n   📝 ТРЕНИРОВКА\n{HDR}\n\n"
                    "Задачи идут от простых к сложным.\n"
                    "Можно пользоваться подсказкой 💡\n\n"
                    "Сколько примеров решаем? 👇",
                    keyboard=count_menu()
                )
        elif cmd.startswith("cnt_"):
            count = int(cmd.split("_")[1])
            session = sessions.get(peer_id)
            if not session or "category" not in session:
                await send_clean(message, "Ошибка. Напишите 'начать'.", keyboard=main_menu())
            else:
                problems = [generate_problem(session["category"]) for _ in range(count)]
                problems.sort(key=lambda p: p["difficulty"])
                session["problems"] = problems
                session["current"] = 0
                session["total"] = count
                mode = session.get("mode", "train")
                time_msg = ""
                if mode == "game":
                    limits = {5: (30 * 60, "30 мин"), 10: (60 * 60, "1 ч"), 20: (90 * 60, "1 ч 30 мин")}
                    tl, hint = limits.get(count, (60 * 60, "1 ч"))
                    session["start_time"] = time.time()
                    session["time_limit"] = tl
                    time_msg = f"⏳ Лимит времени: {hint}\n"
                prob = problems[0]
                bar = progress_bar(0, count)
                if mode == "game":
                    msg = (
                        f"{HDR}\n   🎮 МИНИ-ИГРА\n{HDR}\n"
                        f"{time_msg}\n"
                        f"🎯 Пример 1/{count}   {bar}\n"
                        f"⭐ Сложность: {prob['difficulty']}/5\n"
                        f"{SEP}\n\n"
                        f"{prob['expr']}\n\n"
                        f"{SEP}\n"
                        f"✍️ Твой ответ:"
                    )
                    kb = game_keyboard()
                else:
                    msg = (
                        f"{HDR}\n   📝 ТРЕНИРОВКА\n{HDR}\n"
                        f"🎯 Пример 1/{count}   {bar}\n"
                        f"⭐ Сложность: {prob['difficulty']}/5\n"
                        f"{SEP}\n\n"
                        f"{prob['expr']}\n\n"
                        f"{SEP}\n"
                        f"✍️ Твой ответ:"
                    )
                    kb = train_keyboard()
                set_state(peer_id, STATE_SOLVE)
                await send_clean(message, msg, keyboard=kb)
        elif cmd == "help_solve":
            session = sessions.get(peer_id)
            if state != STATE_SOLVE or not session:
                return
            prob = session["problems"][session["current"]]
            ans_str = prob["answer"] if not isinstance(prob["answer"], list) else ", ".join(prob["answer"])
            sol_text = f"💡 Решение: {prob['solution']}\n✅ Ответ: {ans_str}"
            session["current"] += 1
            if session["current"] >= session["total"]:
                clear_state(peer_id)
                await send_clean(
                    message,
                    f"{sol_text}\n\n{SEP}\n🏁 Тренировка завершена!",
                    keyboard=main_menu()
                )
            else:
                nxt = session["problems"][session["current"]]
                num = session["current"] + 1
                total = session["total"]
                bar = progress_bar(session["current"], total)
                kb = game_keyboard() if session.get("mode") == "game" else train_keyboard()
                await send_clean(
                    message,
                    f"{sol_text}\n\n{SEP}\n"
                    f"🎯 Пример {num}/{total}   {bar}\n\n"
                    f"{nxt['expr']}\n\n{SEP}\n✍️ Твой ответ:",
                    keyboard=kb
                )
        elif cmd == "ai":
            await send_clean(
                message,
                f"{HDR}\n   🧠 ПОМОЩЬ ИИ\n{HDR}\n\n"
                "Как удобнее задать вопрос? 👇",
                keyboard=ai_mode_menu()
            )
        elif cmd == "ai_text":
            if not AI_TEXT_AVAILABLE:
                await send_clean(message, "❌ ИИ временно недоступен.", keyboard=main_menu())
                return
            set_state(peer_id, STATE_AI_TEXT)
            await send_clean(
                message,
                f"{HDR}\n   📝 ТЕКСТОВЫЙ ВОПРОС\n{HDR}\n\n"
                "Напиши вопрос или задачу — я отвечу.\n\n"
                "✍️ Пиши сюда:",
                keyboard=back_button()
            )
        elif cmd == "ai_photo":
            if not AI_PHOTO_AVAILABLE:
                await send_clean(message, "❌ Фото-помощь недоступна.", keyboard=main_menu())
                return
            set_state(peer_id, STATE_AI_PHOTO)
            await send_clean(
                message,
                f"{HDR}\n   📷 ВОПРОС ПО ФОТО\n{HDR}\n\n"
                "Пришли фото задания — распознаю и решу.\n\n"
                "📸 Жду фото...",
                keyboard=back_button()
            )
        else:
            await send_clean(message, "Используйте кнопки меню.", keyboard=main_menu())
        return

    # ---------- Состояния ИИ-помощников ----------
    if state == STATE_AI_TEXT:
        if not openai_client:
            await send_clean(message, "❌ ИИ недоступен.", keyboard=main_menu())
            clear_state(peer_id)
            return
        try:
            response = await openai_client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "Ты — помощник. Отвечай простым текстом, без LaTeX."},
                    {"role": "user", "content": message.text}
                ],
                max_tokens=1500, temperature=0.3
            )
            answer = response.choices[0].message.content
            answer = re.sub(r'\\\[|\\\]|\\\(|\\\)|\$\$?', '', answer)
            answer = re.sub(r'\\frac\{[^}]*\}\{[^}]*\}', '', answer)
            answer = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', answer)
            answer = answer.replace('\\', '').replace('{', '').replace('}', '')
            answer = re.sub(r' +', ' ', answer).strip()
        except Exception as e:
            answer = f"⚠️ Ошибка ИИ: {e}"
        clear_state(peer_id)
        await send_clean(
            message,
            f"{HDR}\n   ✅ ОТВЕТ ИИ\n{HDR}\n\n{answer}",
            keyboard=main_menu()
        )
        return

    if state == STATE_AI_PHOTO:
        if not message.attachments:
            await send_clean(message, "📷 Пришлите фото.", keyboard=back_button())
            return
        photo = None
        for att in message.attachments:
            if att.photo:
                photo = att.photo
                break
        if not photo:
            await send_clean(message, "📷 Пришлите фото.", keyboard=back_button())
            return
        used_today = get_photo_usage_today(peer_id)
        if used_today >= PHOTO_DAILY_LIMIT:
            await send_clean(
                message,
                f"⏳ Лимит фото исчерпан ({PHOTO_DAILY_LIMIT}/{PHOTO_DAILY_LIMIT}).",
                keyboard=main_menu()
            )
            clear_state(peer_id)
            return
        await send_clean(message, "🔍 Анализирую фото... ⏳")
        try:
            import base64
            url = photo.sizes[-1].url
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url) as resp:
                    data = await resp.read()
            b64 = base64.b64encode(data).decode("utf-8")
            user_content = [
                {"type": "text", "text": "Реши задачу на фото."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
            response = await openai_client.chat.completions.create(
                model=VISION_MODEL,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=1500, temperature=0.3
            )
            answer = response.choices[0].message.content
            answer = re.sub(r'\\\[|\\\]|\\\(|\\\)|\$\$?', '', answer)
            answer = re.sub(r'\\frac\{[^}]*\}\{[^}]*\}', '', answer)
            answer = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', answer)
            answer = answer.replace('\\', '').replace('{', '').replace('}', '')
            answer = re.sub(r' +', ' ', answer).strip()
            increment_photo_usage(peer_id)
            remaining = PHOTO_DAILY_LIMIT - get_photo_usage_today(peer_id)
            footer = f"\n\n{SEP}\n📊 Осталось фото-запросов сегодня: {remaining}/{PHOTO_DAILY_LIMIT}"
        except Exception as e:
            answer = f"⚠️ Ошибка обработки фото: {e}"
            footer = ""
        clear_state(peer_id)
        await send_clean(
            message,
            f"{HDR}\n   ✅ ОТВЕТ ПО ФОТО\n{HDR}\n\n{answer}{footer}",
            keyboard=main_menu()
        )
        return

    # ---------- Генерация примеров через ИИ ----------
    if state == STATE_AI_GEN_DESCR:
        description = message.text or ""

        # Парсим количество из запроса
        m = re.search(r'(\d+)\s*(?:пример|задач|шт|штук)', description, re.IGNORECASE)
        if not m:
            m = re.search(r'\b(\d+)\b', description)
        try:
            count = int(m.group(1)) if m else 1
        except Exception:
            count = 1
        count = max(1, min(count, 10))

        await send_clean(message, f"🤖 Генерирую примеры ({count} шт.)... ⏳")

        examples = await generate_ai_examples(description, count)
        if not examples:
            await send_clean(
                message,
                "⚠️ Не удалось сгенерировать примеры. Попробуй ещё раз или переформулируй запрос.",
                keyboard=main_menu()
            )
            clear_state(peer_id)
            return

        total = len(examples)
        sessions.setdefault(peer_id, {})["ai_gen_examples"] = examples
        sessions[peer_id]["ai_gen_current"] = 0
        sessions[peer_id]["ai_gen_total"] = total
        sessions[peer_id]["ai_gen_correct"] = 0
        set_state(peer_id, STATE_AI_GEN_ANSWER)

        ex = examples[0]
        bar = progress_bar(0, total)
        text = (
            f"{HDR}\n"
            f"   🤖 ПРИМЕРЫ ОТ ИИ\n"
            f"{HDR}\n\n"
            f"🎯 Пример 1/{total}   {bar}\n"
            f"{SEP}\n\n"
            f"{ex['example']}\n\n"
            f"{SEP}\n"
            f"✍️ Напиши свой ответ:"
        )
        await send_clean(message, text, keyboard=cancel_keyboard())
        return

    if state == STATE_AI_GEN_ANSWER:
        session = sessions.get(peer_id, {})
        examples = session.get("ai_gen_examples", [])
        if not examples:
            clear_state(peer_id)
            await send_clean(message, "Сессия потеряна.", keyboard=main_menu())
            return

        idx = session.get("ai_gen_current", 0)
        total = session.get("ai_gen_total", len(examples))
        if idx >= len(examples):
            clear_state(peer_id)
            sessions.pop(peer_id, None)
            await send_clean(message, "Готово!", keyboard=main_menu())
            return

        cur = examples[idx]
        user_ans = message.text or ""
        is_correct = check_answer(user_ans, cur["answer"])

        if is_correct:
            session["ai_gen_correct"] = session.get("ai_gen_correct", 0) + 1
            feedback = "✅ Верно! Молодец!"
        else:
            feedback = f"❌ Неверно.\n💡 Правильный ответ: {cur['answer']}"

        next_idx = idx + 1
        session["ai_gen_current"] = next_idx

        # ФИНАЛ
        if next_idx >= len(examples):
            correct = session.get("ai_gen_correct", 0)
            clear_state(peer_id)
            sessions.pop(peer_id, None)
            mood = score_feedback(correct, total)
            text = (
                f"{feedback}\n\n"
                f"{HDR}\n"
                f"   🏁 РЕЗУЛЬТАТ\n"
                f"{HDR}\n\n"
                f"Правильных ответов: {correct}/{total}\n"
                f"Точность: {round(correct / total * 100)}%\n\n"
                f"{mood}"
            )
            await send_clean(message, text, keyboard=main_menu())
            return

        # СЛЕДУЮЩИЙ ПРИМЕР
        nxt = examples[next_idx]
        num = next_idx + 1
        bar = progress_bar(next_idx, total)
        text = (
            f"{feedback}\n\n"
            f"{HDR}\n"
            f"   🎯 Пример {num}/{total}   {bar}\n"
            f"{HDR}\n\n"
            f"{nxt['example']}\n\n"
            f"{SEP}\n"
            f"✍️ Напиши свой ответ:"
        )
        await send_clean(message, text, keyboard=cancel_keyboard())
        return

    # ---------- Решение обычных примеров ----------
    if state == STATE_SOLVE:
        session = sessions.get(peer_id)
        if not session:
            clear_state(peer_id)
            await send_clean(message, "Сессия потеряна.", keyboard=main_menu())
            return
        idx = session["current"]
        problems = session["problems"]
        if idx >= len(problems):
            await send_clean(message, "Готово!", keyboard=main_menu())
            clear_state(peer_id)
            return
        prob = problems[idx]
        is_correct = check_answer(message.text, prob["answer"])
        mode = session.get("mode", "train")
        if is_correct:
            if mode == "game":
                session["score"] = session.get("score", 0) + prob["difficulty"]
                reply = f"✅ Верно! +{prob['difficulty']} очков! Счёт: {session['score']} ⭐"
            else:
                reply = "✅ Верно! Молодец!"
            session["current"] += 1
        else:
            ans_str = prob["answer"] if not isinstance(prob["answer"], list) else ", ".join(
                str(a) for a in prob["answer"])
            reply = (
                f"❌ Неверно.\n"
                f"💡 Правильный ответ: {ans_str}\n"
                f"📖 {prob['solution']}"
            )
            session["current"] += 1
        if session["current"] >= len(problems):
            if mode == "game":
                try:
                    score = int(session.get("score", 0))
                except (TypeError, ValueError):
                    score = 0

                try:
                    name = await get_user_name(message.ctx_api, peer_id)
                except Exception:
                    name = f"id{peer_id}"

                old = leaders.get(peer_id)
                old_score = 0
                if isinstance(old, dict):
                    try:
                        old_score = int(old.get("score", 0))
                    except (TypeError, ValueError):
                        old_score = 0
                elif isinstance(old, int):
                    old_score = old

                if old_score == 0 or score > old_score:
                    leaders[peer_id] = {"name": name, "score": score}
                    try:
                        save_leaders()
                    except Exception as e:
                        print(f"⚠️ Не удалось сохранить лидеров: {e}")

                text = (
                    f"{reply}\n\n"
                    f"{HDR}\n"
                    f"   🏁 ИГРА ОКОНЧЕНА\n"
                    f"{HDR}\n\n"
                    f"🏆 Итоговый счёт: {score} ⭐\n"
                    f"{score_feedback(session.get('score', 0), sum(p['difficulty'] for p in problems))}"
                )
                await send_clean(message, text, keyboard=game_end())
            else:
                correct_total = sum(1 for _ in problems)  # not tracked, оставим простой текст
                text = (
                    f"{reply}\n\n"
                    f"{HDR}\n"
                    f"   🏁 ТРЕНИРОВКА ЗАВЕРШЕНА\n"
                    f"{HDR}\n\n"
                    f"👏 Отличная работа!"
                )
                await send_clean(message, text, keyboard=main_menu())
            clear_state(peer_id)
        else:
            nxt = problems[session["current"]]
            num = session["current"] + 1;
            total = session["total"]
            bar = progress_bar(session["current"], total)
            if mode == "game":
                remaining = int(session.get("time_limit", 0) - (time.time() - session.get("start_time", time.time())))
                if remaining < 0:
                    remaining = 0
                mins, secs = divmod(remaining, 60)
                timer_str = f"{mins:02d}:{secs:02d}"
                text = (
                    f"{reply}\n\n"
                    f"{HDR}\n"
                    f"   🎮 Пример {num}/{total}   {bar}\n"
                    f"   ⏳ {timer_str} • ⭐ сл. {nxt['difficulty']}/5\n"
                    f"{HDR}\n\n"
                    f"{nxt['expr']}\n\n"
                    f"{SEP}\n✍️ Твой ответ:"
                )
                await send_clean(message, text, keyboard=game_keyboard())
            else:
                text = (
                    f"{reply}\n\n"
                    f"{HDR}\n"
                    f"   📝 Пример {num}/{total}   {bar}\n"
                    f"   ⭐ Сложность: {nxt['difficulty']}/5\n"
                    f"{HDR}\n\n"
                    f"{nxt['expr']}\n\n"
                    f"{SEP}\n✍️ Твой ответ:"
                )
                await send_clean(message, text, keyboard=train_keyboard())
        return

    # ---------- Приветствие и прочее ----------
    if message.text and message.text.strip().lower() in ("начать", "/start", "start", "привет"):
        await send_clean(
            message,
            f"{HDR}\n"
            f"   👋 ПРИВЕТ!\n"
            f"{HDR}\n\n"
            "Я — школьный бот-помощник по математике 🧮\n\n"
            "🔹 Решаю примеры 5–6 класс\n"
            "🔹 Помогаю с ИИ (текст)\n"
            "🔹 Генерирую примеры ИИ (можно пачкой!)\n"
            "🔹 Мини-игра с таблицей лидеров 🏆\n\n"
            "Выбери, что тебе интересно 👇",
            keyboard=main_menu()
        )
        return
    await send_clean(message, "Используй кнопки меню 👇", keyboard=main_menu())


# ---------- Запуск ----------
if __name__ == "__main__":
    print("🚀 Бот запущен...")
    asyncio.run(bot.run_polling())



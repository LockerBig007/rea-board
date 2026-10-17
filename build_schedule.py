"""Тянет расписание группы с rasp.rea.ru и пересобирает data.js.

Запуск вручную:   python build_schedule.py
В облаке:         .github/workflows/update-schedule.yml, раз в неделю.

Сайт статический, поэтому расписание лежит рядом с ним отдельным файлом
data.js. Этот скрипт — единственное место, где оно появляется.
"""

import html
import json
import os
import re
import sys
import time
from datetime import date

import requests

GROUP = "15.27д-с01/25б"
WEEKS = range(1, 19)  # 18 недель третьего семестра
URL = "https://rasp.rea.ru/Schedule/ScheduleCard"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.js")

# С октября 2026 rasp.rea.ru отвечает 403 на запрос без браузерного
# User-Agent: по умолчанию requests представляется как python-requests/2.x,
# и защита сайта такие запросы режет. Поэтому ходим как обычный браузер.
# X-Requested-With обязателен: ScheduleCard — это AJAX-кусок страницы,
# без него сайт отдаёт 404.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://rasp.rea.ru/",
}

# Ниже этих порогов ответ сайта считаем сбоем и data.js не переписываем:
# в нём лежит учебный план и предметы, на которые завязаны полки лекций.
MIN_DAYS = 40       # учебных дней в семестре заведомо больше
KEEP_SHARE = 0.8    # и не меньше 80% от того, что уже лежит в data.js
MIN_BOUND = 0.8     # доля занятий, опознанных по учебному плану

# Учебный план третьего семестра: имя, короткое имя, форма контроля,
# з.е., всего часов, контактных часов, лекций, практик, лабораторных.
# Пар = контактные часы / 2 — на этом числе строится балл за посещение.
PLAN = [
    ("Дискретная математика и математическая логика", "Дискретная математика", "Экзамен", 5, 180, 72, 24, 48, 0),
    ("Статистическое моделирование и прогнозирование", "Статмоделирование", "Дифф. зачёт", 2, 216, 52, 24, 28, 0),
    ("Исследование операций и методы оптимизации", "Исследование операций", "Экзамен", 3, 108, 42, 18, 24, 0),
    ("Иностранный язык", "Иностранный язык", "Зачёт", 2, 324, 40, 0, 40, 0),
    ("Теория вероятностей и математическая статистика", "Теория вероятностей", "Дифф. зачёт", 3, 108, 40, 18, 22, 0),
    ("Статистика внешнеэкономической деятельности", "Статистика ВЭД", "Дифф. зачёт", 2, 216, 36, 6, 0, 30),
    ("Визуализация данных и бизнес-аналитика", "Визуализация данных", "Экзамен", 4, 144, 36, 6, 0, 30),
    ("Элективные дисциплины по физической культуре и спорту", "Физкультура", "Зачёт", 0, 328, 36, 0, 36, 0),
    ("Базы данных", "Базы данных", "Зачёт", 3, 216, 34, 18, 16, 0),
    ("Философия", "Философия", "Экзамен", 3, 108, 20, 2, 18, 0),
    ("Государственная антикоррупционная политика", "Антикоррупционная политика", "Зачёт", 2, 72, 12, 2, 10, 0),
]

SEMESTER = {
    "name": "3-й семестр 2026/27",
    "start": "01.09.2026",
    "end": "31.12.2026",
    "sessStart": "09.01.2027",
    "sessEnd": "27.01.2027",
    "holStart": "28.01.2027",
    "holEnd": "31.01.2027",
    "hol": ["04.11.2026"],
}

DAY_RE = re.compile(r'<th class="dayh"[^>]*>\s*<h5[^>]*>([^<]+)</h5>')
HEAD_RE = re.compile(r"([А-ЯЁ]+),\s*(\d{2}\.\d{2}\.\d{4})")
PAIR_RE = re.compile(
    r'<span class="pcap">(\d+)\s*пара</span>'
    r'(?:<br />(\d{2}:\d{2})<br />(\d{2}:\d{2}))?'
)
TASK_RE = re.compile(r"class='task'.*?>(.*?)</a>", re.S)


def fetch(week, session, tries=3):
    # Сайт вуза иногда не отвечает на подряд идущие запросы, поэтому повтор с паузой.
    last = None
    for attempt in range(tries):
        try:
            r = session.get(
                URL,
                params={"selection": GROUP, "weekNum": week, "catfilter": 0},
                timeout=30,
            )
            r.raise_for_status()
            r.encoding = "utf-8"
            if "не найдено результатов" in r.text:
                raise RuntimeError(f"rasp.rea.ru не знает группу {GROUP}")
            return r.text
        except requests.RequestException as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"неделя {week}: {last}")


def parse_week(page, week):
    out = []
    parts = DAY_RE.split(page)
    for i in range(1, len(parts), 2):
        m = HEAD_RE.match(html.unescape(parts[i]).strip())
        if not m:
            continue
        dow, day = m.group(1), m.group(2)
        slots = []
        for block in re.split(r'<tr class="slot', parts[i + 1])[1:]:
            pm = PAIR_RE.search(block)
            task = TASK_RE.search(block)
            if not pm or not task:
                continue
            lines = [
                html.unescape(x).strip()
                for x in re.sub(r"<[^>]+>", "\n", task.group(1)).split("\n")
            ]
            lines = [x for x in lines if x and x != ","]
            if not lines:
                continue
            place = " ".join(lines[2:]).replace(", пл. Основная", "")
            place = re.sub(r"\s+", " ", place).replace(" - ", " ").strip().rstrip(",").strip()
            slots.append({
                "n": int(pm.group(1)),
                "t": (pm.group(2) or "") + ("–" + pm.group(3) if pm.group(3) else ""),
                "s": lines[0],
                "k": lines[1] if len(lines) > 1 else "",
                "p": place,
            })
        if slots:
            out.append({"w": week, "dow": dow.capitalize(), "d": day, "s": slots})
    return out


def previous():
    """Что лежит в data.js сейчас: (учебных дней, занятий).

    Нужно, чтобы сравнить с тем, что пришло с сайта, и не заменить полное
    расписание огрызком. Если файла нет или он битый — считаем, что пусто.
    """
    try:
        with open(OUT, encoding="ascii") as fh:
            text = fh.read()
        payload = json.loads(text[text.index("{"):text.rindex("}") + 1])
        days = payload.get("days", [])
        return len(days), sum(len(d.get("s", [])) for d in days)
    except (OSError, ValueError):
        return 0, 0


def check(days, had_days):
    """Проверяет, что с сайта пришло целое расписание, а не остатки."""
    floor = max(MIN_DAYS, int(had_days * KEEP_SHARE))
    if len(days) < floor:
        raise RuntimeError(
            f"сайт отдал {len(days)} учебных дней, а ожидается хотя бы {floor}"
        )
    slots = [slot for day in days for slot in day["s"]]
    bound = sum(1 for slot in slots if slot["i"] >= 0)
    if not slots or bound < len(slots) * MIN_BOUND:
        raise RuntimeError(
            f"по учебному плану опознано {bound} занятий из {len(slots)} — "
            "похоже, на сайте поменялась вёрстка или названия предметов"
        )


def write(payload):
    """Пишет data.js через временный файл, чтобы не оставить его обрезанным."""
    tmp = OUT + ".tmp"
    body = "window.BOARD=" + json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + ";"
    # ensure_ascii=True не случайно: файл остаётся чистым ASCII и читается
    # правильно даже там, где сервер не прислал charset=utf-8.
    json.loads(body[len("window.BOARD="):-1])  # контроль: это валидный JSON
    try:
        with open(tmp, "w", encoding="ascii") as fh:
            fh.write(body)
        os.replace(tmp, OUT)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main():
    had_days, had_pairs = previous()
    index = {row[0]: i for i, row in enumerate(PLAN)}
    by_date = {}
    session = requests.Session()
    session.headers.update(HEADERS)
    for week in WEEKS:
        for day in parse_week(fetch(week, session), week):
            for slot in day["s"]:
                i = index.get(slot["s"], -1)
                slot["i"] = i
                slot["x"] = slot["s"] if i < 0 else ""
                del slot["s"]
            by_date[day["d"]] = day

    def order(day):
        d, m, y = day["d"].split(".")
        return y, m, d

    days = sorted(by_date.values(), key=order)
    check(days, had_days)

    payload = {
        "group": "15.27Д-С01/25б",
        "prog": "01.03.05 Статистика · «Аналитика и управление данными»",
        "faculty": "Высшая школа кибертехнологий, математики и статистики",
        "updated": date.today().strftime("%d.%m.%Y"),
        "sem": SEMESTER,
        "subjects": [
            {"name": a, "short": b, "form": c, "zet": d, "h": e,
             "kont": f, "lec": g, "pr": h, "lab": i, "pairs": f // 2}
            for a, b, c, d, e, f, g, h, i in PLAN
        ],
        "days": days,
    }
    write(payload)

    pairs = sum(len(d["s"]) for d in days)
    print(f"data.js обновлён: {len(days)} учебных дней, {pairs} занятий "
          f"(было {had_days} и {had_pairs})")
    return 0


if __name__ == "__main__":
    # Любой сбой источника — это понятная строка в логе и ненулевой код выхода,
    # а не трассировка. data.js при этом остаётся прежним: сайт продолжает
    # показывать расписание прошлой недели, а прогон в Actions горит красным.
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f"Расписание не обновлено, data.js не тронут: {e}", file=sys.stderr)
        sys.exit(1)

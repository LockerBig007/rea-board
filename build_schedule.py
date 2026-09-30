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
from datetime import date

import requests

GROUP = "15.27д-с01/25б"
WEEKS = range(1, 19)  # 18 недель третьего семестра
URL = "https://rasp.rea.ru/Schedule/ScheduleCard"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.js")

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


def fetch(week):
    r = requests.get(
        URL,
        params={"selection": GROUP, "weekNum": week, "catfilter": 0},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    r.raise_for_status()
    r.encoding = "utf-8"
    if "не найдено результатов" in r.text:
        raise RuntimeError(f"rasp.rea.ru не знает группу {GROUP}")
    return r.text


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


def main():
    index = {row[0]: i for i, row in enumerate(PLAN)}
    by_date = {}
    for week in WEEKS:
        for day in parse_week(fetch(week), week):
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
    if len(days) < 40:
        print(f"Похоже на сбой: всего {len(days)} учебных дней, data.js не трогаю", file=sys.stderr)
        return 1

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
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("window.BOARD=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";")

    pairs = sum(len(d["s"]) for d in days)
    print(f"data.js обновлён: {len(days)} учебных дней, {pairs} занятий")
    return 0


if __name__ == "__main__":
    sys.exit(main())

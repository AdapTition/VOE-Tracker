# VOE Explorer: план реалізації

> **Для агентів-виконавців:** ОБОВ'ЯЗКОВА ДОПОМІЖНА НАВИЧКА: superpowers:subagent-driven-development (рекомендовано) або superpowers:executing-plans, задача за задачею. Кроки позначені чекбоксами (`- [ ]`).

**Мета:** десктопна Windows-програма (один exe), яка за довільно введеною адресою показує, чи є світло, чому його немає, коли увімкнуть і погодинний графік VOE, а також стежить, чи живий сайт voe.com.ua.

**Архітектура.** Чисте ядро на Python:
- розбір адрес, розбір HTML VOE, виведення статусу, класифікація стану сайту;
- над ядром тонкий мережевий клієнт (stdlib `urllib`) і сховище (JSON + SQLite у `%APPDATA%`);
- фоновий сервіс-потік періодично оновлює стан у пам'яті;
- інтерфейс — HTML/CSS/vanilla JS у вікні pywebview. JS раз на 2 с читає стан через міст `Api` і викликає дії.

**Стек:** Python 3.12 (`py`), pywebview, pytest, PyInstaller, Pillow (тільки для збірки картинки-інструкції).

**Специфікація:** `docs/superpowers/specs/2026-10-17-voe-explorer-design.md`. Посилання виду §N ведуть на неї. Виконавці читають і її, і цей план.

## Глобальні обмеження

- Лише Windows 10/11. Програма — один `VOE Explorer.exe` (PyInstaller `--onefile --windowed`), поширюється zip-архівом із двох файлів: exe і `Як запустити.png`.
- Базовий URL `https://www.voe.com.ua`. Кирилиця в query кодується тільки через `urllib.parse.quote` (UTF-8).
- Таймаут запиту 40 с, до 3 спроб з паузою 2 с при 5xx, таймауті чи мережевій помилці. Не більше кількох запитів на хвилину з однієї копії.
- Інтервали: оновлення карток 300 с, пробний запит VOE 120 с, планові роботи 3 год, перевірка оновлень раз на добу. «Повільно» — довше за 10 с.
- Дані користувача лежать у `%APPDATA%\VOE Explorer\`: `addresses.json`, `memory.json`, `voe.sqlite3`, `samples\`.
- Весь час — локальний і naive (`datetime.now()`), бо VOE віддає київський час, а машина користувача теж у Києві.
- Тексти інтерфейсу дослівно:
  - заголовки статусу: «Світло є», «Немає світла», «Можливе відключення», «Не вдалося оновити», «Сайт VOE змінився — потрібна нова версія програми»;
  - стан сайту: «VOE відповідає · {s} с», «VOE повільний · {s} с», «VOE не відповідає», «Немає інтернету»;
  - кнопки й рядки: «Встановити на цей комп'ютер», «Є нова версія», «+ Додати адресу», «Відповідь VOE», «Скопіювати», «Зберегти у файл», «графік станом на HH:MM», «Не вдалося оновити · останні дані о HH:MM».
- Візуальний напрямок «A · Світлі картки»: фон `#f6f6f3`, білі картки, Segoe UI. Макет: `.superpowers/brainstorm/187-1792224099/content/visual-style.html`, варіант A.
- Тести ніколи не ходять у живу мережу. Мережа в тестах підміняється фейковим `opener`.
- Команди тестів (Git Bash, з кореня проєкту): `.venv/Scripts/python -m pytest -q`.

## На що звернути увагу при рецензуванні

1. **Вулиця без типу при кількох типах-кандидатах** («Ботанічний 10») — завжди вибір, жодного автоматичного рішення. Тест у задачі 4.
2. **Застарілі дані після сну чи вимкнення ноутбука** (останнє оновлення 3 год тому) — «Не вдалося оновити», а не старе «Світло є». В історії VOE цей проміжок — «немає даних». Тести в задачах 3 і 7.
3. **VOE віддає 200, але тіло — сторінка помилки Cloudflare або порожній `[]` автокомпліту.** Це не «нічого не знайдено» і не «світло є»: для графіка — `ParseError`, для моніторингу — `down`. Тести в задачах 2, 5 і 7.
4. **Межа доби й року.** Рядок дня `чт 01.01`, коли запит зроблено 31.12. Таблиця без класу `current_day`. Тест у задачі 2.
5. **Варіанти номера будинку:** `12a` латиницею, `12-А`, `12 а`, `10/2` проти `12А`, `10/2` з VOE. Тест у задачі 1.

---

## Структура файлів

```
voe explorer/
  pyproject.toml                 # пакет voe_explorer, залежності, pytest
  .gitignore                     # .venv/ dist/ build/ __pycache__/ .superpowers/ *.spec
  src/voe_explorer/
    __init__.py                  # __version__ = "0.1.0"
    __main__.py                  # точка входу: python -m voe_explorer
    config.py                    # константи (інтервали, URL, RELEASES_REPO, шляхи)
    models.py                    # dataclass-и та enum-и ядра
    address_parse.py             # розбір вводу та назв вулиць VOE, нормалізація будинку
    schedule_parse.py            # розбір AJAX-відповіді графіка
    status.py                    # виведення статусу картки (правило «гірше перемагає»)
    net.py                       # HTTP з повторами і звітом про кожну спробу
    voe_client.py                # автокомпліт, графік, планові роботи
    resolver.py                  # вибір вулиці/будинку + пам'ять
    planned.py                   # розбір сторінки планових робіт, зіставлення, РЕМ
    storage.py                   # addresses.json, memory.json, SQLite (probes, responses), samples
    health.py                    # класифікація проб, сегменти історії, статистика
    service.py                   # фонові цикли та знімок стану для UI
    updates.py                   # перевірка релізів на GitHub
    install.py                   # «Встановити на цей комп'ютер»
    api.py                       # міст pywebview (методи для JS)
    ui/index.html  ui/app.css  ui/app.js
  tests/
    fixtures/                    # копії docs/research/samples + синтетичні
    test_address_parse.py test_schedule_parse.py test_status.py test_net_client.py
    test_resolver.py test_planned.py test_storage.py test_health.py test_service.py
    test_updates_install.py test_api.py
  packaging/
    build.ps1                    # venv → pyinstaller → zip
    make_howto.py                # малює «Як запустити.png» (Pillow)
```

---

### Задача 1: Каркас проєкту + розбір адрес

**Файли:**
- Створити: `pyproject.toml`, `.gitignore`, `src/voe_explorer/__init__.py`, `src/voe_explorer/models.py` (лише типи цієї задачі), `src/voe_explorer/address_parse.py`
- Тест: `tests/test_address_parse.py`

**Інтерфейси:**
- Створює (`models.py`):
  ```python
  @dataclass(frozen=True)
  class StreetName:
      kind: str | None      # канонічний тип: "вулиця","провулок","проїзд","проспект","бульвар","площа","тупик","узвіз","шосе","набережна","майдан","спуск"
      ordinal: int | None   # 1 для "1-й"
      name: str             # нормалізовано: нижній регістр, апостроф → "'", пробіли стиснуті
  @dataclass(frozen=True)
  class AddressQuery:
      street: StreetName
      house: str | None     # normalize_house(...)
  ```
- Створює (`address_parse.py`):
  - `KIND_SYNONYMS: dict[str, str]` — розширюваний словник, ключі без крапки й у нижньому регістрі (`"вул"→"вулиця"`, `"пров"→"провулок"`, `"пр-к"→"провулок"`, `"пр-д"→"проїзд"`, `"просп"→"проспект"`, `"пр-т"→"проспект"`, `"бул"→"бульвар"`, `"б-р"→"бульвар"`, `"пл"→"площа"`, `"туп"→"тупик"`, а також кожна канонічна назва сама на себе);
  - `ORDINAL_WORDS: dict[str, int]` — `перший/перша/першій`=1 … `десятий`=10, включно з жіночим родом;
  - `parse_query(text: str) -> AddressQuery`;
  - `parse_voe_street(value: str) -> StreetName` — `"провулок. 1-й Ботанічний"`;
  - `parse_plain_street(text: str) -> StreetName` — `"вулиця Стрілецька"`, `"* 1-й Маріі …"` (для задачі 6);
  - `normalize_house(text: str) -> str`;
  - `search_stem(street: StreetName) -> str` — що надсилати в `read_street?q=`;
  - `street_matches(query: StreetName, cand: StreetName) -> bool`.

- [ ] **Крок 1: Каркас.** `git init`. `.gitignore` як у структурі. `pyproject.toml`: пакет `voe_explorer` у `src/`, `requires-python>=3.12`, залежності `pywebview>=5`, extras `dev = ["pytest>=8", "pyinstaller>=6", "pillow>=10"]`, `[tool.pytest.ini_options] pythonpath=["src"] testpaths=["tests"]`. Потім `py -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"`. Скопіювати `docs/research/samples/*` у `tests/fixtures/`.

- [ ] **Крок 2: Падаючі тести.**
```python
BOTAN1 = StreetName("провулок", 1, "ботанічний")

@pytest.mark.parametrize("text", [
    "1-й пров. Ботанічний, 10", "1 провулок Ботанічний 10",
    "перший Ботанічний провулок, 10", "Ботанічний 1-й пров 10", "1й пров Ботанічний,10",
])
def test_parse_query_variants_equal(text):
    assert parse_query(text) == AddressQuery(BOTAN1, "10")

def test_parse_query_without_kind_or_house():
    assert parse_query("Ботанічний") == AddressQuery(StreetName(None, None, "ботанічний"), None)

def test_parse_query_kind_only_street():
    assert parse_query("вул. Соборна 1") == AddressQuery(StreetName("вулиця", None, "соборна"), "1")

def test_apostrophes_unified():
    assert parse_query("вул. Гоголя-П’ятницька 3").street.name == parse_query("вул. Гоголя-П'ятницька 3").street.name

@pytest.mark.parametrize("value,expected", [
    ("провулок. 1-й Ботанічний", StreetName("провулок", 1, "ботанічний")),
    ("проїзд. Ботанічний", StreetName("проїзд", None, "ботанічний")),
    ("вулиця. Ботанічна", StreetName("вулиця", None, "ботанічна")),
    ("вулиця. Юрія Смирнова/1 провулок Український", StreetName("вулиця", None, "юрія смирнова/1 провулок український")),
])
def test_parse_voe_street(value, expected):
    assert parse_voe_street(value) == expected

def test_parse_plain_street():
    assert parse_plain_street("вулиця Стрілецька") == StreetName("вулиця", None, "стрілецька")
    assert parse_plain_street("* 1-й Маріі Литвиненко-Вольгемут") == StreetName(None, 1, "маріі литвиненко-вольгемут")

@pytest.mark.parametrize("raw", ["12А", "12a", "12A", "12-А", "12 а", " 12а "])
def test_normalize_house_letter(raw):
    assert normalize_house(raw) == "12А"

def test_normalize_house_fraction():
    assert normalize_house("10 / 2") == "10/2"

def test_search_stem_is_name_prefix_without_kind_or_ordinal():
    assert search_stem(BOTAN1) == "Ботан"           # перші 5 літер найдовшого слова, перша велика
    assert search_stem(StreetName(None, None, "юрія смирнова")) == "Смирн"

def test_street_matches_kind_and_ordinal_exact():
    assert street_matches(BOTAN1, StreetName("провулок", 1, "ботанічний"))
    assert not street_matches(BOTAN1, StreetName("провулок", 2, "ботанічний"))
    assert not street_matches(BOTAN1, StreetName("вулиця", None, "ботанічна"))
    assert not street_matches(BOTAN1, StreetName("провулок", None, "ботанічний"))

def test_unspecified_kind_or_ordinal_matches_any():
    q = StreetName(None, None, "ботанічний")
    assert street_matches(q, StreetName("провулок", 2, "ботанічний"))
    assert street_matches(q, StreetName("проїзд", None, "ботанічний"))

def test_street_matches_tolerates_adjective_ending_and_partial_name():
    q = StreetName("вулиця", None, "ботанічний")
    assert street_matches(q, StreetName("вулиця", None, "ботанічна"))
    assert street_matches(StreetName(None, None, "коцюбинського"), StreetName("проспект", None, "михайла коцюбинського"))
```

- [ ] **Крок 3: Перевірити, що падають.** `.venv/Scripts/python -m pytest tests/test_address_parse.py -q` → FAIL (ImportError).

- [ ] **Крок 4: Реалізація.** Для `parse_query` потрібен алгоритм, який сигнатури не визначають:
  1. Відокремити хвіст після останньої коми як кандидат на будинок.
  2. Токенізувати.
  3. Токен із `KIND_SYNONYMS` (крапку прибрати) задає `kind`.
  4. Токен виду `\d+-?[йаяеі]` або слово з `ORDINAL_WORDS` задає `ordinal`.
  5. Голе число **перед** першим словом назви — теж `ordinal`. Останній токен, схожий на будинок (`\d+[\w/-]*`), **після** назви — `house`.
  6. Решта слів — це `name`.

  Для `street_matches`:
  - `kind` і `ordinal` запиту, якщо задані, мають дорівнювати кандидатовим. Якщо не задані, підходить будь-яке значення. Неоднозначність потім вирішує resolver (задача 4): він показує вибір.
  - Ім'я: кожне слово запиту `w` збігається з якимось словом кандидата `c`, якщо `c.startswith(w[:max(4, len(w)-2)])`.

  Для `normalize_house`: латиниця A/B/C/E/H/I/K/M/O/P/T/X → кирилиця, верхній регістр, прибрати пробіли та дефіс між цифрами й літерою.

- [ ] **Крок 5: Тести проходять.** `.venv/Scripts/python -m pytest tests/test_address_parse.py -q` → PASS.

- [ ] **Крок 6: Коміт.** `git add -A && git commit -m "feat: project scaffold and address parsing"`

---

### Задача 2: Розбір відповіді графіка

**Файли:**
- Створити: `src/voe_explorer/schedule_parse.py`, типи в `models.py`
- Тест: `tests/test_schedule_parse.py`
- Фікстури: `tests/fixtures/2026-10-17_emergency_1-botanichnyi-2.json`, `…_no-outage_soborna-1.html`, а також синтетична `tests/fixtures/synthetic_gpv_two_days.html`. Її зібрати з `…no-outage_soborna-1.html`: два рядки днів, `пт 31.12` (`current_day`) і `сб 01.01`, комірки з класами `cell-confirmed`, `cell-possible`, `cell-first-half`, `cell-second-half`, `no_disconnection`, `weird_new_state`. У коментарі файлу позначити «SYNTHETIC — формат ГПВ не перевірено».

**Інтерфейси:**
- Створює (`models.py`):
  ```python
  class HourState(str, Enum): ON="on"; OFF="off"; POSSIBLE="possible"; OFF_FIRST_HALF="off_first_half"; OFF_SECOND_HALF="off_second_half"; UNKNOWN="unknown"
  @dataclass(frozen=True)
  class DaySchedule: label: str; day: date | None; is_today: bool; hours: tuple[HourState, ...]   # рівно 24
  @dataclass(frozen=True)
  class Outage: reason: str | None; start: datetime | None; end: datetime | None
  @dataclass(frozen=True)
  class ParsedSchedule:
      power_off_now: bool
      outage: Outage | None
      message_lines: tuple[str, ...]
      warning: str | None
      days: tuple[DaySchedule, ...]
      unknown_classes: frozenset[str]
  class ParseError(Exception): ...
  ```
- Створює (`schedule_parse.py`):
  - `extract_insert_html(raw_json: str) -> str` — `data` команди `insert`; інакше `ParseError`;
  - `parse_schedule_html(html: str, fetched_at: datetime) -> ParsedSchedule`.

- [ ] **Крок 1: Падаючі тести.**
```python
def test_emergency_fixture():
    raw = (FIX / "2026-10-17_emergency_1-botanichnyi-2.json").read_text("utf-8")
    p = parse_schedule_html(extract_insert_html(raw), datetime(2026, 10, 17, 11, 0))
    assert p.power_off_now is True
    assert p.outage == Outage("Аварійне відключення", datetime(2026,10,17,9,16), datetime(2026,10,18,7,16))
    assert p.warning.startswith("Увага!")
    assert len(p.days) == 1 and p.days[0].label == "сб 17.10" and p.days[0].day == date(2026,10,17) and p.days[0].is_today
    assert p.days[0].hours == (HourState.ON,) * 24
    assert p.unknown_classes == frozenset()

def test_no_outage_fixture():
    p = parse_schedule_html((FIX / "2026-10-17_no-outage_soborna-1.html").read_text("utf-8"), datetime(2026,10,17,10,0))
    assert p.power_off_now is False and p.outage is None
    assert "не зафіксовано" in p.message_lines[0]

def test_synthetic_multi_day_year_boundary_and_states():
    p = parse_schedule_html((FIX / "synthetic_gpv_two_days.html").read_text("utf-8"), datetime(2026,12,31,22,0))
    assert [d.day for d in p.days] == [date(2026,12,31), date(2027,1,1)]
    assert {HourState.OFF, HourState.POSSIBLE, HourState.OFF_FIRST_HALF, HourState.OFF_SECOND_HALF, HourState.UNKNOWN} <= set(p.days[0].hours)
    assert p.unknown_classes == frozenset({"weird_new_state"})

def test_missing_current_day_class_uses_date_match():
    html = (FIX / "2026-10-17_no-outage_soborna-1.html").read_text("utf-8").replace(" current_day", "")
    assert parse_schedule_html(html, datetime(2026,10,17,10,0)).days[0].is_today

@pytest.mark.parametrize("body", ["error code: 502", "<html><body>Cloudflare</body></html>", "[]"])
def test_garbage_raises(body):
    with pytest.raises(ParseError):
        parse_schedule_html(extract_insert_html(body) if body.startswith("[") else body, datetime(2026,10,17))
```

- [ ] **Крок 2: Перевірити, що падають.** `.venv/Scripts/python -m pytest tests/test_schedule_parse.py -q` → FAIL.

- [ ] **Крок 3: Реалізація.** Парсити через `html.parser` зі stdlib, з регулярними виразами там, де простіше. Правила:
  - Повідомлення: «відсутня електроенергія» означає `power_off_now`. Причина — текст після `Причина відключення:`, пробіли стиснуті. Час — `(\d{2}):(\d{2}) (\d{4})\.(\d{2})\.(\d{2})` після «Час початку» та «завершення» (тире будь-яке, префікс «до» ігнорується).
  - Класи комірок: прибрати модифікатори `cell`, `current_day`, `grey`, `past`, `day_col`, `legend`, `head`. Решту токенів нормалізувати (зняти префікс `cell-`, `-`→`_`) і зіставити: `no_disconnection`/`non_scheduled` → ON, `confirmed` → OFF, `possible` → POSSIBLE, `first_half` → OFF_FIRST_HALF, `second_half` → OFF_SECOND_HALF. Інше → UNKNOWN плюс запис в `unknown_classes`.
  - Дата з `dd.mm`: рік береться з `fetched_at`. Якщо місяць менший за місяць `fetched_at` більше ніж на 6, рік +1.
  - `is_today`: клас `current_day` **або** `day == fetched_at.date()`.
  - Немає ні блоку повідомлення, ні контейнера таблиці → `ParseError`.

- [ ] **Крок 4: Тести проходять.** Та сама команда → PASS.

- [ ] **Крок 5: Коміт.** `git commit -am "feat: parse VOE schedule response"` (новий файл додати через `git add`).

---

### Задача 3: Статус картки

**Файли:**
- Створити: `src/voe_explorer/status.py`
- Тест: `tests/test_status.py`

**Інтерфейси:**
- Споживає: `ParsedSchedule`, `HourState` (задача 2); `PlannedWork` (задача 6; тут лише тип, у тестах задати вручну, тож визначити його в `models.py` уже зараз):
  ```python
  @dataclass(frozen=True)
  class PlannedWork: id: str; kind: str; status: str; start: datetime; end: datetime; settlement: str; streets: tuple[tuple[StreetName, tuple[str, ...]], ...]
  ```
- Створює:
  ```python
  class Level(str, Enum): ON="on"; OFF="off"; POSSIBLE="possible"; STALE="stale"; SITE_CHANGED="site_changed"
  @dataclass(frozen=True)
  class CardStatus: level: Level; headline: str; reason: str | None; until: datetime | None; source: str | None; data_at: datetime | None
  STALE_AFTER = timedelta(minutes=15)
  HEADLINES = {Level.ON:"Світло є", Level.OFF:"Немає світла", Level.POSSIBLE:"Можливе відключення",
               Level.STALE:"Не вдалося оновити", Level.SITE_CHANGED:"Сайт VOE змінився — потрібна нова версія програми"}
  def derive_status(parsed: ParsedSchedule | None, fetched_at: datetime | None, parse_failed: bool,
                    planned_now: PlannedWork | None, now: datetime) -> CardStatus
  ```

- [ ] **Крок 1: Падаючі тести** (`parsed` будувати вручну через dataclass-и).
  - `test_message_off_beats_green_table`: `power_off_now` і всі години ON → `Level.OFF`, `reason="Аварійне відключення"`, `until=outage.end`, `source="аварійне відключення"`.
  - `test_table_off_current_hour`: о 14:10 година 14 = OFF, години 15–16 = OFF, 17 = ON → OFF, `source="за графіком"`, `until=datetime(...,17,0)`.
  - `test_half_hours`: о 14:10 `OFF_FIRST_HALF` → OFF з `until` 14:30. О 14:40 `OFF_FIRST_HALF` → ON. О 14:40 `OFF_SECOND_HALF` → OFF.
  - `test_possible_and_unknown_are_yellow`: поточна година POSSIBLE → POSSIBLE. Поточна година UNKNOWN → POSSIBLE.
  - `test_worst_wins`: таблиця POSSIBLE + повідомлення OFF → OFF. Таблиця ON + `planned_now` → OFF з `source="планові роботи"` і `until=planned.end`.
  - `test_stale_never_green` (Review Focus 2): `fetched_at = now - 3h`, `parsed` зелений → `Level.STALE`, `data_at == fetched_at`. Те саме при `parsed=None`.
  - `test_site_changed`: `parse_failed=True` → `SITE_CHANGED`.
  - `test_all_clear`: свіже повідомлення «не зафіксовано» плюс таблиця ON → `Level.ON`, `headline == "Світло є"`.

- [ ] **Крок 2: Падають.** `.venv/Scripts/python -m pytest tests/test_status.py -q` → FAIL.

- [ ] **Крок 3: Реалізація.** Порядок перевірок: `SITE_CHANGED` → `STALE` (немає даних або вони старші за `STALE_AFTER`) → зібрати кандидатів (повідомлення, поточна година сьогоднішнього дня, `planned_now`) → взяти найгірший (OFF > POSSIBLE > ON). `until` для OFF за таблицею — кінець безперервної OFF-серії від `now`.

- [ ] **Крок 4: Тести проходять.**

- [ ] **Крок 5: Коміт.** `git commit -m "feat: derive card status with worst-wins rule"`

---

### Задача 4: Мережа, клієнт VOE і resolver адрес

**Файли:**
- Створити: `src/voe_explorer/config.py`, `src/voe_explorer/net.py`, `src/voe_explorer/voe_client.py`, `src/voe_explorer/resolver.py`
- Тест: `tests/test_net_client.py`, `tests/test_resolver.py`

**Інтерфейси:**
- `config.py`: `BASE_URL`, `TIMEOUT_S=40`, `RETRIES=3`, `RETRY_PAUSE_S=2`, `REFRESH_S=300`, `PROBE_S=120`, `PLANNED_S=10800`, `SLOW_S=10.0`, `UA` (рядок Chrome з `probe.py`), `RELEASES_REPO=""`, `APP_DIR = Path(os.environ["APPDATA"]) / "VOE Explorer"`.
- `net.py`:
  ```python
  @dataclass(frozen=True)
  class FetchResult: url: str; at: datetime; status: int | None; elapsed_s: float; body: str | None; error: str | None
      # ok-властивість: status == 200 and body is not None
  class Net:
      def __init__(self, opener=None, on_attempt: Callable[[FetchResult], None] | None = None, sleep=time.sleep): ...
      def get(self, path: str) -> FetchResult          # остання спроба
      def post(self, path: str, form: dict[str, str]) -> FetchResult
  ```
  `opener` — це об'єкт з `.open(request, timeout)` (за замовчуванням `build_opener(HTTPCookieProcessor)`). Кожна спроба передається в `on_attempt` — так її бачить моніторинг.
- `voe_client.py`:
  ```python
  @dataclass(frozen=True)
  class AcItem: value: str; id: str
  @dataclass(frozen=True)
  class ScheduleFetch: result: FetchResult; raw_json: str | None
  class VoeClient:
      def __init__(self, net: Net): ...
      def cities(self, q: str) -> list[AcItem]
      def streets(self, city_id: str, q: str) -> list[AcItem]
      def houses(self, street_id: str, q: str) -> list[AcItem]
      def schedule(self, addr: "SavedAddress") -> ScheduleFetch    # GET форми + POST (§5.2)
      def planned_page(self, region: str, year: int, month: int) -> FetchResult   # GET форми + POST (§5.4)
  class VoeUnavailable(Exception): ...   # автокомпліт не отримав 200 із JSON-масивом
  ```
- `models.py` додати:
  ```python
  @dataclass
  class SavedAddress: id: str; label: str; city_value: str; city_id: str; street_value: str; street_id: str; house_value: str; house_id: str
  ```
- `resolver.py`:
  ```python
  @dataclass(frozen=True)
  class StreetChoice: item: AcItem; parsed: StreetName
  @dataclass(frozen=True)
  class Resolution:
      kind: Literal["found", "choose_street", "choose_house", "not_found"]
      street: StreetChoice | None
      house: AcItem | None
      street_choices: tuple[StreetChoice, ...]
      house_choices: tuple[AcItem, ...]
  class Resolver:
      def __init__(self, client: VoeClient, memory: "MemoryStore"): ...   # MemoryStore з задачі 5; у тестах — dict-фейк з get/put
      def resolve(self, text: str, city: AcItem) -> Resolution
      def resolve_house(self, city: AcItem, street: StreetChoice, house_text: str) -> Resolution
  ```

- [ ] **Крок 1: Падаючі тести** у `test_net_client.py` (фейковий opener повертає наперед задані відповіді й записує URL):
  - `test_cyrillic_query_is_utf8_encoded`: `client.streets("510100000","Ботан")` → URL закінчується на `q=%D0%91%D0%BE%D1%82%D0%B0%D0%BD`.
  - `test_retries_on_502_then_ok`: 502, 502, 200 → `result.status == 200`, `on_attempt` викликано 3 рази, sleep викликано 2 рази з `2`.
  - `test_gives_up_after_3`: тричі 502 → `status == 502`, `client.streets` піднімає `VoeUnavailable`.
  - `test_ac_items_parsed`: тіло з §5.1 → `[AcItem("вулиця. Соборна","1652")]`.
  - `test_ac_html_body_is_unavailable` (Review Focus 3): 200 з `"<html>…"` → `VoeUnavailable`.
  - `test_schedule_posts_expected_form`: перший GET повертає HTML з `form_build_id` `form-XYZ`. POST-тіло містить `form_build_id=form-XYZ`, `street_id=837`, `_triggering_element_value=%D0%9F%D0%BE%D0%BA%D0%B0%D0%B7%D0%B0%D1%82%D0%B8`, а URL — `?ajax_form=1&_wrapper_format=drupal_ajax`.

- [ ] **Крок 2: Падаючі тести** у `test_resolver.py` (фейковий клієнт: на `"Ботан"` повертає 6 вулиць з §5.1: вулиця Ботанічна 1136, проїзд Ботанічний 1137, провулок 1-й/2-й/3-й Ботанічний 837/944/1032, провулок Ботанічний 33570. Будинки вулиці 837 — `2, 20, 22`; 1136 — `12А, 10/2`; 1137 — `5`):
  - `test_exact_ordinal_and_kind_found`: `"1-й пров. Ботанічний, 2"` → `kind="found"`, `street.item.id=="837"`, `house.id` — це id будинку `2`, а не `20`.
  - `test_no_kind_many_kinds_asks` (Review Focus 1): `"Ботанічний 10"` → `choose_street` з усіма 6 варіантами. Те саме для `"Ботанічна 10"`. Жодного автоматичного рішення.
  - `test_no_ordinal_with_ordinal_candidates_asks` (§6): `"пров. Ботанічний 2"` → `choose_street` з чотирма провулками (1-й, 2-й, 3-й і без номера). Вулиці й проїзду серед них немає.
  - `test_single_candidate_auto`: `"проїзд Ботанічний 5"` → `found`, `street.item.id=="1137"`.
  - `test_house_variant_match` (Review Focus 5): `"вул. Ботанічна 12a"` → `found`, `house.value=="12А"`. `"вул. Ботанічна 10 / 2"` → `found`.
  - `test_unknown_house_offers_list`: `"1-й пров. Ботанічний 3"` → `choose_house` з варіантами з VOE.
  - `test_memory_short_circuits`: після `found` другий `resolve` з тим самим текстом не викликає клієнт.
  - `test_not_found`: `"вул. Неіснуюча 1"` → `not_found`.

- [ ] **Крок 3: Падають.** `.venv/Scripts/python -m pytest tests/test_net_client.py tests/test_resolver.py -q` → FAIL.

- [ ] **Крок 4: Реалізація.**
  - `Net` — `urllib.request.Request` із `User-Agent` і `X-Requested-With: XMLHttpRequest`. 5xx, `URLError` і таймаут — привід повторити. 4xx — без повтору.
  - `Resolver.resolve`: спершу пам'ять (ключ `(city.id, нормалізований текст)`). Далі `parse_query`, потім `client.streets(city.id, search_stem(...))`, кожен кандидат через `parse_voe_street`, фільтр через `street_matches`. Рівно один збіг → `resolve_house`. Кілька → `choose_street`. Нуль → `not_found`.
  - `resolve_house`: `client.houses(street.id, цифрова частина будинку)`, порівняння через `normalize_house`. Точний збіг → `found` і запис у пам'ять. Інакше `choose_house`.

- [ ] **Крок 5: Тести проходять.**

- [ ] **Крок 6: Коміт.** `git commit -m "feat: VOE http client and address resolver"`

---

### Задача 5: Сховище

**Файли:**
- Створити: `src/voe_explorer/storage.py`
- Тест: `tests/test_storage.py`

**Інтерфейси:**
```python
class AddressStore:            # addresses.json
    def __init__(self, path: Path): ...
    def all(self) -> list[SavedAddress]            # у збереженому порядку
    def add(self, addr: SavedAddress) -> None
    def rename(self, id: str, label: str) -> None
    def move(self, id: str, delta: int) -> None    # -1 вгору, +1 вниз, з обмеженням на краях
    def remove(self, id: str) -> None
class MemoryStore:             # memory.json
    def get(self, key: str) -> dict | None
    def put(self, key: str, value: dict) -> None
@dataclass(frozen=True)
class StoredResponse: id: int; address_id: str | None; kind: str; at: datetime; status: int | None; elapsed_s: float; url: str; body: str | None; content_hash: str | None
class Db:                      # voe.sqlite3; таблиці probes і responses
    def __init__(self, path: Path): ...
    def add_probe(self, at: datetime, kind: str, status: int | None, elapsed_s: float, state: str) -> None
    def probes_between(self, start: datetime, end: datetime) -> list[tuple[datetime, str, float]]   # (at, state, elapsed)
    def add_response(self, address_id: str | None, kind: str, result: FetchResult, content_hash: str | None) -> int
    def responses(self, address_id: str | None, kind: str) -> list[StoredResponse]   # нові спершу
def save_sample(dir: Path, address_id: str | None, raw: str, note: str) -> Path   # samples\{YYYYmmdd-HHMMSS}_{address_id}.json
```
Політика зберігання `responses`: для кожної пари `(address_id, kind)` лишаються найновіший запис і 10 найновіших записів з `content_hash`, відмінним від попереднього (§7, «останні N відповідей, у яких графік змінився»). `content_hash` — sha256 від JSON-дампу `ParsedSchedule.days` + `outage`. Його обчислює сервіс, а не сховище.

- [ ] **Крок 1: Падаючі тести** (на `tmp_path`):
  - `test_address_crud_and_order`: додати A, B, C → `move(C,-1)` → порядок A, C, B. Після `rename` і `remove` усе переживає перевідкриття файлу.
  - `test_memory_roundtrip_unicode`: ключ і значення з кирилицею однакові після перевідкриття. Файл — валідний UTF-8.
  - `test_response_retention`: 15 відповідей з хешами `h0,h0,h1,h1,h2,…,h7` (по дві на хеш), потім ще 5 з `h7` → лишається найновіша плюс записи зміни хешу, не більше 11 для пари. Найновіша — перша.
  - `test_probes_between_filters_by_time`.
  - `test_save_sample_writes_utf8`.

- [ ] **Крок 2: Падають** → FAIL. **Крок 3: Реалізація** (запис JSON атомарно: `tmp` + `os.replace`. SQLite з `check_same_thread=False` і `threading.Lock`). **Крок 4: Проходять.**

- [ ] **Крок 5: Коміт.** `git commit -m "feat: local storage for addresses, memory, responses, probes"`

---

### Задача 6: Планові роботи

**Файли:**
- Створити: `src/voe_explorer/planned.py`
- Тест: `tests/test_planned.py`
- Фікстура: `tests/fixtures/2026-10-17_planned-page_vinnytsia-2026-10.html`

**Інтерфейси:**
- Споживає: `PlannedWork` (задача 3), `parse_plain_street`, `street_matches`, `normalize_house` (задача 1).
- Створює:
  ```python
  def parse_planned_html(html: str) -> list[PlannedWork]
  def parse_region_options(html: str) -> dict[str, str]           # {"23": "Вінницькі МЕМ", "41": "Жмеринський р-н", ...}
  def city_name(city_value: str) -> str                            # "м.. Вінниця (Вінницька Область/М.Вінниця)" → "Вінниця"
  def region_for_city(city_value: str, regions: dict[str, str]) -> str | None
  def works_for_address(addr: SavedAddress, works: list[PlannedWork], now: datetime, horizon: timedelta = timedelta(days=7)) -> list[PlannedWork]
  def months_to_fetch(now: datetime) -> list[tuple[int, int]]      # поточний місяць + наступний, якщо до кінця місяця ≤7 днів
  ```

- [ ] **Крок 1: Падаючі тести.**
  - `test_parse_fixture`: 20 робіт. Робота `2826054`: `start=2026-10-20 09:00`, `end=2026-10-20 16:30`, `settlement="ВІННИЦЯ"`, у `streets` є `(StreetName("вулиця",None,"стрілецька"), ("16","18","20","26","28","30"))`. Порожні сегменти `; ;` пропущено.
  - `test_matches_strilecka_16`: адреса (`вулиця. Стрілецька`, `16`, Вінниця), `now=2026-10-17 12:00` → у результаті є `2826054`. Адреса `16А` → цієї роботи немає (точний номер). Адреса `провулок. Стрілецький 16` → нічого (тип не той).
  - `test_past_and_far_future_excluded`: `now=2026-10-21` → роботи 20.10 немає. `now=2026-10-01` → нічого (горизонт 7 днів).
  - `test_region_mapping`, використовуючи значення з розвідки:
    - `region_for_city("м.. Вінниця (Вінницька Область/М.Вінниця)") == "23"`;
    - `"смт.. Літин (Літинський Район/Смт Літин)"` → `"27"`;
    - `"м.. Гнівань (Тиврівський Район/Смт Тиврів)"` → `"26"`;
    - `"м.. Жмеринка (Вінницька Область/М.Вінниця)"` → `"41"`;
    - `"смт.. Стрижавка (Вінницький Район/М.Вінниця)"` → `None`.
  - `test_months_to_fetch`: 2026-10-17 → `[(2026,10)]`. 2026-12-28 → `[(2026,12),(2027,1)]`.

- [ ] **Крок 2: Падають.** **Крок 3: Реалізація.**
  - Регіон: `"<X> Район"` у дужках → опція, яка починається з перших 5 літер X і закінчується на «р-н».
  - `"Вінницька Область"` → якщо `city_name` дорівнює «Вінниця», то `"23"`. Інакше — опція «р-н», яка починається з перших 5 літер назви міста.
  - Населений пункт порівнюється з `city_name(addr.city_value)` без урахування регістру.

  **Крок 4: Проходять.**

- [ ] **Крок 5: Коміт.** `git commit -m "feat: planned works parsing and matching"`

---

### Задача 7: Моніторинг сайту

**Файли:**
- Створити: `src/voe_explorer/health.py`
- Тест: `tests/test_health.py`

**Інтерфейси:**
```python
class Health(str, Enum): OK="ok"; SLOW="slow"; DOWN="down"; OFFLINE="offline"
def classify(result: FetchResult, expect_json_list: bool) -> Health      # без OFFLINE
def probe(net: Net, internet_check: Callable[[], bool]) -> tuple[Health, FetchResult]
    # GET /disconnection/detailed/autocomplete/read_city?q=%D0%92%D1%96%D0%BD; при DOWN викликає internet_check → OFFLINE, якщо інтернету нема
def internet_ok() -> bool      # GET https://www.google.com/generate_204 з таймаутом 5 с, True при 204
@dataclass(frozen=True)
class Segment: start: datetime; end: datetime; state: str     # "ok"|"slow"|"down"|"offline"|"nodata"
@dataclass(frozen=True)
class HealthStats: down_count: int; down_total: timedelta; avg_s: float | None; max_s: float | None
def segments(probes: list[tuple[datetime, str, float]], start: datetime, end: datetime, max_gap: timedelta = timedelta(seconds=300)) -> list[Segment]
def stats(probes: list[tuple[datetime, str, float]], segs: list[Segment]) -> HealthStats
def indicator_text(state: Health, elapsed_s: float | None) -> str   # тексти з «Глобальних обмежень»
```

- [ ] **Крок 1: Падаючі тести.**
  - `test_classify`: 200 + `[{"value":…}]` за 0.3 с → OK; те саме за 12 с → SLOW; 502 → DOWN; `status=None` (таймаут) → DOWN; 200 з `[]` при `expect_json_list` → DOWN (Review Focus 3); 200 з HTML → DOWN.
  - `test_probe_offline`: DOWN і `internet_check` → False → OFFLINE.
  - `test_gap_becomes_nodata` (Review Focus 2): проби о 10:00, 10:02, 10:04 (ok), потім 13:00 (ok) → сегменти `ok 10:00–10:04`, `nodata 10:04–13:00`, `ok 13:00–…`. Жодного `down`.
  - `test_down_run_merged_and_counted`: ok, down, down, down, ok з кроком 2 хв → один down-сегмент на 6 хв. `down_count=1`, `down_total=6 хв`.
  - `test_offline_not_counted_as_down`.
  - `test_indicator_text`: `indicator_text(Health.OK, 5.8) == "VOE відповідає · 5.8 с"`, `indicator_text(Health.DOWN, None) == "VOE не відповідає"`, `indicator_text(Health.OFFLINE, None) == "Немає інтернету"`.

- [ ] **Крок 2: Падають.** **Крок 3: Реалізація.** Сегмент триває від проби до наступної. Розрив понад `max_gap` → `nodata`. Сусідні сегменти з однаковим станом зливаються. **Крок 4: Проходять.**

- [ ] **Крок 5: Коміт.** `git commit -m "feat: VOE health classification and history segments"`

---

### Задача 8: Фоновий сервіс і знімок стану

**Файли:**
- Створити: `src/voe_explorer/service.py`
- Тест: `tests/test_service.py`

**Інтерфейси:**
- Споживає все з задач 1–7.
- Створює:
  ```python
  class Service:
      def __init__(self, client: VoeClient, net: Net, addresses: AddressStore, db: Db, samples_dir: Path,
                   clock: Callable[[], datetime] = datetime.now, internet_check=internet_ok): ...
      def refresh_address(self, addr_id: str) -> None        # графік → розбір → статус; зберегти відповідь і зразок, якщо є unknown_classes або ParseError
      def refresh_all(self) -> None
      def refresh_planned(self) -> None                      # для кожного унікального РЕМ серед адрес: months_to_fetch → planned_page → parse
      def run_probe(self) -> None                            # health.probe → db.add_probe(kind="probe")
      def snapshot(self) -> dict                             # див. нижче; лише JSON-сумісні типи
      def start(self) -> None                                # потоки-демони з інтервалами з config; перший прохід одразу
      def stop(self) -> None
  ```
  Форма `snapshot()` (на неї спирається UI):
  ```
  {"health": {"state": "ok|slow|down|offline|unknown", "text": str, "at": "HH:MM"|None},
   "cards": [{"id","label","address": "1-й пров. Ботанічний, 2",
              "level","headline","reason","until": "HH:MM"|"HH:MM завтра"|None,"source","data_at": "HH:MM"|None,
              "today": {"label": str, "hours": [24 рядки HourState.value]} | None,
              "other_days": [{"label","hours"}],
              "planned": [{"text": "пн 20.10, 09:00–16:30"}],
              "loading": bool}],
   "update": {"version","url"} | None,
   "install_offer": bool}
  ```
  Кожна спроба `Net` (через `on_attempt`) також пишеться в `db.add_probe(kind="request", state=classify(...))`, бо §8 вимагає, щоб звичайні оновлення теж ішли в історію. Сирі відповіді зберігаються через `db.add_response` для всіх трьох видів (§7): `kind="schedule"` (з `address_id`), `kind="planned"` і `kind="probe"` (з `address_id=None`). Саме їх показує `Api.get_raw(id, kind)`.

- [ ] **Крок 1: Падаючі тести** (фейкові клієнт і годинник, `tmp_path`):
  - `test_refresh_emergency_snapshot`: фейковий `schedule` повертає фікстуру аварії → у `snapshot()["cards"][0]` поля `level=="off"`, `headline=="Немає світла"`, `reason=="Аварійне відключення"`, `until=="07:16 завтра"` (годинник 2026-10-17 11:00), `len(today.hours)==24`.
  - `test_failed_refresh_keeps_last_data_then_stale`: успішне оновлення, потім годинник +20 хв і помилка (`VoeUnavailable`/502) → `level=="stale"`, `data_at` — час успішного оновлення, `today` збережено.
  - `test_parse_error_marks_site_changed_and_saves_sample`: тіло `"[]"` → `level=="site_changed"`, у `samples_dir` з'явився 1 файл.
  - `test_unknown_classes_save_sample`: синтетична фікстура → файл зразка з'являється, а статус показується.
  - `test_response_history_stored`: два оновлення з різними хешами → `db.responses(addr_id,"schedule")` має 2 записи.
  - `test_planned_line_on_card`: фейковий `planned_page` повертає фікстуру, адреса «вулиця. Стрілецька 16», годинник 2026-10-17 → `planned == [{"text": "пн 20.10, 09:00–16:30"}]`.

- [ ] **Крок 2: Падають.** **Крок 3: Реалізація.** Стан у пам'яті тримається під `threading.Lock`. Мережеві виклики виконуються поза блокуванням. **Крок 4: Проходять.**

- [ ] **Крок 5: Коміт.** `git commit -m "feat: background service and UI snapshot"`

---

### Задача 9: Оновлення та «Встановити на цей комп'ютер»

**Файли:**
- Створити: `src/voe_explorer/updates.py`, `src/voe_explorer/install.py`
- Тест: `tests/test_updates_install.py`

**Інтерфейси:**
```python
# updates.py
@dataclass(frozen=True)
class UpdateInfo: version: str; url: str
def parse_version(tag: str) -> tuple[int, ...]                      # "v0.2.0" → (0,2,0)
def check_latest(repo: str, current: str, fetch: Callable[[str], str | None]) -> UpdateInfo | None
    # repo=="" → None без запиту; GET https://api.github.com/repos/{repo}/releases/latest; url = html_url; будь-яка помилка → None
# install.py
def is_transient_location(exe: Path, env: Mapping[str, str]) -> bool   # під %TEMP%, %TMP% або %USERPROFILE%\Downloads
def install_target(env: Mapping[str, str]) -> Path                     # %LOCALAPPDATA%\VOE Explorer\VOE Explorer.exe
def install_self(exe: Path, env: Mapping[str, str], run: Callable[[list[str]], None]) -> Path
    # копіює exe; ярлик на робочому столі через powershell WScript.Shell; повертає шлях копії
```

- [ ] **Крок 1: Падаючі тести.**
  - `test_newer_version_detected`: фейковий fetch повертає `{"tag_name":"v0.2.0","html_url":"https://x"}` при current `"0.1.0"` → `UpdateInfo("0.2.0","https://x")`. Та сама версія → None. Порожній `repo` → None, fetch не викликано. fetch → None (немає мережі) → None.
  - `test_transient_locations`: `C:\Users\u\AppData\Local\Temp\_MEI123\x.exe` → True (саме так виглядає запуск з zip через Провідник). `C:\Users\u\Downloads\VOE Explorer.exe` → True. `C:\Users\u\AppData\Local\VOE Explorer\VOE Explorer.exe` → False.
  - `test_install_self_copies_and_creates_shortcut`: у `tmp_path` файл копіюється. `run` викликано один раз з командою powershell, яка містить `CreateShortcut` і шлях до `Desktop\VOE Explorer.lnk`.

  **Увага при реалізації `is_transient_location`:** у onefile-збірці `sys.executable` — це шлях до самого exe, а не до `_MEI`. Перевіряти треба саме `Path(sys.executable)`.

- [ ] **Крок 2: Падають.** **Крок 3: Реалізація.** **Крок 4: Проходять.**

- [ ] **Крок 5: Коміт.** `git commit -m "feat: update check and self-install"`

---

### Задача 10: Міст pywebview та інтерфейс

**Файли:**
- Створити: `src/voe_explorer/api.py`, `src/voe_explorer/__main__.py`, `src/voe_explorer/ui/index.html`, `ui/app.css`, `ui/app.js`
- Тест: `tests/test_api.py` (тільки Python-міст; UI перевіряється вручну, крок 5)

**Інтерфейси.** `Api` — публічні методи, усі повертають JSON-сумісні значення й ніколи не піднімають виняток у JS (помилка → `{"error": "текст для людини"}`):
```python
class Api:
    def __init__(self, service: Service, resolver: Resolver, client: VoeClient, addresses: AddressStore, db: Db, window_ref: Callable[[], Any]): ...
    def get_state(self) -> dict                                 # service.snapshot()
    def search_cities(self, q: str) -> list[dict]               # [{"value","id","name"}]
    def resolve(self, text: str, city: dict) -> dict            # Resolution → {"kind","street","house","street_choices":[{"value","id"}],"house_choices":[...]}
    def choose_street(self, city: dict, street: dict, house_text: str) -> dict
    def add_address(self, label: str, city: dict, street: dict, house: dict) -> dict   # {"id"}; одразу запускає refresh_address у потоці
    def rename(self, id: str, label: str) -> None
    def move(self, id: str, delta: int) -> None
    def remove(self, id: str) -> None
    def refresh_now(self) -> None
    def get_raw(self, id: str | None, kind: str) -> dict
        # {"items":[{"id","at","status","elapsed_s","url","understood": {...розбір...},"html": str|None,"json": str|None}]}
    def save_raw(self, response_id: int) -> str | None          # діалог збереження pywebview; повертає шлях
    def health_history(self, window: str) -> dict               # "day"|"week" → {"segments":[{"start","end","state"}],"stats":{...}}
    def install_self(self) -> dict
    def open_url(self, url: str) -> None                        # webbrowser.open; лише https://github.com/…
```
`__main__.py`:
- зібрати залежності;
- `webview.create_window("VOE Explorer", url=<ui/index.html через importlib.resources або sys._MEIPASS>, js_api=api, width=480, height=760, min_size=(380,520))`;
- `service.start()`;
- перевірку оновлень запустити в потоці (раз на запуск, з кешем на добу в `memory.json` під ключем `"__update_checked"`);
- `webview.start()`, а при закритті `service.stop()`.

- [ ] **Крок 1: Падаючі тести `test_api.py`.**
  - `test_methods_never_raise`: фейковий `Resolver.resolve` піднімає `VoeUnavailable` → `api.resolve(...)` повертає `{"error": "Сайт VOE зараз не відповідає. Спробуйте ще раз за хвилину."}`.
  - `test_get_raw_includes_understood_and_raw`: збережена відповідь фікстури аварії → `items[0]["html"]` містить `Причина відключення`, а `items[0]["understood"]["reason"] == "Аварійне відключення"`.
  - `test_open_url_rejects_non_github`.

- [ ] **Крок 2: Падають → реалізація `api.py` → проходять.** `.venv/Scripts/python -m pytest -q` (увесь набір) → PASS.

- [ ] **Крок 3: UI.** Vanilla JS, без збирачів. `app.js` раз на 2 с викликає `pywebview.api.get_state()` і перемальовує DOM. Елементи (тексти дослівно з «Глобальних обмежень»):
  - **Шапка:** «Світло» і кнопка-індикатор з крапкою (зелена/жовта/червона/сіра). Клік відкриває панель історії з перемикачем «День / Тиждень», смугою сегментів (кольори: ok зелений, slow жовтий, down червоний, offline і nodata сірий зі штриховкою та підписом «немає даних»), а також числами: «Падінь: N · загалом X хв · середній час Y с · найгірший Z с».
  - **Картка:**
    - назва (дрібно, сіра), адреса (жирна), рядок статусу: `● {headline}` · `{reason}` · `до {until}` кольором рівня (ON `#15803d`, OFF `#c2410c`, POSSIBLE `#ca8a04`, STALE і SITE_CHANGED сірий);
    - для STALE рядок «Не вдалося оновити · останні дані о {data_at}», а смужка приглушена (`opacity:.45`);
    - смужка з 24 клітинок (ON `#e5e5e0`, OFF `#ea580c`, POSSIBLE `#fcd34d`, половинки — градієнт 50/50, UNKNOWN — сірий зі штриховкою);
    - підпис годин `00 06 12 18 24`, «графік станом на {data_at}», рядки `🔧 Планові роботи · …`;
    - «Інші дні» (розгортається), якщо `other_days` не порожній.
  - **Легенда:** «?» біля смужки або клік по будь-якій клітинці відкриває поповер з п'ятьма рядками простими словами. Жовтий: «Жовтий — відключення можливе, але не підтверджене: світло може бути, а може й ні».
  - **Меню «⋯»:** «Перейменувати», «Вгору», «Вниз», «Видалити» (з підтвердженням усередині сторінки, не `confirm()`), «Відповідь VOE». Остання відкриває повноекранну панель зі списком відповідей (час, код, тривалість), блоком «Як програма це зрозуміла», вкладками «HTML / JSON» (моноширинний шрифт, прокрутка) і кнопками «Скопіювати» та «Зберегти у файл».
  - **«+ Додати адресу»:** діалог з полями «Місто» (за замовчуванням Вінниця, `id 510100000`, змінюється через `search_cities`), «Адреса» (довільний текст) і «Назва» («Дім», «Батьки»…). Після «Знайти»:
    - `found` → картка-підтвердження «провулок 1-й Ботанічний, 2» і кнопка «Додати»;
    - `choose_street` → список кнопок-варіантів з повною назвою VOE, де тип написаний словом;
    - `choose_house` → кнопки номерів;
    - `not_found` → «Не знайшли таку вулицю. Спробуйте написати лише назву, наприклад „Ботанічний“».
  - **Банери:** «Є нова версія» (посилання через `open_url`); при `install_offer` — «Встановити на цей комп'ютер».
  - Порожній стан без адрес: великий заклик «+ Додати адресу».

- [ ] **Крок 4: Ручна перевірка (живий VOE).** `.venv/Scripts/python -m voe_explorer`. Очікування:
  1. вікно відкривається одразу, без білого екрана, а картки показують «оновлюється…» без зависання;
  2. додати «1-й пров. Ботанічний, 2» → знайдено без вибору;
  3. додати «Ботанічний 10» → з'являється вибір, вулиці Ботанічної серед варіантів немає;
  4. статус і смужка видимі, «⋯ → Відповідь VOE» показує HTML;
  5. індикатор VOE показує час, а історія відкривається;
  6. закрити, відкрити → адреси на місці.

  Зробити знімок екрана і показати автору.

- [ ] **Крок 5: Коміт.** `git commit -m "feat: pywebview UI with cards, health history and raw response viewer"`

---

### Задача 11: Збірка exe і zip

**Файли:**
- Створити: `packaging/build.ps1`, `packaging/make_howto.py`

**Інтерфейси:**
- `make_howto.py <out.png>` малює PNG 900×520: світлий фон, три рядки великим шрифтом (Segoe UI з `C:\Windows\Fonts\segoeui.ttf`):
  1. «Якщо Windows показала синє вікно „Windows захистила ваш ПК“:»
  2. «натисніть „Докладніше“»
  3. «потім „Усе одно запустити“».
- `build.ps1`:
  - `pyinstaller --onefile --windowed --name "VOE Explorer" --add-data "src/voe_explorer/ui;voe_explorer/ui" src/voe_explorer/__main__.py`;
  - `make_howto.py`;
  - `Compress-Archive` → `dist/VOE-Explorer-<version>.zip`, де рівно `VOE Explorer.exe` і `Як запустити.png`.

- [ ] **Крок 1: Збірка.** `powershell -ExecutionPolicy Bypass -File packaging/build.ps1` → у `dist/` є exe і zip.

- [ ] **Крок 2: Перевірка вмісту zip.** `py -c "import zipfile,sys;print(zipfile.ZipFile(sys.argv[1]).namelist())" dist/VOE-Explorer-0.1.0.zip` → рівно два імені.

- [ ] **Крок 3: Ручна перевірка exe.**
  - Запустити `dist/VOE Explorer.exe`: вікно відкривається, UI вантажиться (немає 404 на `app.js`).
  - Відкрити zip у Провіднику й запустити exe прямо з архіву: програма працює й показує банер «Встановити на цей комп'ютер». Натиснути → на робочому столі з'являється ярлик, а копія лежить у `%LOCALAPPDATA%\VOE Explorer\`.

- [ ] **Крок 4: Коміт.** `git commit -m "build: one-file exe and zip with how-to image"`

---

### Задача 12: Репозиторії та перший реліз (зовнішні дії — лише з підтвердженням автора)

- [ ] **Крок 1:** Спитати автора його GitHub-ім'я та чи створювати репозиторії зараз. **Без явного «так» нічого не публікувати.**
- [ ] **Крок 2:** Після «так»:
  - створити `gh repo create voe-explorer --private --source . --push`;
  - створити `gh repo create voe-explorer-releases --public` без README з описом;
  - у `config.py` вписати `RELEASES_REPO = "<user>/voe-explorer-releases"`, перезібрати (задача 11), коміт.
- [ ] **Крок 3:** Після окремого «так» на публікацію: `gh release create v0.1.0 dist/VOE-Explorer-0.1.0.zip --repo <user>/voe-explorer-releases --title "VOE Explorer 0.1.0" --notes "Перша версія"`.
- [ ] **Крок 4:** Перевірити, що `check_latest` з порожнім кешем бачить `0.1.0` як поточну (банера немає). Потім тимчасово виставити `__version__="0.0.9"` локально й переконатися, що банер з'являється. Зміну не комітити.

# Моды для агентов

Мод — маленькое дополнение к самой программе Claude Code, в которой живёт агент.
Нужна версия Claude Code **2.1.287 или новее** (`claude --version`, обновить: `claude update`).

| Мод | Кому | Что делает |
|---|---|---|
| `limit-warn` | всем агентам | Когда израсходовано 90% лимита Claude (5-часового или недельного), агент сам пишет владельцу, когда лимит обновится. Один раз на окно, без повторов. |
| `reply-guard` | всем агентам | Не пропускает сообщение с запрещёнными фразами из `core/forbidden-phrases.txt` — агент получает причину и переписывает. |
| `unstick` | всем агентам | Сообщение из Телеграма, застрявшее в строке ввода, пока агент был занят, отправляется само. |
| `style-guard` | маркетологу | Перед отправкой владельцу черновик (пост, сторис, сценарий) проверяет вторая модель: нет ли «иишности» и похоже ли на ваш слог из `materials/examples.md`. Не прошёл — агент переписывает. Тратит немного лимита подписки на каждую проверку. |

## Как поставить

1. Скачать моды на компьютер или сервер агента (если папка уже есть — `git pull` внутри неё):

```
git clone https://github.com/rubisvika123-png/rubis-agent-skills.git ~/rubis-agent-skills
```

2. В `start.sh` агента ПЕРЕД последней строкой `exec env IS_SANDBOX=1 claude ...` добавить строку.
Техспецу и другим агентам:

```
export CLAUDE_CODE_PLUGIN_DIRS="$HOME/rubis-agent-skills/mods/limit-warn:$HOME/rubis-agent-skills/mods/reply-guard:$HOME/rubis-agent-skills/mods/unstick"
```

Маркетологу — то же самое плюс редактор стиля:

```
export CLAUDE_CODE_PLUGIN_DIRS="$HOME/rubis-agent-skills/mods/limit-warn:$HOME/rubis-agent-skills/mods/reply-guard:$HOME/rubis-agent-skills/mods/unstick:$HOME/rubis-agent-skills/mods/style-guard"
```

3. Создать в папке агента файл `core/forbidden-phrases.txt` — по одному правилу в строке,
`фраза | почему нельзя и как сказать иначе`. Пример:

```
# мои запреты
ctrl+c | выход из агента только командой /exit
без кода | говорим «без технических знаний»
```

Нет файла — `reply-guard` ничего не проверяет.

4. Перезапустить агента. Проверка: набрать в его окне `/plugin` — вверху будет строка
вида `3 mods active · limit-warn, reply-guard, unstick`.

Настройки (необязательно, в `secrets/channel.env`): `REPLY_GUARD_RULES` — другой путь к файлу
запретов, `STYLE_GUARD_FILE` — другой путь к файлу стиля маркетолога.

Проверить, что `limit-warn` видит лимит: набрать в окне агента `/limit-status`.
Проверить редактор стиля на любом тексте: `/style-check <текст>`.

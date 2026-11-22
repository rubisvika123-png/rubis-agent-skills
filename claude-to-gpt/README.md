# claude-to-gpt — перенос агента с Claude на GPT (Hermes)

Если Claude недоступен, программа пересаживает агента из курса на движок Hermes с мозгом GPT:
характер, вся память, навыки и тот же Telegram-бот. В каждое сообщение GPT-агенту сами подкладываются
сегодняшняя дата, доска задач, напоминания, файлы с ценами и база разборов: GPT сам их не перепроверяет. Нужен уже установленный Hermes со входом в ChatGPT
(урок «Создание агента с нуля на GPT»).

```
curl -fsSL https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/claude-to-gpt/claude-to-gpt.py -o ~/claude-to-gpt.py
python3 ~/claude-to-gpt.py /root/ai-victoriarubis marketer          # пробный прогон
python3 ~/claude-to-gpt.py /root/ai-victoriarubis marketer --apply  # перенос
```

Пошагово — в уроке «Создание агента с нуля на GPT», раздел «Как перенести своих агентов с Claude на GPT».

## Проверка на настоящих задачах (22.11)
После переноса — `python3 gpt-quality-check.py <профиль> <папка агента> 4`: берёт прошлые просьбы владельца, которые агент на Claude сделал хорошо, даёт их агенту на GPT в отдельном разговоре (ничего не меняет и не отправляет) и кладёт ответы рядом в `~/.hermes/profiles/<профиль>/quality-check.md`. Тратит лимит ChatGPT — 3–5 задач достаточно.

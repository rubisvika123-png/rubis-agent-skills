# claude-to-gpt — перенос агента с Claude на GPT (Hermes)

Если Claude недоступен, программа пересаживает агента из курса на движок Hermes с мозгом GPT:
характер, вся память, навыки и тот же Telegram-бот. Нужен уже установленный Hermes со входом в ChatGPT
(урок «Создание агента с нуля на GPT»).

```
curl -fsSL https://raw.githubusercontent.com/rubisvika123-png/rubis-agent-skills/main/claude-to-gpt/claude-to-gpt.py -o ~/claude-to-gpt.py
python3 ~/claude-to-gpt.py /root/ai-victoriarubis marketer          # пробный прогон
python3 ~/claude-to-gpt.py /root/ai-victoriarubis marketer --apply  # перенос
```

Пошагово — в уроке «Создание агента с нуля на GPT», раздел «Как перенести своих агентов с Claude на GPT».

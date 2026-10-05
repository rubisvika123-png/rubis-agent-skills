// style-guard — before the marketer agent sends its owner a draft (post,
// story, reel script, caption), a second model reads it against the owner's
// style file and refuses a draft that sounds like AI or not like the owner,
// with the concrete phrases to fix. Reports and short replies pass untouched.
//
// Fail-open on purpose: if the check itself fails (no model answer, bad JSON),
// the message goes out — a broken checker must never mute the agent. And at
// most MAX_REFUSALS per turn, so an argument with the checker can't loop.

// The marketer's style file from lesson 6; STYLE_GUARD_FILE in secrets/channel.env overrides.
// Session cwd is <agent>/dashi-plugin-claude-code/plugin.
const STYLE_FILE = '../../materials/examples.md'
const STYLE_CHARS = 14000 // the rules + reference posts sit at the top of the file
const MIN_CHARS = 280      // short replies ("готово", a status line) are not drafts
const MAX_REFUSALS = 2

let refusals = 0

const SYSTEM = `Ты строгий редактор владельца агента. Тебе дают сообщение, которое её агент-маркетолог
собирается отправить владельцу в Телеграм. Сначала реши: есть ли в нём ЧЕРНОВИК ТЕКСТА ДЛЯ ПУБЛИКАЦИИ
или для отправки людям (пост, сторис, сценарий рилса, рассылка, подпись, комментарий, сообщение
клиенту). Отчёты, цифры, статусы, вопросы владельцу — это не черновик.

Если черновик есть — проверь ТОЛЬКО его по двум вопросам:
1. Звучит ли он как написанный ИИ: гладкие риторические связки («И знаешь, что самое…»,
   «Давайте разберёмся», «Это не просто X — это Y»), канцелярит, однотипные тройки, вылизанность,
   продающее давление («Хочешь так же?», «жми», «успей»), буллеты выгод в личном сообщении,
   вычурная манерная проза и плотные абзацы (Anthropic: «Please remove all mannered prose.»).
2. Похож ли он на слог владельца из примеров и правил ниже (его словечки, длина фраз,
   пунктуация, эмоции, как он зовёт к действию). Правила из файла важнее общих.

Ответь ТОЛЬКО JSON без пояснений:
{"has_draft": true|false, "verdict": "ok"|"rewrite", "problems": ["конкретная фраза → что не так и как сказал бы владелец", ...]}
"rewrite" только при явных проблемах, мелочи не придирайся. Максимум 5 проблем.
Оформление — не слог и не признак ИИ: жирный (**...**) заголовок и жирный призыв, ссылки,
пометки вроде [жирным] не считай проблемой и не проси убрать — владелец сам требует так оформлять рассылки.
Если в сообщении сказано, что черновик — расшифровка или дословные слова самого владельца
(его кружок, голосовое, видео), это его настоящий слог: не требуй переписывать, verdict "ok".`

export function parseVerdict(text) {
  try {
    const m = String(text || '').match(/\{[\s\S]*\}/)
    if (!m) return null
    const v = JSON.parse(m[0])
    return { hasDraft: v.has_draft === true, rewrite: v.verdict === 'rewrite', problems: Array.isArray(v.problems) ? v.problems.slice(0, 5) : [] }
  } catch {
    return null
  }
}

async function judge($, text) {
  const style = (await $.fs.read((await $.env.get('STYLE_GUARD_FILE')) || STYLE_FILE)).slice(0, STYLE_CHARS)
  const r = await $.model.complete({
    model: 'sonnet',
    system: SYSTEM + '\n\nПРИМЕРЫ И ПРАВИЛА ВЛАДЕЛЬЦА:\n' + style,
    prompt: 'СООБЩЕНИЕ МАРКЕТОЛОГА:\n' + text,
    maxTokens: 700,
    timeoutMs: 60000,
  })
  return r && r.isAnswered ? parseVerdict(r.text) : null
}

export function register(on) {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'style-check', description: 'Run the style check on the given text', argumentHint: '<text>' })
    return next(e)
  })
  on('command.run', { command: 'style-check' }, async ($, e) => {
    return { text: JSON.stringify(await judge($, e.args)) }
  })

  on('turn.start', async ($, e, next) => { refusals = 0; return next(e) })

  on('tool.call', { tool: 'mcp__dashi-channel__reply' }, async ($, e, next) => {
    // A channel or group (negative chat id) means publishing a text the owner
    // already approved — the check is for drafts sent to the owner, not for her
    // own approved words (Liza 05.10.2026: an approved post was blocked).
    if (String(e.chat_id || '').startsWith('-')) return next(e)
    const text = String(e.text || '')
    if (text.length < MIN_CHARS || refusals >= MAX_REFUSALS) return next(e)
    let v = null
    try { v = await judge($, text) } catch { return next(e) }
    if (!v || !v.hasDraft || !v.rewrite) return next(e)
    refusals += 1
    return {
      deny: 'Сообщение НЕ отправлено: проверка слога нашла в черновике то, что владелец переделывал бы сам.\n- ' +
        v.problems.join('\n- ') +
        '\nПерепиши черновик по примерам из файла стиля и отправь заново. Остальную часть сообщения можно не менять.',
    }
  })
}

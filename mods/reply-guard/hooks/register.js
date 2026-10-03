// reply-guard — checks every message the agent is about to send to a person
// (Telegram reply/edit, ChatPlace chat message) against the owner's list of
// forbidden phrases, and refuses it with the reason so the agent rewrites it
// before anyone sees it.
//
// The list is a plain text file the owner edits, one rule per line:
//     фраза | почему нельзя и как сказать иначе
// Lines starting with # are comments. Default place: core/forbidden-phrases.txt
// in the agent's folder; REPLY_GUARD_RULES in secrets/channel.env overrides it.
// No file — nothing is checked.
//
// Word edges use lookarounds, not \b: \b does not work on Cyrillic.

const DEFAULT_RULES = '../../core/forbidden-phrases.txt' // session cwd is <agent>/dashi-plugin-claude-code/plugin
const L = '(?<![0-9A-Za-zА-Яа-яЁё])'
const R = '(?![0-9A-Za-zА-Яа-яЁё])'

// tool name -> the argument that carries the text people will read
const TEXT_FIELD = {
  'mcp__dashi-channel__reply': 'text',
  'mcp__dashi-channel__edit_message': 'text',
  'mcp__claude_ai_ChatPlace__chats_send_message': 'text',
}

function escape(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// "без кода | пиши «без технических знаний»" -> { re, phrase, why }
export function parseRules(text) {
  const rules = []
  for (const raw of String(text || '').split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const [phrase, ...rest] = line.split('|')
    const p = phrase.trim()
    if (!p) continue
    const body = p.split(/\s+/).map(escape).join('\\s*')
    rules.push({ re: new RegExp(L + body + R, 'i'), phrase: p, why: rest.join('|').trim() })
  }
  return rules
}

export function violations(text, rules) {
  return rules.filter((r) => r.re.test(String(text || ''))).map((r) => '«' + r.phrase + '»' + (r.why ? ' — ' + r.why : ''))
}

export function register(on) {
  on('tool.call', { tool: /^mcp__(dashi-channel__(reply|edit_message)|claude_ai_ChatPlace__chats_send_message)$/ },
    async ($, e, next) => {
      let rulesText = ''
      try { rulesText = await $.fs.read((await $.env.get('REPLY_GUARD_RULES')) || DEFAULT_RULES) } catch { return next(e) }
      const found = violations(e[TEXT_FIELD[e.tool]], parseRules(rulesText))
      if (!found.length) return next(e)
      return { deny: 'Сообщение НЕ отправлено: в нём запрещённые владельцем фразы. Перепиши и отправь заново.\n- ' + found.join('\n- ') }
    })
}

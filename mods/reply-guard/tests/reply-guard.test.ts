import { expect, test } from 'claude-code/testing'
import { parseRules, violations } from '../hooks/register.js'

const RULES = `# мои правила
ctrl+c | выход только командой /exit
ctrl-c | выход только командой /exit
твоим голосом | говорим «в твоём стиле»
без кода | пиши «без технических знаний»
`

function wire(on: any, rules: string | null) {
  on('env.get', () => ({ value: undefined }))
  on('fs.read', () => (rules === null ? { deny: 'no file' } : { value: rules }))
  on('tool.call', () => ({ result: 'sent' }))
}

test('clean reply goes out', async ($, on) => {
  wire(on, RULES)
  const out = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: 'Готово, выход — командой /exit.' })
  expect(out).toEqual({ result: 'sent' })
})

test('a forbidden phrase is refused with the owner reason', async ($, on) => {
  wire(on, RULES)
  const out: any = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: 'Нажмите Ctrl+C и запустите снова' })
  expect(out.deny).toContain('/exit')
})

test('ChatPlace message is checked too', async ($, on) => {
  wire(on, RULES)
  const out: any = await $.tool.call({ tool: 'mcp__claude_ai_ChatPlace__chats_send_message', chatId: 'x', text: 'Курс без кода!' })
  expect(out.deny).toContain('без технических знаний')
})

test('no rules file — nothing is checked', async ($, on) => {
  wire(on, null)
  const out = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: 'Нажмите Ctrl+C' })
  expect(out).toEqual({ result: 'sent' })
})

test('other tools are not touched', async ($, on) => {
  wire(on, RULES)
  const out = await $.tool.call({ tool: 'Bash', command: 'echo ctrl+c без кода' })
  expect(out).toEqual({ result: 'sent' })
})

test('word edges work on Cyrillic', () => {
  const r = parseRules(RULES)
  expect(violations('агент пишет твоим голосом', r).length).toBe(1)
  expect(violations('Твоим   голосом', r).length).toBe(1)
  expect(violations('в твоём стиле, голосовые сообщения', r).length).toBe(0)
  expect(violations('без кодировки', r).length).toBe(0)
  expect(violations('Ctrl-C', r).length).toBe(1)
  expect(violations('ctrl+cmd', r).length).toBe(0)
})

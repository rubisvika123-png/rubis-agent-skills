import { expect, test } from 'claude-code/testing'
import { parseVerdict } from '../hooks/register.js'

const LONG = 'Вот черновик поста для канала: ' + 'Это не просто инструмент — это настоящий прорыв. '.repeat(8)

function wire(on: any, modelText: string | null) {
  const asked: any[] = []
  on('env.get', () => ({ value: undefined }))
  on('fs.read', () => ({ value: '# Примеры моих текстов\nЭталон...' }))
  on('model.complete', ($: any, e: any) => {
    asked.push(e)
    return { value: modelText === null ? { isAnswered: false, reason: 'down' } : { isAnswered: true, text: modelText, usage: null } }
  })
  on('tool.call', () => ({ result: 'sent' }))
  on('turn.start', ($: any, e: any) => ({ turnId: e.turnId }))
  return asked
}

test('short status replies are not checked at all', async ($, on) => {
  const asked = wire(on, '{"has_draft":true,"verdict":"rewrite","problems":["x"]}')
  const out = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: 'Готово, выложила.' })
  expect(out).toEqual({ result: 'sent' })
  expect(asked.length).toBe(0)
})

test('an AI-sounding draft is sent back with the problems', async ($, on) => {
  wire(on, '{"has_draft":true,"verdict":"rewrite","problems":["«это не просто X — это Y» → ИИ-штамп"]}')
  const out: any = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: LONG })
  expect(out.deny).toContain('ИИ-штамп')
})

test('a good draft or a report goes out', async ($, on) => {
  wire(on, '{"has_draft":false,"verdict":"ok","problems":[]}')
  const out = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: LONG })
  expect(out).toEqual({ result: 'sent' })
})

test('a broken checker never mutes the agent', async ($, on) => {
  wire(on, null)
  const out = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: LONG })
  expect(out).toEqual({ result: 'sent' })
})

test('after two refusals in one turn the third attempt goes out', async ($, on) => {
  wire(on, '{"has_draft":true,"verdict":"rewrite","problems":["x"]}')
  await $.turn.start({ turnId: 't' } as any)
  const a: any = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: LONG })
  const b: any = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: LONG })
  const c = await $.tool.call({ tool: 'mcp__dashi-channel__reply', chat_id: '1', text: LONG })
  expect(a.deny).toBeDefined()
  expect(b.deny).toBeDefined()
  expect(c).toEqual({ result: 'sent' })
})

test('verdict parsing tolerates prose around the JSON and rejects junk', () => {
  expect(parseVerdict('вот: {"has_draft":true,"verdict":"rewrite","problems":["a"]} всё')!.rewrite).toBe(true)
  expect(parseVerdict('нет json')).toBe(null)
})

import { expect, mock, test } from 'claude-code/testing'
import { mskTime, warningText } from '../hooks/register.js'

const ENV = { TELEGRAM_BOT_TOKEN: '123:abc', TELEGRAM_ALLOWED_USER_IDS: '111111111,222222222', AGENT_ID: 'coder' }
const FIVE = (pct: number) => ({ kind: 'five_hour', percentUsed: pct, resetsAt: '2026-10-03T12:40:00Z' })

function wire(on: any) {
  mock.env(on, ENV)
  const saved = new Map<string, unknown>()
  on('store.get', ($: any, e: any) => ({ value: saved.get(e.key) }))
  on('store.set', ($: any, e: any) => { saved.set(e.key, e.value); return { value: undefined } })
  on('ui.log', () => ({ value: undefined }))
  const sent: any[] = []
  on('http.fetch', ($: any, e: any) => { sent.push(e); return { value: { status: 200, ok: true, headers: {}, text: '{"ok":true}' } } })
  on('session.measure', ($: any, e: any) => ({ changed: e.changed }))
  return sent
}

test('below 90% nobody is bothered', async ($, on) => {
  const sent = wire(on)
  await $.session.measure({ context: { window: 1 }, rateLimits: [FIVE(89.9)], changed: ['rateLimits'] })
  expect(sent.length).toBe(0)
})

test('at 90% the owner gets one warning, not one per measurement', async ($, on) => {
  const sent = wire(on)
  await $.session.measure({ context: { window: 1 }, rateLimits: [FIVE(91)], changed: ['rateLimits'] })
  await $.session.measure({ context: { window: 1 }, rateLimits: [FIVE(95)], changed: ['rateLimits'] })
  expect(sent.length).toBe(1)
  const body = JSON.parse(sent[0].init.body)
  expect(body.chat_id).toBe('111111111')
  expect(body.text).toContain('15:40')
  expect(sent[0].url).toContain('bot123:abc/sendMessage')
})

test('a new window (new reset time) warns again', async ($, on) => {
  const sent = wire(on)
  await $.session.measure({ context: { window: 1 }, rateLimits: [FIVE(92)], changed: ['rateLimits'] })
  await $.session.measure({ context: { window: 1 }, rateLimits: [{ ...FIVE(93), resetsAt: '2026-10-03T17:40:00Z' }], changed: ['rateLimits'] })
  expect(sent.length).toBe(2)
})

test('weekly limit names the date', () => {
  expect(warningText({ kind: 'seven_day', percentUsed: 90.4, resetsAt: '2026-10-07T06:00:00Z' })).toContain('07.10 в 09:00')
  expect(mskTime('garbage', false)).toBe(null)
})

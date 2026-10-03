import { expect, mock, test } from 'claude-code/testing'
import { inJournal } from '../hooks/register.js'

const JOURNAL = '2026-10-03T08:00:00Z text Верни открытые чаты боту, пожалуйста\n'

function wire(on: any, draft: { text: string }, journal: string) {
  const clock = mock.clock(on)
  on('session.start', () => ({ cwd: '/agent' }))
  on('prompt.read', () => ({ value: { text: draft.text, cursor: draft.text.length } }))
  on('fs.read', () => ({ value: journal }))
  on('ui.log', () => ({ value: undefined }))
  const fills: string[] = []
  on('prompt.fill', ($: any, e: any) => { fills.push(e.text); draft.text = e.text; return { isFilled: true } })
  const sent: string[] = []
  on('prompt.submit', ($: any, e: any) => { sent.push(e.text); return { text: e.text } })
  on('turn.start', ($: any, e: any) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  return { clock, sent, fills }
}

test('a stuck Telegram message is submitted once, after it sat unchanged', async ($, on) => {
  const draft = { text: 'Верни открытые чаты боту, пожалуйста' }
  const { clock, sent } = wire(on, draft, JOURNAL)
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/agent' })
  await clock.advance(20_000)
  expect(sent).toEqual([]) // first sighting: wait
  await clock.advance(20_000)
  expect(sent).toEqual(['Верни открытые чаты боту, пожалуйста'])
  await clock.advance(60_000)
  expect(sent.length).toBe(1)
})

test('a suggestion-like line not in the journal is never sent', async ($, on) => {
  const draft = { text: 'Жду результатов про моды' }
  const { clock, sent } = wire(on, draft, JOURNAL)
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/agent' })
  await clock.advance(100_000)
  expect(sent).toEqual([])
})

test('nothing is sent while the agent is busy', async ($, on) => {
  const draft = { text: 'Верни открытые чаты боту, пожалуйста' }
  const { clock, sent } = wire(on, draft, JOURNAL)
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/agent' })
  await $.turn.start({ turnId: 't1' } as any)
  await clock.advance(100_000)
  expect(sent).toEqual([])
})

test('journal match uses the first 40 chars', () => {
  expect(inJournal('Верни открытые чаты боту, пожалуйста', JOURNAL)).toBe(true)
  expect(inJournal('   ', JOURNAL)).toBe(false)
  expect(inJournal('что-то другое', JOURNAL)).toBe(false)
})

test('without a journal, a draft is sent only after it sat a whole minute', async ($, on) => {
  const draft = { text: 'когда будет готово?' }
  const clock = mock.clock(on)
  on('session.start', () => ({ cwd: '/agent' }))
  on('prompt.read', () => ({ value: { text: draft.text, cursor: 0 } }))
  on('fs.read', () => ({ deny: 'no such file' }))
  on('ui.log', () => ({ value: undefined }))
  on('prompt.fill', ($: any, e: any) => { draft.text = e.text; return { isFilled: true } })
  const sent: string[] = []
  on('prompt.submit', ($: any, e: any) => { sent.push(e.text); return { text: e.text } })
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/agent' })
  await clock.advance(60_000)
  expect(sent).toEqual([])
  await clock.advance(20_000)
  expect(sent).toEqual(['когда будет готово?'])
})

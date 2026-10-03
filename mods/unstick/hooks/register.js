// unstick — the in-process replacement for scripts/agent-unstick.sh.
//
// A channel message that lands while the agent is busy can stay in the input
// box and never be sent (seen since 2026-08-25). The old script screen-scrapes
// the pane, and the screen also shows Claude Code's own dim suggestion on that
// line — 3,000+ refusals logged and, on 2026-09-03/29, invented «Vika»
// messages answered. $.prompt.read() returns the real draft only, never the
// suggestion, so that confusion is gone at the source.
//
// A draft is submitted only when (1) the agent is idle, (2) the draft is
// unchanged since the previous check (nobody typing it now), (3) it wasn't
// submitted already, and (4) if the bridge keeps an inbound journal (newer
// dashi plugins do), its first 40 chars are in it — i.e. it really came from
// Telegram. Without a journal, (2) must hold for STABLE_NO_JOURNAL checks.

const JOURNAL = 'state/telegram/inbound-recent.log' // relative to the plugin dir = session cwd
const EVERY_MS = 20_000
const STABLE_NO_JOURNAL = 3 // ~1 minute unchanged when there is no journal to prove the source

let busy = false
let lastSeen = ''
let stable = 0
const submitted = new Set()

export function inJournal(draft, journal) {
  const head = draft.trim().slice(0, 40)
  return head.length > 0 && String(journal || '').includes(head)
}

export function register(on) {
  on('turn.start', async ($, e, next) => { busy = true; return next(e) })
  on('turn.complete', async ($, e, next) => { busy = false; return next(e) })

  on('session.start', async ($, e, next) => {
    $.clock.every(EVERY_MS, async () => {
      if (busy) return
      const { text } = await $.prompt.read()
      const draft = (text || '').trim()
      if (!draft) { lastSeen = ''; stable = 0; return }
      if (draft !== lastSeen) { lastSeen = draft; stable = 0; return } // wait one more check
      stable += 1
      if (submitted.has(draft)) return
      let journal = null
      try { journal = await $.fs.read(JOURNAL) } catch { journal = null }
      if (journal === null && stable < STABLE_NO_JOURNAL) return
      if (journal !== null && !inJournal(draft, journal)) {
        $.ui.log('draft left alone, not from Telegram: ' + draft.slice(0, 60))
        submitted.add(draft) // judged once, don't re-log it every 20 s
        return
      }
      submitted.add(draft)
      await $.prompt.fill({ text: '' })
      await $.prompt.submit({ text: draft, asUser: true })
      $.ui.log('submitted a stuck Telegram message: ' + draft.slice(0, 60))
    })
    return next(e)
  })
}

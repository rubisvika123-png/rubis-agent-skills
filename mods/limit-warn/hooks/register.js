// limit-warn — tells the agent's owner in Telegram BEFORE a Claude plan limit
// runs out, with the reset time. Vika 03.10.2026: today the watchdog only
// notices a limit after the agent has already gone silent.
//
// Fires on session.measure (after each turn and whenever a limit's percent
// moves). One message per limit window: the window is identified by its kind
// and reset time, remembered in $.store so a restart doesn't repeat it.
// The bot token and owner id come from the agent's own environment
// (start.sh loads secrets/channel.env), so the warning arrives from the
// agent's own bot, like the watchdog's.

const THRESHOLD = 90

const KIND_RU = { five_hour: 'пятичасового', seven_day: 'недельного' }

// "2026-10-03T12:40:00Z" -> "15:40" (MSK, UTC+3, no DST); weekly adds the date
export function mskTime(iso, withDate) {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  const d = new Date(t + 3 * 3600 * 1000)
  const p = (n) => String(n).padStart(2, '0')
  const hm = p(d.getUTCHours()) + ':' + p(d.getUTCMinutes())
  return withDate ? p(d.getUTCDate()) + '.' + p(d.getUTCMonth() + 1) + ' в ' + hm : hm
}

export function warningText(rl) {
  const kind = KIND_RU[rl.kind] || ''
  const when = rl.resetsAt ? mskTime(rl.resetsAt, rl.kind !== 'five_hour') : null
  return 'У меня израсходовано ' + Math.floor(rl.percentUsed) + '% ' + kind +
    ' лимита Claude (он общий у всех агентов на этой подписке). Скоро можем замолчать до обновления' +
    (when ? ' — оно в ' + when + ' по Москве.' : '.') +
    ' Срочное лучше отдать сейчас.'
}

export function register(on) {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'limit-status', description: 'Show plan limits as limit-warn sees them' })
    return next(e)
  })

  on('command.run', { command: 'limit-status' }, async ($) => {
    const u = await $.session.usage()
    return { text: JSON.stringify(u.rateLimits) }
  })

  on('session.measure', async ($, e, next) => {
    const hot = (e.rateLimits || []).filter((rl) => rl.percentUsed >= THRESHOLD && rl.kind !== 'spend_limit')
    if (hot.length) await warn($, hot)
    return next(e)
  })
}

async function warn($, hot) {
  const token = await $.env.get('TELEGRAM_BOT_TOKEN')
  const owner = ((await $.env.get('TELEGRAM_ALLOWED_USER_IDS')) || '').split(',')[0].trim()
  if (!token || !owner) {
    $.ui.log('no TELEGRAM_BOT_TOKEN / TELEGRAM_ALLOWED_USER_IDS — cannot warn')
    return
  }
  // One key for the whole machine user: every agent here shares one Claude
  // subscription, so whichever agent sees the window first warns, the rest stay quiet.
  const storeKey = 'notified'
  const done = (await $.store.get(storeKey)) || {}
  for (const rl of hot) {
    const id = rl.kind + '|' + (rl.resetsAt || '')
    if (done[id]) continue
    const res = await $.http.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: owner, text: warningText(rl) }),
    })
    if (!res.ok) {
      $.ui.log('Telegram refused the warning: status ' + res.status)
      continue // not remembered, so the next measurement retries
    }
    done[id] = Date.now()
    $.ui.log('warned owner: ' + rl.kind + ' at ' + rl.percentUsed + '%')
  }
  // keep only recent windows so the store doesn't grow forever (8 days)
  const cutoff = Date.now() - 8 * 24 * 3600 * 1000
  for (const k of Object.keys(done)) if (done[k] < cutoff) delete done[k]
  await $.store.set(storeKey, done)
}

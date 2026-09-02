# Ops Hardening Plan — before the Nov 25 renewal week

Current: SQLite on one box behind Cloudflare Tunnel, subprocess per sync (300s timeout),
cookie jars on local disk. Fine for ~20 users; fails under 500 concurrent during renewal week.

## Priority order
1. **SQLite WAL mode + daily backup cron** — lowest effort, do first
2. **Rate limiting** per user on sync endpoints (prevent stampede during renewal week)
3. **Subprocess sync → in-process** with proper session management (removes the 300s timeout ceiling)
4. **Session jars → encrypted at rest** (Fernet, same scheme as cebroker_email)
5. **Failure-spike alerts** to Telegram (renewal-week incident indicator)
6. **Postgres migration** only if user count demands it (>200 active syncs/day)

## Renewal-week readiness checklist
- [ ] WAL mode enabled + tested
- [ ] Daily backup cron running before Nov 20
- [ ] Rate limits: max N syncs/hour/user, global cap
- [ ] Kill switch tested (BREATHE_CEBROKER_SYNC_ENABLED=false)
- [ ] Sync-failure alerts wired to Telegram
- [ ] Load test: 50 concurrent syncs

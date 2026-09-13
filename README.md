# relocation-jobs-agent

A scheduled bot that finds **newly posted jobs offering visa sponsorship or relocation support** —
across Europe, the UAE, Singapore, Canada, and remote roles open worldwide — and publishes them
to a Telegram channel with a link to each opening.

```
 daily ──► discover ──► job APIs + companies' own career boards
                         │  keyword rules → optional model check → region tagging
                         ▼
                    data/queue.json ──► every 20 min: publish ──► Telegram
 weekly ──► refresh-companies ──► seed list ∪ observed employers ──► board detection ──► sponsor registers
```

## How it works

**Discover (daily).** Pulls postings from the last 24 hours out of
[Arbeitnow](https://www.arbeitnow.com/api/job-board-api) (which flags visa sponsorship explicitly),
[Remotive](https://remotive.com/api/remote-jobs), [Jobicy](https://jobicy.com/api/v2/remote-jobs),
and the Greenhouse / Lever / Ashby boards of every company in `data/companies.json`. Each posting is
screened: a configurable list of negative phrases ("no sponsorship", "must be authorised to work…")
rejects outright, positive phrases ("relocation package", "Blue Card", "Employment Pass"…) accept,
and anything ambiguous can be handed to a language model under a strict per-run call budget.
Accepted jobs are tagged with a region from their location and queued.

**Publish (every 20 minutes, working hours).** Posts the next queued job if the daily cap and the
minimum spacing allow. Everything is idempotent — a job is never posted twice.

**Refresh companies (weekly).** Merges the curated seed list with employers that posted accepted
jobs recently, tries to detect a public ATS board for each, and checks them against the UK Home
Office sponsor register and Canada's positive-LMIA employer dataset.

## License

MIT

# Job radar — run instructions

You run three times a day (morning, noon and evening) and send the candidate a short email of new jobs worth applying to. He should be able to read it in two minutes and start applying, with no shortlisting left to do. Rewritten 8 September 2026; the older, longer version and every dated lesson from it are in `notes/`.

Read `instructions/PROFILE.md` first. It defines who he is, what disqualifies a job, the two German bands, how to score, how to rank. Follow it exactly. Then read `state/applications.md`, the log of what he already researched or applied to. Do not read `notes/` unless a source is broken and you need its history.

Aim to finish in about 90 minutes (raised from 25 on 29 Sep 2026, when a run read 52 of 477 candidates, then to 45, then to 90 on 30 Sep 2026 at the candidate's request, because about 60 jobs a run is too few). Collection is one command. Your time goes into reading and scoring, so use the time to read further down the list.

Check the time with `python3 scripts/slots.py --elapsed $SC`. It counts from the moment collection started. The reader (`scripts/read_next.py`, section 3) prints the same clock with every batch and stops handing out jobs at 80 minutes. Then finish the employer apply links, write the shortlist and render. Never judge the time by feel. On 30 Sep 2026 the morning run believed it was 72 minutes in when 20 had passed, read 59 of 318 candidates, and skipped the apply links. `write_pack.py` fills `minutes` from the same clock, so the value you write is replaced.

## 1. Load state

Read `state/seen.json`, `state/applications.md`, and the board list in `instructions/COMPANIES.md` (the list only, it has no run notes any more). Decide the slot with `python3 scripts/slots.py`: `morning` before 10:00 UTC, `noon` from 10:00 to 15:00 UTC, `evening` after that. Use it for the shortlist file name and `slot` in `shortlist.json`.

**The noon run** (Monday and Thursday, 13:30 Berlin time; daily from 29 Sep to 29 Oct 2026) finishes what the morning and evening runs left unread and resolves the rows nobody could read. Each morning and evening run ends by writing every candidate it did not read into `state/leftover.json` (`write_pack.py` does this; it prints a `state/leftover.json:` line). At noon `collect_all.py` collects nothing. It turns `state/leftover.json` into `candidates.json`, drops anything sent or applied to since, and prints a `noon run: no collection` line. Skip the title triage (those rows were triaged already) and the funded-startup sweep. Run `fetch_desc.py`, which retries any row whose description could not be fetched earlier. Then run `python3 scripts/retext.py $SC`: it lists every row still without text, with its id. For each one, search the web for the company and the title. Look for the employer's own careers page first, then the Bundesagentur, then a job board copy that carries the full text. When a page carries the posting, run `python3 scripts/retext.py $SC <id> <url>`: it fetches the text onto the row and the reader prints it in the next batch like any other job. When no page carries it, or every copy is closed or outside Germany, hand in a verdict with gate `no_text` and a reason that says where you looked and what the pages said (`verdict.py` takes this gate without a printed text). Ten minutes at most for the whole search. Measured 29 Oct 2026 on the 10 rows then on the list: 2 resolved (Hornetsecurity, on the Bundesagentur), 8 retired (Forithmus is a Zurich startup with no posting anywhere, Revolut's roles are outside Germany, Synera's Recruitee page is 404, Pillar and Carrier are nowhere). Then read from the top as usual. Every verdict, `no_text` included, goes into `state/decisions.json` for 14 days, so the morning and evening runs stop listing a retired row under Could not be read, and into `state/backlog_done.json`, so it leaves `state/leftover.json`. When you render, `write_pack.py` removes from `state/leftover.json` every row you processed, and the rows you did not reach stay for the next noon. Morning and evening still read fresh jobs as before. So list every job you read in `rejected` or `jobs`, as always. There is no mailbox scan at noon (section 8 is evening only) and no pack cleanup. New postings wait for the evening run, which collects everything as usual.

## 2. Collect, one command

    SC=$(mktemp -d)
    python3 scripts/collect_all.py $SC

Run it as a background command and wait for its finish notice. Do not run it in the foreground: a foreground command is killed at 10 minutes, and LinkedIn alone took 12 to 20 minutes on 5 of the 58 collecting runs in October 2026, so each of those runs collected twice. Do not poll for the file while it runs. The command's last line names the file to work from: `$SC/candidates.json`. That file is in the scratch directory, never in the repo root, and there is nothing else to wait for (on 30 Sep a run polled the repo root for five minutes).

It runs every collector in parallel, writes one JSON per source into `$SC`, a `<source>.log` per collector, then runs `scripts/filter_run.py`, which writes `candidates.json` (fresh, title-relevant, not a repeat, not the same role he already applied to; other roles at a company he applied to are kept and tagged `applied_before`), `repeats.json`, and `phd_off.json`. Its stderr ends with a `relevance-passed` line, an `after repeat check` line and a `rejected before` line; keep all three for the coverage table. A `read by an earlier run, verdict remembered` line counts the jobs that left the list because a run of the last 14 days already read them (`state/decisions.json`, written by `write_pack.py` from every run's verdicts). They are listed in `remembered.json` with the old verdict and are not read again. A job whose text changed since comes back into the list, marked `text_changed`. If the candidate says a verdict was wrong, `python3 scripts/decisions.py forget "<company>" "<title words>"` removes it and the next run reads the job again. The `rejected before` line counts jobs an earlier run dropped on a quoted German requirement above B1 or a nationality or clearance rule in the last 14 days. They are listed in `rejected_before.json` and are not read again. `state/rejected.json` at the repo root holds them, and `write_pack.py` adds your `rejected` list to it. Judgement rejections are deliberately not remembered, so those jobs come back and are read again. A `German required, dropped unread` line counts rows whose description states a strong German requirement in one sentence; they are in `german_off.json` with the sentence. Report the count in the coverage table. Do not read them or list them in `rejected`; the filter drops them again every run. Referral rows are never dropped this way. A `German line unclear, kept for the agent to decide` line counts rows that stay in `candidates.json` with the unclear sentences in `german_decide` (instructions/PROFILE.md, Language rule). Those rows are yours to decide when you read them. A `Nationality or clearance required, dropped unread` line counts rows whose text demands a citizenship or a security clearance in firm words; they are in `clearance_off.json` with the sentence, and you do not read or list them. A row whose clearance line is only conditional stays in the list, and `write_pack.py` puts that sentence into the job's Gaps line by itself.

Sources, and the one fact about each that matters:

- **Bundesagentur für Arbeit API** (`ba.json`). Search is `v6` and the results key is `ergebnisliste`; detail is `v4`. The arbeitsagentur.de page sits behind a captcha, so section 3 resolves every BA job to the employer's own posting.
- **Company ATS boards** (`ats.json`), every slug in `instructions/COMPANIES.md`. Greenhouse, Lever, Ashby, Personio, Teamtailor, Workable, Recruitee, SmartRecruiters, join.com.
- **LinkedIn, last 24 hours** (`linkedin.json`). The guest endpoint, verified from this cloud environment on 8 September 2026. Cards only; `scripts/read_linkedin.py` fetches the full description. This is the source he cares about most, because a job that is hours old lets him reach people at the company before the pool grows. Never write it off on the strength of a web search; the web search never worked, the endpoint does.
- **XING** (`xing.json`). Rows arrive with the description, the real posting date and, on most rows, the employer's own apply URL. Rows older than 14 days are filtered out.
- **StepStone, last 3 days** (`stepstone.json`). Works from this cloud environment only, the laptop is blocked. Rows arrive with the JSON-LD description, employer, real posting date and employment type. The url is StepStone's page; find the employer's copy as in section 3 and keep the StepStone link as `fallback_url`.
- **de.talent.com** (`talent.json`). Cards with a company name and title; `scripts/read_talent.py` fetches the full text.
- **arbeitnow** (`arbeitnow.json`). Full descriptions inline. Its date is an ingest date, so take freshness from the employer's board.
- **VC portfolio boards on Getro** (`getro.json`). About 5,300 rows a morning, 4 in 100 pass the title and location filters, so `collect_all.py` runs it in the morning slot only.

Dropped sources. berlinstartupjobs produced zero across 28 runs. The `site:linkedin.com`, `site:xing.com` and `site:stepstone.de` web-search sweeps produced index pages, and are replaced by the three collectors above. Indeed and Glassdoor answer 403 from here.

Newly funded startups. Weekly, not every run. Run `python3 scripts/sweep_due.py` in every morning and evening run (the noon run skips it). When it prints `DUE`, run the sweep in this run, ten minutes at most; when it prints `NOT DUE`, skip it and copy that line into the coverage table. Start from `python3 scripts/sweep_due.py --leads`, which lists the deutsche-startups.de funding posts (#DealMonitor, #StartupTicker, #Wochenrückblick) since the last sweep. Open the ones that name a German AI or ML startup, find its careers page, and read the roles there. If the feed prints `NO LEADS` or `FEED ERROR`, fall back to a web search and say so. If a board slug can be confirmed, add it to `instructions/COMPANIES.md` so the collector polls it from then on. When the sweep is finished, record it with `python3 scripts/sweep_due.py --done <roles found> "<one-line summary>" <slugs added>` and commit `state/sweep.json` with the run. A sweep that is due and skipped stays due, so the next run picks it up.

On the evening run `collect_all.py` also runs `scripts/prune_packs.py` (every second evening; it skips itself when its last check was less than 2 days ago and prints `prune: skipped`), which deletes the pack of a job he never applied to once it was sent 3+ days ago (20 until 29 Oct 2026; this is the backlog refresh, so a closed job leaves his batch list within a day or two), its apply and fallback links both check GONE (its board, not a LinkedIn copy, decides), the job is not in this run's collected pool, and it was GONE on an earlier check at least a day before. Its `PRUNED` lines and summary go in the notes; commit `state/prune.json` and the deletions with the run. `collect_all.py` ends with a `--- health ---` block from `scripts/health.py`: SOURCE LOW, SOURCE ZERO, BOARD DEAD, BOARD EMPTY, BOARD NEW and, on the first recorded run, FIRST RUN. They are recorded in `state/health.json` and printed in the email by `write_pack.py`; commit `state/health.json` and `state/health_candidates.json` with the run. Look into any SOURCE flag in this run. For a BOARD DEAD, open the board once; if it moved, fix the slug in `instructions/COMPANIES.md`, and if it is gone, delete the line. If a collector's log ends with a non-zero return code or zero rows, say so in the coverage table with the last log line. Fix it only when the fix is one line and you can verify it in the same run. Otherwise leave it and write the symptom into `notes/`.

## 2b. Title triage, before any full read

Run `python3 scripts/triage.py $SC list`. It writes `$SC/titles.txt`, one numbered line per candidate: number, prescore, company, title, source. Read the whole list once, by title and company only. Write `$SC/title_drop.txt` with one line per row to drop, `<number> <one-word reason>`. Then run `python3 scripts/triage.py $SC apply`, which removes those rows from `candidates.json` and keeps them in `title_dropped.json`.

Drop a row only when the title is plainly not AI, ML, computer vision, data science, MLOps, agentic, LLM, GenAI, NLP, speech or audio ML, or robotics perception work: sales, marketing, product specialists, HR, auditors, recruiters' own staff, pure frontend, project managers, field installers, postdocs. Keep anything related, and keep data engineering titles, which he wants (instructions/PROFILE.md, 30 Sep 2026). Data analyst and BI titles are still dropped. **Keep every unclear title** ("Software Engineer II", "Member of Technical Staff", a recruiter's generic "Engineer", "Research Engineer" with no field): an unclear title is read, never dropped. When in doubt, keep. Report `title_dropped` (the count) in the reading line.

Why: on 29 Sep the morning run read 52 of 477 candidates and an audit of the unread rows found 34 jobs worth sending, sitting all the way down the list (median rank about 178). This triage dropped a third of them with one borderline miss, so the full reads reach much further.

Then fetch the full text for the clean rows with `python3 scripts/fetch_desc.py $SC`. Every row that has no description is fetched here, from any source (changed 2 Oct 2026). Bundesagentur, LinkedIn and talent.com rows go through their own readers. Every other row without text (Getro, SmartRecruiters, JOIN, Avature, Breezy, and the Personio boards whose feed carries no text) is read from its link by `scripts/jobpage.py`. No description is cut at any length. The script writes each description into `candidates.json`, drops the rows whose text states a strong German requirement into `german_off_fetched.json`, and sorts the list again by prescore. Add its `German required, dropped after fetch` count to `german_dropped`, and do not read or list those rows.

It prints two lines, and both go into the notes. The first ends with how many rows failed and how many postings were closed. A closed posting (its own link says so) is removed and listed in `gone.json`; do not read it or list it. A failed row stays in the list without a description and is listed in `no_text.json` with the reason. The second line is the text check: how many candidates have the full text and how many have none. **A row in `no_text.json` was not read.** Never count it in `read_full`, and never write "no language line in the posting" for it, because nobody saw the posting. To try another link for such a row, run `python3 scripts/jobpage.py <url>`, which prints the whole text or says why it cannot.

**Fresh jobs first, and every one of them.** the candidate applies to a job in his field on the day it is posted, while the pool of applicants is small, and that is what this radar is for. `candidates.json` is sorted freshest first: jobs posted within a day, then within three days, then the rest, and by prescore inside each group (`reading.fresh_first_days` in `config/radar.yaml`). Read every job posted in the last two days before any older one, in order, and do not skip one because its title or score looks weaker: on 29 Sep the evening run skipped statworx, Brainlab and Apheris, all posted that day and all in the field. `scripts/fresh_check.py` enforces this in section 5.

After the fresh jobs, read down the list as far as the run allows, not just the top. The prescore is a floor, not a ranking: nothing below 0 was useful, but between 0 and 5 the hit rate was flat.

## 3. Read each promising posting

**One reader, and a verdict after every batch** (2 Oct 2026). `candidates.json` is sorted freshest first and by `prescore` inside each group. You read it with one command and with nothing else:

    python3 scripts/read_next.py $SC

It prints the next few unread jobs, each one whole. Above each text it prints the lines that decide a job most often (language, clearance or nationality, years, PhD), and any German line the code could not settle. Read every job of the batch. Then hand in one verdict per job, as a JSON list:

    python3 scripts/verdict.py $SC - <<'EOF'
    [{"id": "<id the reader printed>", "fit": 7, "gate": "", "band": "A",
      "lang_line": "<the sentence from the text, or: no language line in the posting>",
      "reason": "<one plain line tied to his real work, or the quoted line the gate rests on>",
      "hard_req": "<the quoted requirement that demands years in a tool or method he has never used, or: none>"}]
    EOF

`verdict.py` stores the verdicts and prints the next batch itself, so one command per batch is enough. Repeat until it prints `ALL READ` or `TIME`. It hands out no new batch while a job of the last one has no verdict. `verdict.py` refuses a verdict that names a gate outside the ten in instructions/PROFILE.md, that says "no language line" although the text names German, or that waves through a German line the code flagged. Fix what it prints and hand in again.

Rules that go with it:

- **Never write a helper of your own to print, shorten or scan the candidates, and never read a job through `python3 -c`, `jq`, `head` or a slice.** On 30 Sep a run printed 300 characters per job and reported 248 jobs "read in full". A job counts as read only when `read_next.py` printed it. `write_pack.py` takes `read_full` from the reader's log, and `final_check.py` and `write_pack.py` refuse to send a job the reader did not print. A run that has candidates and never started `read_next.py` is refused at render as a whole, whatever its shortlist says (3 Oct 2026). `write_pack.py` also stores when each batch was printed and when its verdicts came back, in `reading` in the shortlist file, and `python3 scripts/read_audit.py` prints that record.
- **Read in the order the reader gives. Do not skip a job.** There is no "skip by title" here: the title triage in section 2b was the place for that.
- `hard_req` is required on every verdict at fit 7 or higher. Quote the requirement when the posting demands years of experience in a specific tool or method he has never used and the role is built on it (instructions/PROFILE.md, "A hard requirement he cannot back caps the fit at 6"). Write "none" when there is no such requirement. A quoted `hard_req` caps the fit at 6, so the job becomes one line with the requirement shown.
- The `fit` and `gate` you hand in decide where the job goes. A gate rejects it. No gate and fit 7 or higher sends it in full, and there is no cap on how many. No gate and fit 6 lists it as one line. No gate and fit 5 or lower lists it as borderline. A referral row is sent at fit 5 or higher.
- A job with no text is never printed. The reader counts those rows and `no_text.json` names each with the reason. To try another link, run `python3 scripts/jobpage.py <url>`. Do not fetch a posting through WebFetch, which returns a summary of the page and not the page. A job found outside the list (the employer's careers page, the funded-startup sweep) is added and read like the rest with `python3 scripts/read_next.py $SC --add <url> "<company>" "<title>"`.
- If the tool shortens a batch on the way to you, the whole batch is in `$SC/batches/batch_<n>.txt`. Read that file.
- `python3 scripts/read_next.py $SC --status` prints the counts at any time.

**Take the salary while you are in the text.** Search the description for a figure before you leave it. German adverts write it as `70.000 - 90.000 EUR` or `Gehaltsspanne`, English ones as `EUR 90-120k` or `up to €80,000`. `python3 scripts/salary.py --show <file>` reads a band out of a saved description and prints the sentence it came from, which is the quick way to check yourself on a long posting. It prints nothing when the posting names no figure, and that is the normal answer. Figures in the title line, a single labelled figure ("Einstiegsgehalt ca. 90.000 €") and public pay scales ("TV-L EG 13") all count, and `salary.py` reads them.

**Size class, for the salary ask.** For every job you send, set `size_class` and `staff` in `shortlist.json`: `startup` under 50 staff, `mid` 50 to 1,000, `large` 1,000+, `public` for public sector and research institutes, `recruiter` when the client is not named. Put the headcount in `staff` ("~30", "28,000 (group)") and where it comes from in `staff_source`. **A headcount is a fact with a source** (changed 2 Oct 2026: a run wrote Quantum-Systems as about 400 from a search summary, it has about 1,600, and that moved the salary ask by about EUR 5k). The draft fills all three from `companies/` when an earlier run stored them. Otherwise take the number from the company's own site, its LinkedIn company page (`company_linkedin` on a LinkedIn row) or the posting, and name that in `staff_source`. Never take it from the summary line of a web search. When you cannot find it, leave `staff` and `size_class` empty: no ask line is better than one built on a guess. `write_pack.py` stores a sourced headcount in `companies/` for the next run. When the posting states no salary, `write_pack.py` prints an `Ask for:` line from the candidate's own table in `scripts/salary.py`. Never put that figure in `salary`; `salary` is only what the posting says.

**Find the employer's own posting.** For every job you intend to send, the `apply_url` must be the employer's own page or their ATS page whenever one exists. He opens that link and applies there. The aggregator or BA copy goes into `fallback_url`.

- BA jobs: start from `employer_site`, look at the careers page and where its apply links point, then try the ATS patterns with a slug from the company name, then search the title in quotes plus the company. If nothing resolves, `apply_url` is the employer's careers page and `ba_url` is the arbeitsagentur link, and say in `gaps` that the original is on the BA behind a captcha.
- LinkedIn jobs: the same search from the company name. If the employer's copy cannot be found, the LinkedIn URL is an acceptable `apply_url`. Always keep `linkedin_url` filled, he uses it for the referral approach.
- XING jobs: `apply_url` comes with the row when the posting has an employer link. An empty `apply_url` means the application runs on XING itself, so look for the employer's own posting as for a LinkedIn job.
- A 404 on a careers page is not proof the role is closed. Say "could not verify" unless you saw it marked closed.
- **Dates.** A LinkedIn or XING card date is the day the aggregator listed or re-listed the job, not the day the employer opened it (MEDIFOX DAN: card 7 Sep, employer board 28 Aug; Audatic: cards 7 hours old, on Sonova's board since 12 Aug). Put the listing date in `posted` only when nothing better exists. `write_pack.py` reads the employer board through `scripts/board_date.py` for every job with an employer `apply_url` or `fallback_url`, replaces `posted`, moves the freshness bonus, and prints `REDATED` lines; read them and mention a large gap in `gaps`. When the employer's date is 14 or more days before the listing date, the email says `RELISTED` on that job. When only the job board's date is known, the email says so. A job whose `apply_url` is a job board copy is marked in the email and counted in its last line, so find the employer's own posting whenever one exists. This only works when you found the employer's own URL, which is one more reason section 3 matters. `scripts/deepdive.py <apply_url> "<title>"` shows the whole board with dates when you want to see the hiring wave.

Unreadable postings. A job whose description cannot be read anywhere is never sent and never rejected, because nobody read it (changed 2 Oct 2026: three such jobs were sent that day, one of them a NATO-nationality role). `write_pack.py` lists every such row in the email under "Could not be read", with its link and the reason, so he can open it himself. It stays unread and comes back in the next run.

Recruiter postings (rows tagged `recruiter`, or BA rows with the flags). Read them like any other job. Put the consultant's name, email and phone into `contact`. Cap at 3 per run.

## 4. Research the company

Look in `companies/` first: `python3 scripts/company_cache.py get "<company>"`. the candidate's local session writes what it learned during research there, and `write_pack.py` writes your note back, so the second time a company comes up the work is already done. Say "cached, checked <date>" in `company_note` when you reuse it and only spend time on what changed.

For every job that passes the fit bar, two or three sentences. What they build and who pays for it. Size and stage. Whether there is a real ML team or he would be the first hire. Anything notable in the last year. Say plainly when you could not find much. Skip this for recruiter postings that hide the client.

## 5. Score, rank, filter

Score fit 0 to 10 against `instructions/PROFILE.md` in the verdict you hand in for each job (section 3). PhD and Doktorand roles are off and were already set aside in `phd_off.json`; count them, do not read them. Every job at fit 7 or higher is sent in full, and there is no cap (the candidate, 2 Oct 2026). A job at fit 6 is one line under "Fit 6, one line each". For each job you send, give the source bonus from instructions/PROFILE.md as a number in `bonus`. `write_pack.py` computes `priority` itself as fit plus the freshness of the final date plus your bonus, so do not add the freshness yourself (a job with no date counts -2, which runs used to forget).

When the reader prints `ALL READ` or `TIME`, run `python3 scripts/verdict.py $SC --draft`. It writes `$SC/shortlist.json` with every job to send already filled from its verdict and from the candidate row (title, location, date, source, fit, band, `lang_line`, the whole `desc`, and `why` set to your reason), and with `rejected`, `borderline` and `also_found` built from the verdicts. Rows tagged `referral` (the companies in `profile.referral_companies`) are read first, sent at fit 5 or higher with `referral: true`, and get +3 priority; see instructions/PROFILE.md.

Before rendering, write `$SC/shortlist.json` and run `python3 scripts/fresh_check.py $SC/shortlist.json`. It lists every candidate posted in the last two days that the shortlist neither sends nor rejects (`UNREAD FRESH` lines) and exits 1 while any remain. Read each one, add it to `jobs` or `rejected`, and run it again until it prints 0. If the run truly cannot finish them, render anyway: `write_pack.py` lists what is left under "Fresh, not read yet" in the email, and say why in the notes.

Then run `python3 scripts/final_check.py $SC/shortlist.json` on the final list. `write_pack.py` runs the same check before it writes anything and refuses to render while a job must go, so a repeat found late can no longer cause a second email. **Do not call `is_repeat` by hand for this.** It prints OK, SECOND OPENING, REPEAT or APPLIED per job and exits 1 when anything must go. Drop every REPEAT, APPLIED, GERMAN and CLEARANCE (the last two mean the description carries a Drop-band German line or a nationality or clearance rule you missed; move the job to `rejected` with that gate), keep every SECOND OPENING and say in `why` what differs from the sent job, then render once. `GERMAN?` means the description has an unclear German line that `lang_line` does not show. Read the sentence it prints. Either move the job to `rejected` with gate `german`, or keep the job and put that sentence in `lang_line`, then run the check again. On 29 Sep a hand-run `is_repeat` dropped two second openings the filter had let through, and the morning email went out twice.

## 6. Write `shortlist.json` and render it

**Render once.** Finish every repeat, second-opening and German decision before you run `write_pack.py`, then render and push once. The email is the file down to the heading `Run details`. The coverage table, the health flags, your notes and the rejected list are below that heading: they stay in the file and in `reports/LATEST.md` and are not mailed. A noon run with no job to send, no fit-6 line and no borderline line is not mailed at all; push it as usual. Every push to `shortlists/` sends an email, and on 29 Sep a re-render sent the morning list twice. If you truly must correct a run after pushing, render again: `deliver.yml` then sends only the added and removed jobs (`scripts/correction.py`), but treat that as a failure to write up in the notes.

**Never hand-write the shortlist markdown. Never create a Gmail draft. The shortlist is never delivered through the connector.** Reading the mailbox is section 8 and nothing to do with this section.

Complete `$SC/shortlist.json`, which `verdict.py --draft` wrote. Fill in, for each job to send: `apply_url`, `priority`, `why`, `gaps`, `company_note`, `size_class`, `staff`, `cv_base`. Then `intro`, `coverage` and `notes`. Leave `desc`, `rejected`, `borderline`, `also_found` and the reading counts alone: `write_pack.py` takes them from the reader's log and from `verdicts.json`, and replaces whatever stands there. The schema is printed by `python3 scripts/write_pack.py --schema`. The fields that need care:

- `band`: `A` or `B` per `instructions/PROFILE.md`. `lang_line`: the exact sentence from the posting, or "no language line in the posting". For a row that carries `german_decide`, `lang_line` must quote one of those sentences.
- `referral`: `true` for roles at a referral company. They render in their own block at the top.
- `apply_url`, `fallback_url`, `employer_site`, `linkedin_url`, `xing_url`, `ba_url`: see section 3.
- `salary`: the band the posting states, in the posting's own numbers, such as `EUR 90-120k` or `bis zu 80.000 EUR`. Leave it empty when the posting states nothing, and it usually states nothing. About one advert in six carries a band. Take it from the row's `salary` field when the collector supplied one (StepStone, Personio and the odd Ashby board fill it), otherwise from the text. A XING row carries XING's own estimate in `salary_estimate`: that is not a salary the posting states, so never copy it into `salary` and never show it. Add the condition in the same string when there is one, as in `EUR 85-160k, the US range` or `EUR 60-80k plus VSOP`. **Never estimate a band and never carry one over from a similar role.** An invented number is worse than no number, because he would negotiate against it.
- `desc`: the description text as the readers printed it, verbatim. The readers already removed perk sentences and diversity boilerplate (`scripts/trim_desc.py`); everything else is there. This is what his local session works from, so do not summarise it.
- `cv_base`: which of his four base CVs fits the role. `CV` for computer vision and general ML engineering, `LLM` for LLM and RAG systems, `Agentic` for agents and voice, `Res` for research roles.
- `why`, `gaps`, `company_note`: plain sentences tied to his real work.
- `coverage`: one row per source in section 2, no exceptions, counts from the collector logs and the filter output. `repeats_skipped`, `applied_skipped`, `phd_set_aside` from the same output. The reading counts (`candidates`, `read_full`, `left_unread`, `unread_by_source`, `no_text`, `remembered`) are filled by `write_pack.py` from the reader's log; whatever you write there is replaced. Fill these yourself: `rejected_before` is the count from the filter output; `german_dropped` is the filter's count plus the `fetch_desc.py` count; `title_dropped` is the triage count. `minutes` is filled by `write_pack.py` from the clock. Unread rows are not lost, they come back next run until they leave their source's window, and LinkedIn's window is 24 hours, so a strong LinkedIn row left unread twice is gone. Read LinkedIn rows before older rows from sources that will still carry them tomorrow.
- `source` values: `Bundesagentur`, `ATS/<kind>`, `linkedin`, `xing`, `stepstone`, `talent.com`, `arbeitnow`, `careers`, `web`.
- `rejected`: every job you read and dropped, with fit, the single reason, and `gate`: one of `german`, `clearance`, `years`, `phd`, `non_software`, `lead`, `field`, `closed`, `repeat`, `unpaid`, `no_text` (instructions/PROFILE.md, "When to reject"). Software skills are never a gate. A rejection without a valid gate is shown in the email as borderline.
- `borderline`: jobs you read that fail no gate but would score 5, with `url` and one line on the doubt in `reason`. They are listed in the email for him to decide, and count as read. This section never goes in the email; it exists so the scoring can be audited. When the reason is German or a nationality or clearance rule, quote the posting's sentence in the reason, as in `Drop band: 'Sehr gute Deutschkenntnisse (C1)'`. `scripts/rejected.py` decides from that text whether the job is skipped for the next 14 days.

Then:

    python3 scripts/write_pack.py $SC/shortlist.json

If it prints `REFUSED`, nothing was written. Either the `date` or `slot` in `shortlist.json` differs from what `collect_all.py` recorded in `$SC/run_slot.json` when this run started (set both to the recorded values), or a job in `jobs` was not read in full by `read_next.py` (the `NOT READ` lines name each one and say why: read it and hand in a verdict, or take it out of `jobs`). Then render again.

It reads the description for a stated band and fills `salary` when you left it empty, printing a `SALARY` line for each one it found, and prints `SALARY MISMATCH` when your band and the description's band share no figure, which usually means the advert carries a US range beside a European one. Your reading wins; say in one line what the two bands were. It runs `scripts/check_live.py` on every apply URL and drops any job that is gone, looks up every job in `state/seen.json` and prints `PRIOR SAME ROLE` when the same role was sent before under any company spelling (read those lines; a second send at a higher score needs a sentence in `why` saying what changed, and a third send is a repeat-check bug to write into `notes/`), writes `shortlists/{date}-{slot}.md` with Band A first and Band B second, writes one pack per job into `jobs/<id>.md` with the full description, every link and the prior appearances, writes the same rows as `shortlists/{date}-{slot}.json` and rebuilds `jobs/index.json`, updates `companies/<slug>.json`, and appends `state/seen.json` with the pack path and priority. Read the rendered file once. If something is wrong, fix `shortlist.json` and render again; do not edit the markdown.

If nothing passes, the JSON has an empty `jobs` list and the render says so. A two-job email is a good email. Never lower the bar to fill slots.

## 7. Save state and push

Add any newly confirmed board to `instructions/COMPANIES.md`, with the slug you tested in this run. A slug you did not test is worse than no entry.
A `BOARD DEAD` line in the health output names a board that has answered an error for 3 runs, and again every tenth run. Act on it in the same run: open the company's careers page, and either correct the slug or kind on its `instructions/COMPANIES.md` line, or change the line's kind to `dead`, which retires the slug from the collector. A `BOARD EMPTY` line needs the same check once; a board that is genuinely empty stays as it is.

Write run notes only when a future run needs them, to `notes/run-notes-{date}.md`. A source that broke, a trap in a board, a company to avoid. Keep them short. Nothing dated goes into `instructions/COMPANIES.md` or this file.

Commit and push with `python3 scripts/gitsync.py push -A -m "Job radar, {date} {slot}, {n} new"`. It rebases onto `origin/main` first and retries a rejected push, which matters because the laptop pushes into this repo too. Do not use a bare `git push`; a push that loses a race to the laptop is silently dropped and the run's state never reaches GitHub. The push into `shortlists/` is what sends the email; the Action rebuilds `reports/LATEST.md` and mails the newest run. Confirm the Action ran. If the push fails, retry; if the email does not arrive, the fix is on the push and the Action, never a draft.

After the push, run `python3 scripts/archive_run.py $SC`. It uploads the run's working files (the triage list, the batches, the verdicts, the drop files, a compact list of every collected row) as a GitHub Release tagged `run-{date}-{slot}`, so a discard or a verdict can be audited later, and deletes releases older than 90 days. It prints one `archive:` line; copy it into the notes. It never fails the run: `archive: skipped` means the token is not set, `archive: failed` names the error, and both are fine to leave as they are.

## 8. Evening run only: scan the mailbox and update the pipeline ledger

**Switched off on 7 Oct 2026. Every run skips this section.** The routines moved to a new account with no Gmail connector, and the candidate chose to keep only the job emails. Do not try to open Gmail. Leave `pipeline/events.json` and `reports/PIPELINE.md` as they are. The text below is kept for when the scan comes back.

The morning and noon runs skip this section. The evening run always does it, even when the shortlist was empty.

`pipeline/events.json` is the application ledger and `reports/PIPELINE.md` is its rendered form. Between them they hold every application, rejection, interview and assessment with the date on the email that proved it. Two things depend on this being current. The laptop session reads `reports/PIPELINE.md` to know where the hunt stands, and the summary emails are computed from `events.json`, the weekly one by the `weekly-report` routine on Saturday (see `docs/WEEKLY.md`) and the monthly one by a GitHub Action on the last evening of the month. A skipped scan makes those numbers wrong.

**Gmail is read-only here.** Use `search_threads` and `get_thread` and nothing else. Never create a draft. Never send mail. The draft step was removed on 25 August 2026 because it left an unwanted draft in his mailbox twice a day for a month, and it must not come back. Delivery is still the Action on a push, never the connector.

### 8.1 Work out what is new

Read `reports/PIPELINE.md`. Its header carries `Last scan`. Everything since that date is what you are looking for. If the file is missing, render it with `python3 scripts/pipeline.py render` and scan the last 7 days.

### 8.2 Search

Three sweeps, with `after:` set to the last scan date. These queries were checked against this mailbox on 12 September 2026 and they are the ones that find real mail rather than job alerts.

Confirmations:

    after:YYYY/MM/DD ("received your application" OR "successfully submitted" OR "Thanks for applying" OR "Thank you for applying" OR "Bewerbung ist angekommen" OR "application was sent" OR "confirm receipt" OR "Confirmation of your application" OR "application has been received" OR "Ihre Bewerbung")

Rejections:

    after:YYYY/MM/DD (unfortunately OR "not moving forward" OR "other candidates" OR "ideal fit" OR regret OR leider OR Absage OR "has been filled" OR "nicht berücksichtigen" OR "move forward with" OR "decided to proceed with" OR "anderen Kandidaten")

Interviews and assessments:

    after:YYYY/MM/DD (interview OR "intro call" OR shortlisted OR assessment OR Vorstellungsgespräch OR "Online-Assessment" OR Einladung OR "next stage" OR "next steps" OR "invite you")

Applications he sent by email himself. Added 21 September 2026. An ATS confirms receipt, a company
mailbox usually does not, so those applications were invisible to the three sweeps above and never
reached the ledger at all. His sent mail is the only record they have.

    in:sent after:YYYY/MM/DD (Bewerbung OR application OR applying OR Lebenslauf OR "cover letter" OR "motivation letter" OR CV)

Read the ones addressed to a company rather than to a person he already knows, and record one
`applied` event each, dated the day he sent it, with the address he wrote to in `--evidence`. GAF
Geospatial is the live example: applications go to recruiting@gaf.de and nothing comes back. Skip a
reply in a thread that is already on the ledger, and skip mail to a recruiter who approached him.

Add this to every sweep, or the results fill with job alerts and newsletters:

    -subject:"Job radar" -from:linkedin.com -from:jobagent.stepstone.de -from:e-fellows.net -from:deeplearning.ai -from:alignerr.com -from:alignerrcore.com -from:coursera.org -from:jobleads.com -from:zenjob.com -from:crowdgen.com -from:stackoverflow.email -from:studysmarter.de -from:vaia.com -from:efinancialcareers.com -from:efinancialcareers.de -from:instaffo.com -from:germanpedia.com -from:economictimesnews.com

Two exceptions to the exclusions. `jobs-noreply@linkedin.com` sends "your application was sent to X", which is a real confirmation, so read those before excluding LinkedIn wholesale. And `info@email.stepstone.de` relays employer rejection feedback, which is real, while `info@jobagent.stepstone.de` is only alerts.

Use `THREAD_VIEW_MINIMAL`. The subject and the snippet decide most of them. Fetch the full thread with `PLAIN_TEXT` only when the snippet cuts off before the verdict, and never on a mail over about 40 KB, because those are newsletters and they will flood the run.

### 8.3 Classify

One event per thing that actually happened.

- A confirmation of receipt is `applied`, dated the day it arrived. So is an application he sent by
  email himself, dated the day he sent it.
- "we decided to move forward with other candidates", "isn't an ideal fit", "unfortunately", "leider", "Absage" is `rejected`. So is "we've decided to move forward with candidates whose experience aligns more closely" (Autonomous Teaming, 28 Sep 2026), which has no "unfortunately" and no "other candidates" in it and was only found because the interview sweep matched "next steps".
- An invitation to talk, a booked call, or being shortlisted is `interview`.
- An online test, a timed technical, or a take-home is `assessment`.
- "The position has been filled" or a pulled posting is `closed`, because it is not a decision about him.
- An offer is `offer`.

Not events, do not record them. A "please be patient, we have a lot of applications" holding mail. A job alert. A newsletter. A recruiter cold approach he never applied to. A careers-portal "welcome, complete your profile" mail.

Be careful with two shapes that look like the opposite of what they are. A mail whose subject is "Thank you for your application" is very often a rejection, so read the body. And a mail that opens "We were impressed with your application" is usually followed by "unfortunately".

### 8.4 Record

One call per event. The script appends, refuses exact duplicates, and re-renders `reports/PIPELINE.md` itself.

    python3 scripts/pipeline.py add --key lucid-labs --type interview \
        --company "Lucid Labs" --role "AI Engineer (m/f/d)" --date 2026-09-10 \
        --evidence "matthew.goddard@lucidlabs.msg.join.com, 'Next steps'" \
        --note "Intro call booked for 2026-09-15 09:00 CEST"

`--key` is the stable slug for the application and it is the one thing to get right. Grep `pipeline/events.json` for the company first and reuse the key that is already there, otherwise the rejection lands as a separate application from the one it answers and both the counts and the days-to-answer go wrong. Use a new key only for a company he has genuinely applied to twice, and make the difference visible, as in `actai-senior`.

`--evidence` is the sender plus the phrase that decided the classification. It is what lets a later session check the call instead of trusting it.

`--track side` is for logistics and retail applications. They stay out of the headline counts.

An `applied` event also writes `state/applications.md`, which the radar reads to skip jobs he already
applied to. It skips on company and title together, so the title is what keeps a different role at
the same company on the shortlist. For every `applied` event:

- `--role` is the job title exactly as the mail or the posting gives it, gender tag and all. Never
  a summary and never a guess.
- If the mail does not name the role, look for it in `state/seen.json` and `jobs/` by company and date.
  If it is still unknown, leave `--role` empty. The script then records the event, writes no row,
  and prints a line saying so. Put that line in the run report.
- `--location` is the city from the posting, when known.

The script stamps his existing row when it finds one for that job, and keeps his title. Otherwise
it adds a row marked `not researched, found in the mailbox`. If it prints that a title matches
more than one row, put that line in the run report too.

Never edit `pipeline/events.json` or `reports/PIPELINE.md` by hand. Every number in them is computed.

### 8.5 Stamp and push

Stamp the scan date even when nothing was found, or the next run re-reads the same mail.

    python3 scripts/pipeline.py scanned --date YYYY-MM-DD
    python3 scripts/gitsync.py push pipeline reports/PIPELINE.md reports/INTERVIEWS.md state/applications.md -m "Pipeline scan, YYYY-MM-DD, {n} new events"

Then say in the run report how many events were added and what they were. Pushing `pipeline/` does not send an email; only `shortlists/` does that.

## Rules

Be honest about fit. Two real matches beat eight padded ones, and a wrong 9 costs him a morning.

Never apply to anything. Never fill in a form, never send anything to an employer. You find and rank, he applies.

**Never change code during a run** (the candidate, 3 Oct 2026). Do not edit, create or delete anything under `scripts/`, `tests/`, `config/` or `.github/`, and never commit such a change. When a script misbehaves, work around it in this run's data only: correct the field in `shortlist.json` by hand and say so in the notes. Then add an entry to `docs/CODE_ISSUES.md` with the date and slot, the script, what happened with the exact output, the job it affected, and what you did instead. the candidate fixes the code in his own sessions. On 3 Oct 2026 the morning run patched `scripts/board_date.py` and pushed it without running the tests.

Never invent a posting date, a salary, a requirement, or a language line. If you do not know, say you do not know.

Read Gmail only, and only in section 8. Never create a draft and never send mail from the connector. Delivery of the shortlist is the GitHub Action on a push into `shortlists/`, and delivery of the weekly and monthly summaries is the Actions on their own schedules.

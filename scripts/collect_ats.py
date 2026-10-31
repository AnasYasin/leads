#!/usr/bin/env python3
"""Poll every ATS board in instructions/COMPANIES.md, including the documented exceptions."""
import json, os, re, sys, time, urllib.request, urllib.error, concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jobid import PLACE, fold
from textclean import html_to_text, join_html

# RADAR_KEEP_RAW=1 keeps each description's source HTML beside the cleaned text, as `desc_raw`,
# so a cleaning change can be compared with the old output on the same input. Off in a run.
KEEP_RAW = bool(os.environ.get("RADAR_KEEP_RAW"))

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

BOARDS = [
    # Added 26 Sep 2026 morning. Same failure as dexter-health and microagi below: all three of
    # these were documented in instructions/COMPANIES.md and never wired in here, so they went unpolled.
    # imfusion had been in instructions/COMPANIES.md since 31 Aug and was never once polled by this collector;
    # its Research Engineer - Machine Learning & Medical Imaging was the top pick of this run and
    # arrived through talent.com with no date instead of off the board with a createdAt.
    # Since 29 Sep 2026 every `kind | slug | name` line in instructions/COMPANIES.md is polled too (see
    # _from_companies_md below), so a board only needs adding here when it wants a comment.
    ("personio", "imfusion", "ImFusion"),        # Munich medical image computing, 4 positions
    ("greenhouse", "smartlyio", "Smartly"),      # 79 jobs; AI Platform team posts per city
    ("join", "ai-coustics", "ai-coustics"),      # Berlin speech enhancement SDK, audio ML
    # Added 27 Sep 2026 morning from the funded-startup sweep, slug fetched by hand against
    # this exact host first: 15 jobs over 3 pages. Munich acoustic AI, USD 3M pre-seed, builds
    # a "Large Acoustic Model" for non-speech audio plus the OmniDome counter-drone system.
    # Only the ML Engineer seat is scoreable and it sits on page 3, so this board is also the
    # reason the join pagination bug below was found. Their careers page said "hiring paused"
    # on 27 Sep while every join posting still answered 200 — check before scoring the board.
    ("join", "omnisent", "Omnisent"),
    # Added 25 Sep 2026 morning. Every slug below was fetched by hand against the exact host
    # this collector uses before being added, and the job counts are from that fetch.
    # lawzero: Yoshua Bengio's AI-safety non-profit, 15 jobs, 9 of them Berlin or Berlin/Montreal.
    # It is also the unnamed client behind the European Tech Recruit adverts of 24 Sep, so match
    # its Senior ML Research Developer / Scientist against those before sending either again.
    ("greenhouse", "lawzero", "LawZero"),
    # xheroncom: Berlin, Service-as-Software for short-term rentals, 5 roles. Note the `com`
    # suffix on the slug; plain `xheron` is not the board. Their AI Harness Engineer is the
    # role already sent on 15 Sep under its old title, so match on the join id, not the title.
    ("join", "xheroncom", "xHeron Solutions"),
    # clera: Munich/Zurich/San Francisco, agent systems and post-training. 273 postings and only
    # three ML seats, so this board needs hard title filtering.
    ("ashby", "clera", "Clera"),
    # manex: Munich, agentic platform over manufacturing data, Lightspeed and BlueYard. 10 jobs.
    # `manexai` 404s on Ashby and Greenhouse; the slug is the bare `manex`.
    ("ashby", "manex", "Manex AI"),
    # bowatt: Munich, agentic requirements engineering for manufacturing, EUR 500k+ ARR before
    # raising. 10 jobs. The "(German-speaking)" tags sit on the commercial roles only.
    ("ashby", "bowatt", "BoWatt"),
    # greenpeak: Munich PE house, Infra Investment Team building a shared AI capability for
    # portfolio companies. 4 positions on the `.de` Personio host, only one of them senior.
    ("personio", "greenpeak", "GREENPEAK Partners"),
    # Berlin startups
    ("ashby", "n8n", "n8n"), ("ashby", "deepsetai", "deepset"),
    ("ashby", "mirelo", "Mirelo"), ("ashby", "voize", "Voize"), ("ashby", "peec", "Peec AI"),
    ("ashby", "langfuse", "Langfuse"), ("ashby", "climatiq", "Climatiq"),
    ("ashby", "sensmore", "sensmore"), ("ashby", "almetra", "Almetra"),
    ("ashby", "telli", "telli"), ("ashby", "cortea", "Cortea"),
    ("personio", "workist-gmbh", "Workist"), ("personio", "apheris", "Apheris"),
    ("personio", "vara", "Vara"), ("greenhouse", "parloa", "Parloa"),
    ("personio", "merantix", "Merantix"), ("ashby", "prior-labs", "Prior Labs"),
    ("personio", "dida", "dida"), ("greenhouse", "doctolib", "Doctolib"),
    ("ashby", "qontext", "Qontext"), ("ashby", "finmid.com", "finmid"),
    ("greenhouse", "atolls", "Atolls"), ("greenhouse", "solarisbank", "Solaris"),
    # Added 25 Aug 2026 evening, read off their own Ashby board after the Cherry Ventures
    # Getro sweep surfaced the company. Note the `-de` suffix; plain `integral` 404s.
    ("ashby", "integral-de", "Integral"),
    # Rest of Germany
    ("ashby", "hawk", "Hawk"), ("ashby", "sereact", "Sereact"),
    ("ashby", "mindpeak", "Mindpeak"), ("ashby", "orbem", "Orbem"),
    ("ashby", "alephalpha", "Aleph Alpha"), ("ashby", "tacto", "Tacto"),
    # Moved Greenhouse -> Ashby, corrected 29 Aug 2026 morning after `greenhouse/blackforestlabs`
    # started answering 404. The Ashby slug is hyphenated; plain `blackforestlabs` 404s there too.
    ("ashby", "black-forest-labs", "Black Forest Labs"),
    ("personio", "wandelbots", "Wandelbots"), ("personio", "twaice", "TWAICE"),
    # Added 5 Sep 2026 evening. Found by tracing a talent.com card back to the company board.
    # The feed carries metadata only, no description body, and most rows are Pflichtpraktika --
    # filter on `recruitingCategory` == "Fulltime Role" before scoring.
    ("personio", "synapticon", "Synapticon"),
    ("greenhouse", "konux", "KONUX"), ("ashby", "spaitial", "SpAItial"),
    ("ashby", "arago", "Arago"), ("personio", "ottonova", "ottonova"),
    ("personio", "stark", "STARK"), ("personio", "spread-gmbh", "SPREAD"),
    ("greenhouse", "arxroboticsgmbh", "ARX Robotics"),
    ("ashby", "cosuno", "Cosuno"), ("ashby", "moss", "Moss"),
    ("ashby", "mazehq", "Maze"), ("recruitee", "qualifyzegmbh", "Qualifyze"),
    ("ashby", "preply", "Preply"), ("lever", "finn", "FINN"),
    # 29 Oct 2026: the slug is `advasolutions`, read off advasolutions.com/karriere (8 positions).
    # `advastore` had answered 404 on every one of the 30 recorded runs.
    ("personio", "advasolutions", "Advasolutions"), ("personio", "super-ai", "super.AI"),
    ("personio", "deeploi", "deeploi"), ("greenhouse", "inceptive", "Inceptive"),
    ("smartrecruiters", "ScalableGmbH", "Scalable Capital"),
    ("recruitee", "synera", "Synera"), ("personio", "holidu", "Holidu"),
    ("ashby", "se3", "SE3 Labs"), ("recruitee", "netconomy", "NETCONOMY"),
    ("ashby", "finto", "Finto"),
    # Confirmed by hand 15 Aug 2026 morning, each read off a live apply link, not guessed.
    ("personio", "credium", "credium"),          # geospatial CV, Augsburg, 5 jobs
    ("ashby", "avelios-medical", "Avelios Medical"),  # note the `-medical`; plain `avelios` 404s
    ("personio_html", "alpas-gmbh", "Alpas"),    # slug is `alpas-gmbh`; /xml 404s, HTML board works
    # geospatial
    ("personio", "ororatech", "OroraTech"),
    # 29 Oct 2026: constellr left Personio (404 on all 30 recorded runs). constellr.com links
    # job-boards.eu.greenhouse.io/constellrgmbh, 27 jobs, served by boards-api like JetBrains.
    ("greenhouse", "constellrgmbh", "constellr"),
    ("pinpoint", "careers.osapiens.com", "osapiens"),
    ("greenhouse", "isaraerospace", "Isar Aerospace"),
    # larger
    ("ashby", "deepl", "DeepL"), ("greenhouse", "celonis", "Celonis"),
    ("greenhouse", "helsing", "Helsing"),
    ("greenhouse", "ubiquiti", "Ubiquiti"), ("greenhouse", "scaleai", "Scale AI"),
    # DHL Data & AI, Bonn. Added 25 Aug 2026 at the candidate's request — he has an inside contact
    # there, so anything this board returns is worth flagging even at a middling fit.
    ("avature", "dhlconsulting", "DHL Data & AI"),
    # Added 27 Aug 2026 evening. Both were found by a site-scoped Greenhouse search, not by any
    # board sweep, and both had roles that passed the fit bar the same run — which is the argument
    # for polling them. Filter hard on SumUp: 394 jobs, only three are ML and one of those wants
    # 8+ years. SoundCloud's board is small (14) but carries evergreen postings, so read
    # `first_published`, not `updated_at`.
    ("greenhouse", "sumup", "SumUp"), ("greenhouse", "soundcloud71", "SoundCloud"),
    # Added 30 Aug 2026 morning. All four of that run's shortlisted roles came from these three
    # boards and none was being polled before — they were found by a site-scoped Ashby/Greenhouse
    # web search, which is exactly the gap polling is meant to close. Each slug was confirmed
    # returning jobs before being written down.
    ("ashby", "almedia", "Almedia"),      # Berlin adtech, bootstrapped, 53 jobs, growing its ML org
    ("ashby", "cohere", "Cohere"),        # enterprise foundation models, Berlin office, 146 jobs
    # Air Apps posts the same role across ~10 cities; the body usually says onsite Lisbon regardless
    # of the city in the title, so read the location out of the description, not the tag.
    ("ashby", "airapps", "Air Apps"),     # 498 jobs, heavily duplicated across locations
    # documented exceptions
    ("teamtailor_feed", "ml6", "ML6"), ("teamtailor_feed", "hedvig", "Hedvig"),
    # Added 3 Sep 2026 evening. Both were reached through aggregators whose posting dates were
    # wrong, and polling the board directly is what fixed them — see instructions/COMPANIES.md.
    # Shine's feed is the JSON-feed shape (`items` + `date_published`), so `teamtailor_feed`.
    ("teamtailor_feed", "shine", "Shine"),
    # Added 6 Sep 2026 evening, all three read off a live board, not guessed.
    # NET CHECK: only `nc-group` works. `net-check`, `netcheckgmbh` and `ncgroup` return nothing,
    # and `netcheck.jobs.personio.de` is a DIFFERENT company (Madrid marketing) that answers 200
    # with a valid feed, which is exactly how a wrong slug fails silently.
    ("personio", "nc-group", "NET CHECK / NC GROUP"),
    # Buddywise: industrial-safety computer vision, Berlin/Stockholm, remote across DE and SE.
    # JSON-feed shape, so `teamtailor_feed`. Their own host jobs.buddywise.co serves the same feed.
    ("teamtailor_feed", "buddywise", "Buddywise"),
    # Makersite: makersite.io/careers/ 301s straight to the Recruitee board, which is how the slug
    # was found. Only 2 offers, but full description/requirements/published_at.
    ("recruitee", "makersitegmbh", "Makersite"),
    ("personio", "codecentric", "codecentric"),
    ("recruitee_custom", "career.quantum-systems.com", "Quantum-Systems"),
    ("personio_html", "enocean", "EnOcean"),
    # Added 2 Sep 2026 evening; both shortlisted that run, both slugs confirmed live before
    # being written down. Note the split: Legalhero serves /xml (6 positions), Briink does not
    # — briink.jobs.personio.de AND .com/xml both 404, only the HTML board answers, so it has
    # to be personio_html. Briink reached this run through the Merantix AI Campus Getro board,
    # which means it arrived a day late and via a middleman; polling it directly fixes that.
    ("personio", "legalhero", "Legalhero"),      # Berlin legal-tech, ~60-90 people, AI seat
    ("personio_html", "briink", "Briink"),       # Berlin AI Campus, ESG agents, EUR3.85M seed
    ("breezy", "remerge", "Remerge"),
    # Confirmed by hand 24 Aug 2026 morning, both read off a live join.com board.
    ("join", "datacept", "Datacept"),        # RF/SIGINT ML, Hamburg, pre-seed, 1-10 people
    ("join", "kausableai", "kausable"),      # causal world models, Heidelberg, EUR12M seed
    # Added 24 Aug 2026 evening, both confirmed off a live join board rather than guessed.
    ("join", "lucidlabs", "Lucid Labs"),     # Berlin agent studio for the Mittelstand, 5 jobs
    # dexter health was documented in instructions/COMPANIES.md on 18 Aug and never added here, so it went
    # unpolled for six days and its roles kept arriving late through talent.com instead.
    ("join", "dexter-health", "dexter health"),
    # Added 26 Aug 2026 morning. Both were found as a talent.com row and then read at source on
    # the company's own board, which is the Tier 2 path in section 3 of instructions/PROMPT.md. Both slugs
    # were confirmed to return real jobs before being written here.
    ("personio", "peter-park", "Peter Park"),   # note the hyphen; `peterpark` is not the board
    ("join", "zalionai", "Zalion"),             # note the `ai` suffix; `zalion` 404s everywhere
    ("teamtailor", "aignostics", "Aignostics"),
    # 29 Oct 2026: microagi moved onto Ashby (11 jobs, 6 of them Munich). The old careers page
    # parser (`jsbundle`) had read 0 jobs for 30 runs. Its board link is on every role on microagi.ai.
    ("ashby", "microagi", "microagi"),
    # added 8 Aug 2026 morning
    ("ashby", "hipeople-official", "HiPeople"),
    ("ashby", "poolside", "poolside"),
    ("workable", "enjins", "Enjins"),
    ("hirehive", "luma-vision", "LUMA Vision"),
    # added 9 Aug 2026 morning
    ("greenhouse", "bluefishai", "Bluefish"),
    # Added 9 Aug 2026 evening. JetBrains has been supplying a steady stream of ML/research
    # roles, but every one of them reached us through the Bundesagentur, one at a time and
    # weeks late, because their board was never polled. The board lives on the EU host
    # (job-boards.eu.greenhouse.io) and boards-api.greenhouse.io serves it fine: 93 jobs.
    ("greenhouse", "jetbrains", "JetBrains"),
    # Added 11 Aug 2026 morning. Medical-imaging AI for prostate cancer, Berlin office. Reached
    # from an Indeed search result, not a board sweep: nucs.ai/careers 404s and the only clue to
    # the ATS is the string "recruitee" in the homepage markup. Standard host works, 12 offers.
    ("recruitee", "nucsai", "Nucs AI"),
    # Added 12 Aug 2026 morning. Berlin earth-observation company, ~130 people, founded 2018,
    # >EUR 72M raised. Their Senior ML Engineer role is the closest thing to his SPHF geospatial
    # CV work the radar has surfaced: PyTorch Lightning, GDAL, Rasterio, GeoPandas, STAC. Found
    # through a general geospatial web search, not a board sweep — the Personio slug carries the
    # `-gmbh` suffix and plain `liveeo` 429s/404s, so take it from here rather than guessing.
    # Warning: their Governmental Solutions roles require eligibility for a German security
    # clearance (Sicherheitsüberprüfung), which is a hard filter for non-EU nationals — read that
    # line on every role from this board before scoring it.
    ("personio", "liveeo-gmbh", "LiveEO"),
    # Added 14 Aug 2026 morning. Munich reality-capture company (VLX scanners + IVION platform),
    # $85M raised this month, reached from the funding sweep rather than a board poll. Their IVION
    # Data Foundation team does semantic segmentation and scene understanding on point clouds and
    # 360-degree imagery at petabyte scale — the closest geospatial CV work in the file after
    # LiveEO. Board is on the EU Greenhouse host but boards-api serves it fine, same as JetBrains.
    # Scoring note: their "Lead ML Engineer - Geometric Spatial AI" is lead-level, do not send it.
    ("greenhouse", "navvis", "NavVis"),
    # Added 16 Aug 2026 morning, both read off a live apply link rather than guessed.
    # All Your BI: Rotterdam remote-first data agency, 60+ people across Europe, hiring their
    # first AI/GenAI lead. Reached through talent.com; the Recruitee slug is the bare company
    # name and serves 3 offers with real `created_at` dates, which is exactly what talent.com's
    # own age field does not (see the shortlist note for 16 Aug).
    ("recruitee", "allyourbi", "All Your BI"),
    # botario: NFON's Bremen conversational-AI subsidiary (spin-off of JUST ADD AI, acquired by
    # NFON 1 Aug 2024). This is where NFON's ML roles actually originate — the 15 Aug run reached
    # their ML Engineer through join.com one job at a time. `/xml` answers 200 with **zero bytes**
    # on both .de and .com, so the normal `personio` type looks alive and returns nothing; the
    # HTML board serves all 5 jobs. Use personio_html, not personio.
    ("personio_html", "botario", "botario (NFON)"),
    # Added 17 Aug 2026 evening, both read off a live API response rather than guessed.
    # nicos: secure managed WANs for German Mittelstand, Münster, part of the Xantaro Group. The
    # slug carries the `-ag` suffix — plain `nicos` 404s on Personio. Reached through the
    # Bundesagentur, and the board is the better copy: BA reported the AI Agent Engineer role as
    # first published 17 Aug while the board's `createdAt` says 10 Aug, so take dates from here.
    # Mostly sales and network roles; their AgentAI platform is the thing worth watching.
    ("personio", "nicos-ag", "nicos AG (Xantaro Group)"),
    # Machine Learning Reply: Reply's ML consultancy, Munich/Berlin/Vienna, 13 offers with real
    # dates. Content matches well on paper (agentic AI, LangChain/LangGraph, RAG, MLOps) but
    # **every role mandates C1 German and says so explicitly**, so it will pass fit almost never.
    # Polled anyway so the aggregator tier stops surfacing these one job at a time.
    ("recruitee", "machinelearningreply", "Machine Learning Reply"),
    # Added 18 Aug 2026 evening, both read off a live API response rather than guessed.
    # Q.ANT: photonic computing spin-off of TRUMPF, Stuttgart/Munich/Austin. Slug needs the `-gmbh`
    # suffix; plain `qant`/`q-ant` are not the board and qant.com's careers page is a JS shell. 18
    # postings with real createdAt dates, but ~90% are photonics/semiconductor hardware — expect one
    # or two hardware-flavoured ML roles at a time (their Senior LLM Algorithm Developer wants
    # silicon-photonics co-design and Mamba/state-space models at 5-7 years, scored 5).
    ("personio", "q-ant-gmbh", "Q.ANT"),
    # Bees & Bears: Berlin climate-fintech (solar, storage, heat-pump financing), reached through the
    # talent.com tier. Their AI roles are observability and first-pipeline data plumbing rather than
    # modelling, but it is a cheap Berlin startup board to keep in rotation.
    ("personio_html", "bees-bears-gmbh", "Bees & Bears"),
    # Added 19 Aug 2026 morning, both read off a live API response rather than guessed.
    # Agile Robots: DLR spin-out building industrial robot arms (force-torque sensing + vision),
    # Munich HQ, 2,300+ people, production in Kaufbeuren. Slug needs the `-se` suffix; plain
    # `agilerobots`/`agile-robots` are not the board. 77 postings with real createdAt dates, ~8 of
    # them AI/robot-learning. Reached through talent.com on 16 Aug one job at a time — polling the
    # board directly is what surfaced the (Senior) ML Research Engineer Robotics role. Two things
    # worth knowing: the board is English with **no German requirement on the ML roles**, which is
    # rare in this list, and their (Senior) ML Research Engineer Robotics says outright "You don't
    # need a robotics background", so do not auto-reject their robotics titles on a missing
    # robotics background. Not a startup, so no small-employer bonus.
    # MOVED, 25 Sep 2026 evening: the Personio board `agile-robots-se` now returns zero rows.
    # Read off the apply button on agile-robots.com/en/career/: they are on Greenhouse EU under
    # `agilerobotsse`, 58 postings, served fine by boards-api.greenhouse.io (same as JetBrains above).
    # The Greenhouse feed carries updated_at and the full description, so unlike the old Personio XML
    # it needs no per-job fetch and the date can be trusted.
    ("greenhouse", "agilerobotsse", "Agile Robots SE"),
    # Dunia Innovations: Berlin deep-tech, AI + a self-driving robotic lab for electrocatalyst
    # discovery (green hydrogen, CO2 conversion). $11.5M/EUR 10.6M seed led by Elaia and redalpine.
    # 13 postings. The /xml carries `yearsOfExperience` but **no jobDescriptions**, so titles and
    # year bands come from the feed and the description needs a fetch of
    # `dunia.jobs.personio.com/job/<id>?language=en`. Their ML Researcher, Representation Learning
    # is his exact thesis topic but is banded 7-10 years and wants a PhD; the mid-level opening to
    # wait for is the next ML Engineer role.
    ("personio", "dunia", "Dunia Innovations"),
    # Added 28 Aug 2026 evening, all three read off a live API response rather than guessed.
    # EMPIT: Berlin deep-tech (founded 2015, 43 people), non-invasive magnetometry inspection of
    # buried pipelines. Reached through talent.com and read at source. 21 positions, mostly
    # hardware and inspection-technician roles. Their one ML role is an evergreen posting dated
    # March 2025 — take dates from this feed, never from the talent.com card, which reported the
    # same posting as three days old.
    ("personio", "empit", "EMPIT"),
    # WeSort.AI: Würzburg, AI waste analysis and automated material sorting, ~$11.5M raised.
    # Their ML Engineer - Foundation Models role is the best content match the radar has found in
    # weeks (SSL pretraining of ViTs, FSDP/DDP, linear/k-NN probing eval suite, ONNX/TensorRT edge
    # distillation) but requires fluent German, so expect to score high and send nothing until a
    # role without that line appears.
    ("join", "wesort", "WeSort.AI"),
    # Added 5 Sep 2026 evening. Berlin medtech (VICORDER cardiovascular diagnostics) extending
    # into data/AI. Surfaced by the new arbeitnow sweep, then confirmed on their own join board.
    ("join", "80beatsmedicalcom", "80 Beats Medical"),
    # ICEYE: SAR satellite constellation, HQ Espoo, 1000+ people. Big healthy board. Read the
    # clearance line on every German role — their Forward Deployed AI Engineer (Munich) needs a
    # German Sicherheitsüberprüfung Ü1/Ü2/Ü3, NATO clearance AND native-level German. The Espoo
    # ML/AI roles carry no such condition and are the ones worth reading.
    ("ashby", "iceye", "ICEYE"),
    # Added 30 Aug 2026 evening. All four confirmed returning jobs before being written down.
    # MOTOR Ai: Berlin, Level 4 autonomous driving on an explainable-AI stack, $20M seed Jul 2025.
    # The radar has been seeing this company through the Bundesagentur only, which is why its
    # AI/ML Engineer arrived twice — once on 24 Aug and again tonight off this board. Polling the
    # board directly puts it through the repeat check like everything else. 5 jobs.
    ("join", "motor-ai", "MOTOR Ai"),
    # RobCo: Munich, modular autonomous industrial robotics, hardware plus software plus AI.
    # 41 jobs across Munich and Austin; their Senior Applied AI Engineer is Europe-remote.
    ("ashby", "robco", "RobCo"),
    # Mercanis: Berlin, AI procurement and supplier management, $19.9M Series A. 48 positions,
    # but note their only Agentic AI Engineer seat is listed under a Spain office and the XML
    # carries no descriptions at all, so every role needs a follow-up fetch to be scored.
    ("personio", "mercanis", "Mercanis"),
    # AUTO1 Group: Berlin, Europe's largest used-car platform, and it runs a standing computer
    # vision team on the production imaging pipeline. Big board — 532 postings, mostly operations
    # and sales across Europe, so filter hard. Their Senior Computer Vision Engineer was confirmed
    # closed at source on 30 Aug 2026; this entry exists to catch the repost.
    ("smartrecruiters", "Auto1", "AUTO1 Group"),
    # Added 3 Sep 2026 morning. GlassFlow: Berlin data infrastructure for AI agents (Tares feeds
    # agents correlated data, Rius traces and debugs them), $5.9M total, $4.8M seed led by Upfront
    # Ventures Oct 2024. Reached the radar as a talent.com card and read at source, which is the
    # Tier 2 path; their own site has no /careers (404) and the board lives on join.com under the
    # slug `getglassflow` — note the `get` prefix, plain `glassflow` is not the board. Confirmed
    # returning 5 visible jobs (7 claimed) before being written here. Their AI Engineer was the
    # top of this run at fit 8.
    ("join", "getglassflow", "GlassFlow"),
    # Added 5 Sep 2026 morning. All four were found through the arbeitnow JSON API and then read
    # at source on the employer's own board, which is the Tier 2 path in section 3 of instructions/PROMPT.md.
    # Every slug was confirmed returning jobs before being written here.
    ("ashby", "perplexity", "Perplexity"),        # 206 jobs; Berlin postings are real now
    ("greenhouse", "intercom", "Intercom (Fin)"), # 705 jobs; new Berlin R&D hub
    ("greenhouse", "databricks", "Databricks"),   # 5,224 jobs — the biggest board here, filter hard
    ("lever_eu", "pnlfin", "Finom"),              # EU Lever host; `pnlfin` 404s on api.lever.co
]

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{s}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{s}?mode=json",
    # Lever runs a separate EU instance and a slug on it 404s on the .co host. Finom's board
    # (`pnlfin`) lives there — found 5 Sep 2026 morning. Same JSON shape, so it reuses the
    # `lever` parser below; only the host differs.
    "lever_eu": "https://api.eu.lever.co/v0/postings/{s}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{s}?includeCompensation=true",
    "personio": "https://{s}.jobs.personio.de/xml",
    "teamtailor": "https://{s}.teamtailor.com/jobs.json",
    "teamtailor_feed": "https://{s}.teamtailor.com/jobs.json",
    # Teamtailor on a vanity host with no working <slug>.teamtailor.com. Slug is the full host.
    # SLNG, 10 Sep 2026: careers.slng.ai/jobs.json answers, slng.teamtailor.com 404s.
    "teamtailor_custom": "https://{s}/jobs.json",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{s}?details=true",
    "recruitee": "https://{s}.recruitee.com/api/offers/",
    "recruitee_custom": "https://{s}/api/offers/",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=100",
    "personio_html": "https://{s}.jobs.personio.com/?language=en",
    "breezy": "https://{s}.breezy.hr/json",
    # Avature. No JSON feed exists, but unlike most enterprise ATSs the board is rendered
    # server-side, so the plain HTML with a browser UA IS the feed. Added 25 Aug 2026 for
    # DHL. Avature is common across large German employers, so this parser should port to
    # others by slug alone.
    "avature": "https://{s}.avature.net/en_US/careers/SearchJobs/",
    # Pinpoint. The board page itself is a JS shell, but postings.json next to it is the full
    # feed. Found 6 Aug 2026 evening on osapiens, whose careers.osapiens.com/postings/<uuid>
    # url shape is the giveaway for this ATS. `desc` is `description`; `requirements` is a
    # separate field and is often left unpublished, so a short description is not a parse bug.
    "pinpoint": "https://{s}/postings.json",
    # join.com. There IS a public REST endpoint at /api/public/companies/{s}/jobs, but its
    # `pageSize` validator rejected every integer tried (10, 12, 15, 20, 24, 25, 30, 50, 100)
    # while accepting `page=1`, so it is unusable without knowing the magic value. The board
    # page itself carries the whole list in the Next.js hydration payload — same trick as the
    # Getro `__NEXT_DATA__` method in instructions/PROMPT.md — under `initialState.jobs.items`, with a real
    # ISO `createdAt` per job. Found 24 Aug 2026 morning on datacept and kausableai.
    # Worth knowing: talent.com aged the Datacept role at "vor 3 Tagen" when `createdAt` said
    # it was 10 hours old. Trust the board's date over the aggregator's relative string.
    "join": "https://join.com/companies/{s}",
    # HireHive. The board page renders fine but `api/v1/jobs` next to it is the real feed:
    # full `description.html`, a `hostedUrl`, and epoch-second `publishedDate` / `createdDate`.
    # Found 8 Aug 2026 morning on luma-vision, reached from an Indeed search rather than a board
    # sweep. `/jobs.json` and `/api/jobs` both 404 here — only `/api/v1/jobs` answers.
    "hirehive": "https://{s}.hirehive.com/api/v1/jobs",
}

# 29 Sep 2026: instructions/COMPANIES.md is read as well. Runs kept "adding a board" by writing it into
# instructions/COMPANIES.md and never into BOARDS above, so 51 of the 171 documented boards were never
# polled, among them Mistral AI, Hugging Face, Atira, The Exploration Company (whose one ML
# role scored fit 8 on 16 Sep off a LinkedIn card) and LIME medical. Fetched from the laptop
# that day with this parser: 37 of the 51 answered with 1,447 jobs. Every `kind | slug | name`
# line whose kind has a URL is polled now, and BOARDS stays for entries that need a comment.
def _from_companies_md(path=None):
    """Review, 29 Sep 2026: slugs may carry %20 ("Tools%20for%20Humanity"); the same board listed
    under two kinds of one ATS (teamtailor and teamtailor_feed, personio and personio_html,
    recruitee and recruitee_custom) is polled once, keyed on the ATS family and the company
    name; and a missing instructions/COMPANIES.md must not stop the whole collector."""
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instructions/COMPANIES.md")
    fam = lambda k: k.split("_")[0]
    nm = lambda n: fold(re.sub(r"\([^)]*\)", " ", n or ""))
    have = {(k, s.lower()) for k, s, *_ in BOARDS}
    have_names = {(fam(k), nm(n)) for k, s, n, *_ in BOARDS}
    have_urls = {URLS[k].format(s=s) for k, s, *_ in BOARDS if k in URLS}
    out, dead = [], set()
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError as ex:
        print("instructions/COMPANIES.md not read: %s" % ex, file=sys.stderr)
        return out, dead
    for line in lines:
        m = re.match(r"\s*([a-z_]+)\s*\|\s*([A-Za-z0-9._%\-]+)\s*\|\s*(.+?)\s*\|", line)
        # 29 Oct 2026: a line whose kind is `dead` retires that slug everywhere, BOARDS included.
        # Meshcapade's line had said "DEAD, stop polling" since 3 Aug while BOARDS kept polling it.
        if m and m.group(1) == "dead":
            dead.add(m.group(2).lower())
            continue
        if not m or m.group(1) not in URLS:
            continue
        k, slug, name = m.group(1), m.group(2), m.group(3)
        url = URLS[k].format(s=slug)
        if (k, slug.lower()) in have or (fam(k), nm(name)) in have_names or url in have_urls:
            continue
        have.add((k, slug.lower())); have_names.add((fam(k), nm(name))); have_urls.add(url)
        out.append((k, slug, name))
    return [b for b in out if b[1].lower() not in dead], dead


_MD, DEAD = _from_companies_md()
BOARDS = [b for b in BOARDS if b[1].lower() not in DEAD] + _MD



def fetch(url, timeout=40, _retries=1):
    # 2 Oct 2026: a Personio board that is not public redirects to personio.com, and personio.com
    # answers a script with 429. That 429 was read as a rate limit on the board since 21 Aug 2026
    # (meshcapade, advastore), with a 20 second pause and a retry on every run. It is now reported
    # as what it is, and a real 429 from the board itself still gets one pause and retry.
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if "jobs.personio" in url and "jobs.personio" not in (getattr(e, "url", "") or url):
            raise RuntimeError("the board is not public, it redirects to %s" % e.url.split("//")[-1].strip("/")[:40])
        if e.code == 429 and _retries > 0:
            time.sleep(20)
            return fetch(url, timeout, _retries - 1)
        raise


def strip(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h or "", flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    h = (h.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", h).strip()


def _cdata(x):
    return re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", x or "", flags=re.S)


def parse(kind, slug, name, raw):
    o = []
    if kind == "greenhouse":
        for j in json.loads(raw).get("jobs", []):
            o.append(dict(title=j.get("title", ""),
                          location=(j.get("location") or {}).get("name", ""),
                          # `first_published` first, not `updated_at`. Greenhouse boards carry
                          # evergreen pipeline reqs whose `updated_at` is refreshed constantly:
                          # Intercom's *Senior Machine Learning Scientist* read 4 Sep 2026 on
                          # `updated_at` and 2 Nov 2025 on `first_published` (5 Sep 2026 morning).
                          # Scoring off `updated_at` hands a 10-month-old pipeline advert a +2
                          # freshness bonus. The SumUp and SoundCloud notes in instructions/COMPANIES.md
                          # already say to score off `first_published`; this makes the collector
                          # emit it.
                          url=j.get("absolute_url", ""), date=j.get("first_published", "") or j.get("updated_at", ""),
                          desc=j.get("content", "")))
    elif kind in ("lever", "lever_eu"):
        for j in json.loads(raw):
            o.append(dict(title=j.get("text", ""),
                          location=(j.get("categories") or {}).get("location", ""),
                          url=j.get("hostedUrl", ""), date=str(j.get("createdAt", "")),
                          # 2 Oct 2026: `descriptionPlain` is the opening only. The requirements
                          # are in `lists` and the closing section in `additional`; on the one
                          # `lever` board they held 8,400 of 9,100 characters per job.
                          desc=join_html(j.get("description") or j.get("descriptionPlain", ""),
                                         *[(l.get("text", ""), "<ul>%s</ul>" % (l.get("content") or ""))
                                           for l in (j.get("lists") or []) if isinstance(l, dict)],
                                         j.get("additional") or j.get("additionalPlain", ""),
                                         j.get("salaryDescription") or j.get("salaryDescriptionPlain", ""))))
    elif kind == "ashby":
        # `location` is the PRIMARY location only; a job open in several offices carries the
        # rest under `secondaryLocations`. Reading `location` alone hid SpAItial's entire
        # board from 22 Aug 2026 back: every SpAItial job says `location: "London"` with
        # Munich sitting in secondaryLocations, so filter_run's loc_ok saw a pure-UK job and
        # threw all nine away. They only surfaced through the Getro copy, which writes the
        # location as "Munich, Germany, London, UK". Join every office into one string so a
        # German office anywhere in the list is visible to the location filter.
        for j in json.loads(raw).get("jobs", []):
            locs = [j.get("location") or ""]
            for s in (j.get("secondaryLocations") or []):
                # NB: never bind this to `name` — that is the company parameter, and shadowing
                # it here stamped the last secondary location onto every job on the board as
                # its employer. 436 of 2983 rows on 22 Aug 2026 evening came back with a city
                # ("Berlin", "Kyiv", "Home Office") where the company should be.
                locname = s.get("location") if isinstance(s, dict) else str(s)
                addr = ((s.get("address") or {}).get("postalAddress") or {}) if isinstance(s, dict) else {}
                part = ", ".join(x for x in [locname, addr.get("addressCountry")] if x)
                if part:
                    locs.append(part)
            # The URL above already asks for compensation. Ashby publishes it on very few
            # postings (1 of 109 at Preply, 0 of 31 at Moss, checked 21 Sep 2026), but when it
            # is there it sits outside the description and no reader would ever see it.
            comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
            o.append(dict(title=j.get("title", ""),
                          location="; ".join(x for x in locs if x)[:120],
                          url=j.get("jobUrl", ""), date=j.get("publishedAt", "") or "",
                          salary=comp,
                          desc=j.get("descriptionHtml") or j.get("descriptionPlain", "")))
    elif kind == "personio":
        for m in re.finditer(r"<position>(.*?)</position>", raw, re.S):
            b = m.group(1)
            g = lambda t: (re.search(r"<%s>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>" % (t, t), b, re.S) or [None, ""])[1]
            pid = g("id")
            # 2 Oct 2026: the text is one <jobDescription> per section, each a <name> and a CDATA
            # <value>. Stripping the whole <position> block put the id, department, keywords and
            # a stray "]]>" into every description.
            secs = [(strip(_cdata(n)), _cdata(v)) for n, v in re.findall(
                r"<jobDescription>\s*<name>(.*?)</name>\s*<value>(.*?)</value>\s*</jobDescription>", b, re.S)]
            # The feed states a salary on a few postings (33 of 623 on 2 Oct 2026), outside the text.
            sal = re.search(r"<salaryInformation>(.*?)</salaryInformation>", b, re.S)
            pay = ""
            if sal:
                f = lambda t: (re.search(r"<%s>(.*?)</%s>" % (t, t), sal.group(1), re.S) or [None, ""])[1].strip()
                lo, hi = f("min").split(".")[0], f("max").split(".")[0]
                per = {"yearly": "", "monthly": " a month", "hourly": " an hour"}.get(f("type"), " " + f("type") if f("type") else "")
                pay = ("%s %s%s" % (f("currencyCode") or "EUR", "-".join(x for x in [lo, hi] if x), per)).strip() if lo or hi else ""
            o.append(dict(title=strip(g("name")), location=strip(g("office")),
                          url="https://%s.jobs.personio.de/job/%s" % (slug, pid),
                          date=strip(g("createdAt")), salary=pay, desc=join_html(*secs)))
    elif kind in ("teamtailor", "teamtailor_feed", "teamtailor_custom"):
        d = json.loads(raw)
        for j in d.get("items", []) or d.get("jobs", []):
            o.append(dict(title=j.get("title", ""), location=j.get("location", "") or "",
                          url=j.get("url", "") or j.get("id", ""),
                          date=j.get("date_published", "") or j.get("created-at", ""),
                          desc=j.get("content_html", "") or j.get("body", "")))
    elif kind == "workable":
        for j in json.loads(raw).get("jobs", []):
            o.append(dict(title=j.get("title", ""),
                          location=", ".join(x for x in [j.get("city"), j.get("country")] if x),
                          url=j.get("url", ""), date=j.get("published_on", "") or "",
                          desc=join_html(j.get("description"), j.get("requirements"), j.get("benefits"))))
    elif kind in ("recruitee", "recruitee_custom"):
        for j in json.loads(raw).get("offers", []):
            o.append(dict(title=j.get("title", ""),
                          location=", ".join(x for x in [j.get("city"), j.get("country_code")] if x),
                          url=j.get("careers_url") or j.get("careers_apply_url", ""),
                          date=j.get("published_at") or j.get("created_at", ""),
                          desc=join_html(j.get("description"), j.get("requirements"))))
    elif kind == "pinpoint":
        d = json.loads(raw)
        for j in (d.get("data") if isinstance(d, dict) else d) or []:
            loc = j.get("location") or {}
            o.append(dict(title=j.get("title", ""),
                          location=", ".join(x for x in [loc.get("city"), loc.get("province")] if x),
                          url=j.get("url", ""),
                          date=j.get("published_at") or j.get("created_at") or "",
                          # 2 Oct 2026: there is no `requirements` field. The tasks and the
                          # requirements are in the two fields below, 3,200 of 5,100 characters.
                          desc=join_html(j.get("description"),
                                         ("Key responsibilities", j.get("key_responsibilities")),
                                         ("Skills, knowledge and expertise", j.get("skills_knowledge_expertise")),
                                         ("Benefits", j.get("benefits")))))
    elif kind == "hirehive":
        import datetime
        for j in json.loads(raw).get("jobs", []):
            ts = j.get("publishedDate") or j.get("createdDate")
            date = (datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                    if isinstance(ts, (int, float)) else "")
            ctry = (j.get("country") or {}).get("name") or ""
            o.append(dict(title=j.get("title", ""),
                          location=", ".join(x for x in [j.get("location"), ctry] if x),
                          url=j.get("hostedUrl", ""), date=date,
                          desc=(j.get("description") or {}).get("html", "") or (j.get("description") or {}).get("text", "")))
    elif kind == "smartrecruiters":
        for j in json.loads(raw).get("content", []):
            loc = j.get("location") or {}
            o.append(dict(title=j.get("name", ""),
                          location=", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
                          url="https://jobs.smartrecruiters.com/%s/%s" % (slug, j.get("id")),
                          date=j.get("releasedDate", "") or "", desc=""))
    elif kind == "personio_html":
        # The anchor text is title + location + employment type run together, e.g.
        # "Software Engineer - AI Workflows (m/f/d) NL, DE Full-time Permanent employee".
        # Left whole it defeats the repeat check: on 9 Aug 2026 evening EnOcean's AI Workflows
        # role — sent 4 Aug — came back as new, because the trailing noise sank the fuzzy
        # title overlap in is_repeat. Split the tail off and keep it as the location instead.
        #
        # Two extensions, both found on botario 17 Aug 2026 evening, where the whole tail
        # survived and the title came off the board as "Machine Learning Engineer (all
        # genders) Bremen, Mainz, Berlin, München, Mannheim Full or part-time Permanent
        # employee". That title has five tokens of pure noise on the end, which sinks the
        # Jaccard in `same_title` to 0.44 and let a role sent on 15 August through as new
        # for the third run running.
        #
        # 1. The employment type is not always one of the four fixed words. botario writes
        #    "Full or part-time", Personio also emits "Voll- oder Teilzeit" and a bare
        #    "Permanent employee" when no working-time is set, and none of those anchored.
        # 2. Locations are not always two-letter codes. Boards with several offices spell
        #    them out in full, so peel real place names off the end of what is left and put
        #    them in the location where they belong, rather than leaving them in the title.
        TAIL = re.compile(
            r"\s+((?:[A-Z]{2}(?:,\s*[A-Z]{2})*\s+)?"
            r"(?:Full(?:\s+or\s+part)?[-\s]?time|Part(?:\s+or\s+full)?[-\s]?time|"
            r"Voll(?:-?\s*(?:oder|und)\s*Teil)?zeit|Teil(?:-?\s*(?:oder|und)\s*Voll)?zeit|"
            r"Intern|Internship|Working Student|Werkstudent|Temporary|Fixed term|"
            r"Permanent employee|Limited contract)\b.*)$")

        def peel_places(head):
            """Move trailing place names out of the title and into the location."""
            toks, places = head.split(), []
            while toks and fold(toks[-1].strip(",")) in PLACE:
                places.insert(0, toks.pop().strip(","))
            # Never strip the title down to nothing: "Berlin" alone is not a job, but a
            # role genuinely titled e.g. "Remote Engineer" must keep its first word.
            if len(toks) < 2:
                return head, ""
            return " ".join(toks).rstrip(" ,-|"), ", ".join(places)

        for m in re.finditer(r'href="(/job/(\d+)[^"]*)"[^>]*>(.*?)</a>', raw, re.S):
            text = strip(m.group(3))[:200]
            tail = TAIL.search(text)
            title, loc = (text[:tail.start()].strip(), tail.group(1).strip()) if tail else (text, "")
            title, extra = peel_places(title)
            loc = ", ".join(x for x in [extra, loc] if x)
            o.append(dict(title=title[:120],
                          location=loc[:60], url="https://%s.jobs.personio.com%s" % (slug, m.group(1)),
                          date="", desc=""))
    elif kind == "join":
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
        if m:
            items = (json.loads(m.group(1)).get("props", {}).get("pageProps", {})
                     .get("initialState", {}).get("jobs", {}).get("items") or [])
            for j in items:
                # `locations` is null on every row seen. The place is under `city`, which is a
                # NESTED dict {"cityName", "countryName"}, not a string — reading it as a string
                # yields a bare "hybrid" location, which `loc_ok` in filter_run.py then drops as
                # neither German nor remote. That would have silently binned both new boards.
                city = j.get("city") if isinstance(j.get("city"), dict) else {}
                loc = ", ".join(x for x in [city.get("cityName"), city.get("countryName")]
                                if isinstance(x, str) and x)
                wt = j.get("workplaceType")
                if isinstance(wt, str) and wt and wt.lower() != "onsite":
                    loc = "%s (%s)" % (loc, wt.lower()) if loc else wt.lower()
                jid = j.get("idParam") or j.get("id")
                o.append(dict(title=j.get("title", ""), location=loc[:80],
                              url="https://join.com/companies/%s/%s" % (slug, jid),
                              date=j.get("createdAt", "") or "", desc=""))
    elif kind == "avature":
        # One <li class="list__item ..."> per role. Title and url live in
        # list__item__text__title; the subtitle runs "Location · Seniority · Type · blurb"
        # with <span> · </span> separators, so the location is everything before the first
        # dot. Split on the <li> first rather than running one regex over the whole page,
        # because the non-greedy spans would otherwise stitch one job's title to the next
        # job's subtitle.
        #
        # No posting date is published anywhere on the board, so `date` stays empty and
        # these score without a freshness bonus. Do not invent one. Closed roles return
        # HTTP 410 rather than disappearing quietly, so a 410 on a link the radar sent
        # earlier means the role was filled, not that this parser broke.
        for chunk in raw.split('class="list__item ')[1:]:
            t = re.search(r'list__item__text__title.*?<a\s+href="([^"]+)"[^>]*>(.*?)</a>',
                          chunk, re.S)
            if not t:
                continue
            s = re.search(r'list__item__text__subtitle[^>]*>(.*?)</div>', chunk, re.S)
            loc = strip(s.group(1)).split("·")[0].strip() if s else ""
            o.append(dict(title=strip(t.group(2))[:120], location=loc[:60],
                          url=t.group(1), date="", desc=""))
    elif kind == "breezy":
        for j in json.loads(raw):
            loc = j.get("location") or {}
            city = (loc.get("city") or "") if isinstance(loc, dict) else str(loc)
            o.append(dict(title=j.get("name", ""), location=city,
                          url=j.get("url", "") or ("https://%s.breezy.hr/p/%s" % (slug, j.get("id"))),
                          date=j.get("published_date", "") or "", desc=""))
    for j in o:
        j["company"], j["source"] = name, "ats:" + kind
        # Every branch above leaves the source HTML in `desc`. It is cleaned here, once, whole.
        raw = j.get("desc") or ""
        j["desc"] = html_to_text(raw)
        if KEEP_RAW:
            j["desc_raw"] = raw
    return o


def one(b):
    kind, slug, name = b
    url = URLS[kind].format(s=slug)
    try:
        raw = fetch(url)
        jobs = parse(kind, slug, name, raw)
        # SmartRecruiters caps a response at 100 postings and reports the real size in
        # `totalFound`. Without paging, AUTO1 returned 100 of 532 on 30 Aug 2026 and the
        # missing 432 are not ordered in any useful way, so a computer-vision role could sit
        # in the unread tail every run and never be seen. Scalable Capital fits in one page,
        # which is why this went unnoticed until a bigger board was added.
        if kind == "smartrecruiters":
            total = json.loads(raw).get("totalFound") or 0
            for off in range(100, min(total, 2000), 100):
                jobs += parse(kind, slug, name, fetch(url + "&offset=%d" % off))
        # join.com paginates the hydration payload at a FIXED five jobs per page and ignores
        # `pageSize` entirely (same validator that rejects it on the public REST endpoint), so
        # reading only the board url gives 5 of however many exist. Found 27 Sep 2026 morning
        # on omnisent, whose ML Engineer role — the only ML seat on a 15-job board — sits on
        # page 3 and had never been collected. Checked across all twelve join slugs that day:
        # 32 of 67 jobs were invisible, worst of them motor-ai at 5 of 16. `?page=N` works and
        # the real size is in `initialState.jobs.pagination`, so walk it like SmartRecruiters.
        if kind == "join":
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
            pages = 1
            if m:
                pages = ((json.loads(m.group(1)).get("props", {}).get("pageProps", {})
                          .get("initialState", {}).get("jobs", {})
                          .get("pagination", {}) or {}).get("pageCount") or 1)
            for pg in range(2, min(int(pages), 40) + 1):
                jobs += parse(kind, slug, name, fetch(url + "?page=%d" % pg))
        return name, slug, kind, jobs, None
    except urllib.error.HTTPError as e:
        return name, slug, kind, [], "HTTP %s" % e.code
    except Exception as e:
        return name, slug, kind, [], str(e)[:80]


def main():
    all_jobs, report = [], []
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for name, slug, kind, jobs, err in ex.map(one, BOARDS):
            report.append(dict(company=name, slug=slug, kind=kind, n=len(jobs), err=err))
            all_jobs.extend(jobs)
            print("%-22s %-16s %-18s %4s %s" % (name[:22], slug[:16], kind, len(jobs), err or ""),
                  file=sys.stderr)

    json.dump(all_jobs, open(sys.argv[1], "w"), ensure_ascii=False)
    json.dump(report, open(sys.argv[2] if len(sys.argv) > 2 else sys.argv[1] + ".report",
                                "w"), ensure_ascii=False, indent=1)
    print("TOTAL %d jobs from %d boards" % (len(all_jobs), len(BOARDS)), file=sys.stderr)


if __name__ == "__main__":
    main()

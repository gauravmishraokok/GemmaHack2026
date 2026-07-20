# The problem it solves

## In one line
Small banks can't afford good AML compliance, and big AML tools can't legally touch their data. viGEMMAlya fixes both — it runs entirely on the bank's own machine and does the compliance officer's manual work for them.

## The problem, broken down

Every bank in India — big or small — has to watch its transactions for money laundering and file a report (STR) within **7 working days** if something looks suspicious. Miss it, and there are heavy daily fines.

- **Small NBFCs and co-operative banks can't afford a big compliance team.** A large bank has dozens of people doing this by hand. A small bank has one or two.
- **Rule-based alert systems flag almost everything.** Simple rules ("amount > ₹10 lakh") create **90%+ false alarms**. Someone still has to check every single one by hand — pull the transaction history, check if accounts are linked, find the right law section, and write it all up. That's hours per case.
- **Cloud AI tools are illegal to use here.** RBI and India's data protection law (DPDP) say customer financial data cannot leave the bank's building. So ChatGPT-style tools are simply not allowed for this job, no matter how good they are.

## What we built

```
Raw transactions
     │
     ▼
┌─────────────────────────────┐
│  BATCH ENGINE (:8001)         │   turns thousands of transactions
│  Rules → ML score → Cluster   │   into a handful of real "cases"
│  → Gemma reads its own risk   │
│    score from the data         │
└─────────────────────────────┘
     │  a few real cases come out
     ▼
┌─────────────────────────────┐
│  REASONING ENGINE (:8002)     │   for each case:
│  Gather evidence               │   - build a timeline
│  → Check: enough evidence?     │   - find linked accounts
│    NO → STOP, don't guess       │   - check KYC red flags
│  → Gemma writes the report      │   - if not enough proof → refuse
│  → Check every number is real   │   - draft the report
│  → Colour-code each sentence    │   - grade its own confidence
└─────────────────────────────┘
     │
     ▼
Human reviews → clicks "Attest" → 
   ✅ Report emailed
   ✅ WhatsApp sent
   ✅ Official filing exported
   ✅ Tamper-proof log updated
```

**The whole thing runs on a normal computer, nothing goes to the cloud.**

## Who this helps and how

| Who | What changes for them |
|---|---|
| **Compliance officer** | Spends minutes, not hours, per case. The AI does the first draft; they just check and sign off. |
| **SME customer** | Banks often **freeze an account first and investigate later**. Faster investigation means fewer accounts get stuck frozen — so payroll, supplier payments, and daily business don't get blocked. |
| **SME applying for a loan** | AML checks before a loan is approved are a big source of delay. Cutting that from hours to minutes means faster access to credit exactly when it's needed. |
| **SMEs with "messy" profiles** (new business, cross-border payments) | Banks often avoid these customers because manually checking them is expensive. Cheaper, faster review means banks can afford to say yes more often. |
| **The bank itself** | Gets a real audit trail, a report drafted for them, and instant notification the moment something is filed — instead of paperwork sitting in someone's inbox. |

---

# Challenges we ran into

We ran into problems at every layer — model, backend, integration, and frontend. Listing all of them, small and big, because they show how much of this was actually built and debugged, not just planned.

### 🧠 Getting Gemma to actually run

- **The big model didn't fit.** We originally planned to use Gemma's 4B model to read its internal "thoughts" for risk scoring. It needed more RAM than we had and kept crashing. We swapped to Gemma's 1B model instead — smaller, but it worked, and we're honest about that trade-off.
- **The bigger model was too slow to demo.** For the report-writing side, the bigger Gemma model took over **10 minutes per case** on our machine because it didn't fully fit on the GPU. We switched the default to a smaller, faster model that finishes in about a minute with no real drop in report quality. (The bigger model is still there as an option if someone has better hardware.)
- **Gemma's answers were getting cut off, and we didn't know why at first.** Gemma "thinks out loud" internally before answering, and that silently used up its whole response limit — so we'd get an empty answer back instead of a report, with a confusing error message. We fixed it by giving it a bigger response window.

### 🔍 Making sure the AI doesn't lie

- **We built a rule: the AI can never invent a fact.** Every number and every claim in the report has to trace back to a real piece of evidence. We built a checker that verifies every dollar amount the AI writes actually exists in the transaction data.
- **That checker then caught a bug in our own code, not the AI.** We were showing the AI a rounded-off number (like ₹9,90,000) instead of the exact one (₹9,90,000.42). The AI correctly copied what we showed it — but our own checker then flagged it as "unverifiable" because it didn't match the *real* exact number, which we weren't even displaying. It looked like the AI was hallucinating; it was actually our display bug. Took a while to realize the AI was innocent here.
- **The AI is also forced to use a fixed list of official terms**, so it can never write something like "looks kinda suspicious" instead of a real legal category — that option simply isn't available to it at the token level, not just filtered afterward.

### 🔗 Two people, one shared codebase, no chaos

- We split the project into two halves (data engine vs. reasoning engine) built by two people at once. To stop them from breaking each other, we froze a shared "contract" file early — the exact shape of the data both sides agree on.
- Halfway through, one side needed extra fields (KYC status, shared PAN groups, ML scores per transaction). We had to add these carefully so nothing broke for whoever hadn't updated yet — every new field was optional with a safe default.
- We wrote an actual integration document with copy-pasteable examples so merging the two halves didn't turn into a guessing game.

### 💰 Real data breaks things fake data never would

- Once we plugged in the real transaction dataset, things broke that never showed up in our test data — like currencies written as "US Dollar" and "Euro" instead of ₹ everywhere. Had to rewrite our number-formatting and our fact-checking code to handle any currency, not just rupees.

### 🖥️ Frontend headaches

- **Ported the entire analyst dashboard to a second, nicer frontend** (Timeline, Graph view, Evidence list, Investigation view, Report + Heatmap) — rebuilding every screen to match the new design system while keeping every feature working exactly the same.
- **Blank white/black screen with no error message.** After some dependency changes, the new frontend loaded to a completely blank page. Turned out to be a stale build cache clashing with a config change — cleared it and it came back.
- **Port conflicts everywhere.** Multiple background servers from earlier testing kept holding onto the same ports, so a "new" server launch would silently fail while an old, outdated version kept answering requests. Had to hunt down and kill stale processes more than once.
- **Live backend status, not fake loading bars.** We wanted the frontend to show *real* progress while the AI is working (assembling evidence → checking → writing → verifying), not just a spinner. Built a live event stream from the backend so the UI actually reflects what's happening on the server in real time.
- **Light mode / dark mode toggle.** Added a full theme switch — had to make sure every single colour (including special ones like the red/yellow/green risk colours) had a version that stays readable in both light and dark, and that switching between them is smooth instead of jarring.

### 📩 Getting notifications working, fast

- Added automatic email + WhatsApp alerts the moment a report is officially attested. Along the way discovered that our free-tier WhatsApp number **only works for WhatsApp, not plain SMS**, and that the receiving phone number has to manually "join" a sandbox first before messages will deliver. Debugged this live against the real APIs until confirmed messages were actually delivered, not just "sent."
- Made sure that if the email or SMS ever fails, it **never breaks the actual report export** — the important part (the filing + audit log) is already safely saved before we even try to send a notification.

---

# Why this fits Track 2 — Gemma Financial Compliance & Risk Triage

> *"Develop an intelligent compliance assistant that analyzes transactions, onboarding documents, and financial records to detect anomalies, assess risk, summarize findings, and generate compliance-ready reports for review teams."*

Here's how each part of that sentence maps to something we actually built:

| Track asks for | What we built |
|---|---|
| **Analyze transactions & financial records** | Real 5-million-row transaction dataset, cleaned, rule-checked, ML-scored, and clustered into cases |
| **Detect anomalies** | A Gemma-based risk model that reads the case's own internal representation (not just a prompt) to score suspicion — tested against two other methods on the same data, and it wins |
| **Assess risk** | Every case gets a risk score, a confidence margin, and an "out of distribution" flag, sorted into Red / Yellow / Green with an adjustable threshold |
| **Summarize findings** | A plain-English case summary, a description of the suspicious pattern, and suggested next questions — every claim linked back to real evidence |
| **Generate compliance-ready reports** | A structured Suspicious Transaction Report using only official legal categories, colour-coded by how confident each sentence is, exported as an official filing, and now automatically emailed + WhatsApp'd the moment it's signed off |
| **Onboarding documents** | KYC status, shell-company flags, and jurisdiction risk already feed into the report today; the next natural step is plugging in real document scanning, and the pipeline is already built to accept it |

## What makes it more than "just an LLM wrapper"

For a track specifically about *compliance and risk*, where a wrong answer means a bad legal filing, we leaned hard into things that are **only possible because the model runs locally**:

- 🧠 **Reads the model's brain, not just its words** — risk scoring looks at Gemma's internal activations directly, something a cloud API physically cannot expose.
- 🔒 **Physically cannot output an invalid answer** — the legal category field is locked to a fixed list at the token level. It's not "usually correct," it's "impossible to be wrong here."
- 🎯 **Grades its own honesty, sentence by sentence** — using the model's own confidence per word, cross-checked against the real transaction ledger, so a human knows exactly which lines to double-check before signing anything.
- 🔐 **Never leaves the building** — which isn't just a nice feature here, it's the actual legal requirement this whole track is quietly built around.

# Atheria — Demo Video Script

**Target length:** 4:30 – 5:00
**Audience:** Non-technical. PV leadership, quality, compliance, business stakeholders.
**Spoken words:** 596 — 4:00 of pure narration at 150 wpm, landing near 4:45 with
clicks and the live AI pauses. If you need to come in under 4:00, drop the
Literature Monitoring section (0:22) and shorten the problem intro.

## How to use this

Left column is what the viewer sees. Right column is what you say, word for word.
Timings are cumulative. `[Brackets]` are stage directions, not spoken.

**Golden rule for this audience:** never say model, LLM, prompt, API or schema.
Say *"the AI reads it"* and *"the rulebook decides"*. Technical credibility comes
from what appears on screen, not from vocabulary.

---

## 0:00 – 0:20 · The problem

| Screen | Narration |
|---|---|
| Title card: **Atheria**, then a slide with three icons — form, phone, journal | Every day, reports arrive that a patient may have been harmed by one of our medicines. From doctors, from patients, from published research. |
| | Someone must read every one and answer one question: **is this a case we are legally required to report?** |
| | Today that's manual and it doesn't scale. Atheria answers it in seconds — and shows its work. |

---

## 0:20 – 0:38 · Sign in: two doors

| Screen | Narration |
|---|---|
| Sign-in page, cursor over the two roles | Atheria has two front doors, because two very different people use it. |
| Highlight **Reporter**, then **PV Expert** | A reporter, who needs to tell us something happened. And a pharmacovigilance expert, who decides what to do about it. |
| Click **Reporter** | Let's start as the reporter. |

---

## 0:38 – 1:15 · Reporter: the web form

| Screen | Narration |
|---|---|
| Reporter home: **Report an Event** and **Talk to us**. Click **Report an Event** | Two ways to reach us. First, a form: reporter, patient, medicine, what happened. |
| Pause on the optional fields | Almost everything is optional, deliberately — a form that refuses incomplete information just loses the report. |
| Submit the complete example | So: a physician reports a fifty-four-year-old woman, severe rash after starting her medicine, admitted overnight. Submit. |
| Green **Valid ICSR** badge appears | Two seconds, and it has a decision: **a valid reportable case.** We'll come back to how. |

---

## 1:15 – 1:55 · Reporter: the voice agent

| Screen | Narration |
|---|---|
| Back to reporter home. Click **Talk to us** | But many people won't fill in a form. They'd rather just talk. |
| Type: *"my mum has been really dizzy since her new tablets"* | So they can describe it in their own words. |
| Agent asks a follow-up | And here it does something a form cannot. It notices what's missing, and asks. |
| Agent asks a second follow-up | How old is she. What's the medicine. When did it start — until the account is complete. That's the difference between an abandoned form and a usable report. |
| Confirmation summary | But the assistant only gathers. It decides nothing. Every report goes to the same rulebook — which brings in our second user. |

---

## 1:55 – 2:15 · Switching to the expert

| Screen | Narration |
|---|---|
| Sign out, sign in as **PV Expert** | This is the expert's view. |
| Dashboard with live counts | How much came in, how much is genuinely reportable, how much needs a human, how much isn't our concern. |
| Open the **Triage Inbox** | And the work queue — form, conversation, literature, all in one list, most urgent first. |

---

## 2:15 – 3:00 · The determination, and its evidence

| Screen | Narration |
|---|---|
| Click the green **Valid ICSR** case | Let's open the case we just submitted. |
| Four criteria panel, all Present | A reportable case legally needs four things: an identifiable patient, an identifiable reporter, a suspect medicine, and an adverse event. All four are here. |
| **Click an evidence quote** — source highlights below | Now watch this. Every one is backed by the actual words from the report. Click it, and it highlights the exact sentence it came from. Nothing is asserted without evidence — there's no black box to take on trust. |
| Scroll to the rule panel showing `val_001 v1.0.0` | And the decision wasn't made by the AI. It was made by our own rulebook — named, version-numbered, controlled by us. |
| | The AI reads. The rulebook decides. A qualified person approves. That separation is what makes this defensible to a regulator. |

---

## 3:00 – 3:30 · The case that matters most

| Screen | Narration |
|---|---|
| Back to the queue. Click the amber **Escalated** case | Now the most important screen here. |
| Criteria: medicine and event present, patient and reporter absent | Someone mentioned a medicine and a serious side effect — but we've no idea who the patient was, or who reported it. |
| Zoom the rule explanation | Read what it does with that. *"We do not guess — escalating for human review rather than asserting or discarding validity."* |
| | It could have quietly filed this as not-a-case and the numbers would look tidier. It could have invented the missing details. It does neither — it says so, and hands the case to a human. |
| | In safety work, a system that admits what it doesn't know is worth more than one that always has an answer. |

---

## 3:30 – 3:52 · Literature monitoring

| Screen | Narration |
|---|---|
| Click **Literature Sweep**, show standing queries, run one | We're also legally required to monitor published research. This searches the world's medical literature live, and puts every article through the same assessment. |
| Point at a *Not an ICSR* result | Most review articles correctly come back as not reportable — there's no individual patient in them. That's it being right, not lazy. And run the same search tomorrow, it recognises what it's already seen. |

---

## 3:52 – 4:05 · Close

| Screen | Narration |
|---|---|
| Dashboard, or a four-line slide | So: three ways in, assessed in seconds. Every decision shows the words behind it and names the rule that made it. And when information is missing, it escalates instead of guessing. |
| Atheria title card | The AI reads. The rulebook decides. The expert approves. That's Atheria. |

---

# Production notes

## Before you can record this

The **role-based sign-in does not exist in the codebase yet.** Today there is a
dev-bypass login and all four pages are visible to everyone. To record this
script as written you need:

1. A sign-in page offering **Reporter** and **PV Expert**
2. **Reporter view** — Report an Event and the voice agent only
3. **PV Expert view** — Dashboard, Triage Inbox, Literature Sweep
4. The **voice agent embedded** in the reporter view (it is a separate service
   today and not part of this repository)

Everything else in the script works right now.

## Seed the data before recording

Do this beforehand so the inbox isn't empty on camera, then **don't clear it**:

1. Submit the *Complete report* example → the green Valid ICSR
2. Submit the *Incomplete report* example → the amber Escalated case
3. Submit the *Enquiry only* example → a Not-an-ICSR case
4. Run one literature sweep → adds real articles

During recording you then submit only **one** live case, which keeps the runtime
down while giving you a populated queue to explore.

## Things that will hurt the video

- **Cold starts.** On a free tier the first request after idle can take a minute.
  Click something to wake it immediately before you hit record.
- **Live AI calls take about two seconds.** Don't edit them out — that pause is
  proof it's really running. Just talk over it.
- **Synthetic data only.** Every name in the examples is invented. Never record
  with real case data.
- **Zoom in on the evidence highlight and the rule name.** They're small on
  screen and they're the two most persuasive moments in the demo.
- **Hide dev tools and the terminal.** Non-technical viewers read logs as errors.

## If you only have 90 seconds

Submit the complete report → show the four criteria → click one evidence quote to
highlight the source → open the escalated case and read the "we do not guess"
line. That's the whole argument.

## Questions you will be asked

**"Is the AI making medical decisions?"**
No. It reads the report and points at what it found. A fixed rulebook we own
makes the decision, and a qualified person approves it.

**"What if the AI gets it wrong?"**
Every field shows the sentence it came from, so a reviewer verifies in seconds
instead of re-reading everything. And the AI cannot overrule the rulebook.

**"Can it handle something it hasn't seen before?"**
If the information needed isn't present, it escalates rather than guessing.
That's designed behaviour, not a failure.

**"Could we prove this to an inspector?"**
Every decision records which rule made it, which version, and the evidence it
used — and the trail can't be edited afterwards.

**"How much does it cost to run?"**
Fractions of a penny per report assessed.

**"What happens to the voice conversation afterwards?"**
It should be archived as the source document, so every detail taken from it can
be traced back. Worth confirming this is wired up before go-live.

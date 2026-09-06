# Atheria — Demo Video Script

**Audience:** Non-technical — PV leadership, quality, compliance, business stakeholders

Read this aloud as continuous narration. Screen directions sit in *italics* between
paragraphs; everything else is spoken as written.

### Two lengths in one script

Both counts below are measured from this file, not estimated.

| Read | Words | Narration | With pauses |
|---|---|---|---|
| **Full** | 984 | 6:33 | **~7:00** |
| **Short** — skip everything marked `[SHORT: cut]` | 731 | 4:52 | **~5:15** |

The short read drops the lifecycle slide, the literature section, and three
paragraphs. The story still runs start to finish: the obligation, the vision, both
reporting routes, the evidenced decision, and the escalation.

Prose runs longer than clipped bullet points. That's the cost of it sounding like a
person talking rather than a list being read, which is usually worth paying with
this audience.

### One rule throughout

Never say model, LLM, prompt, API or schema. Say *the AI reads it* and *the rulebook
decides*. The credibility comes from what's on screen, not the vocabulary.

Whatever you cut, keep the escalated case at 3:52. It's the most persuasive forty
seconds in the video.

---

## Part one — the vision

### 0:00 · Where this sits · **`[SHORT: cut this whole section — open on the channels slide instead]`**

*Open on the lifecycle wheel, all four quadrants visible.*

Every medicine follows the same journey. Discovered and tested for years.
Manufactured at scale. Approved, and one day it reaches a patient who needs it.

*Let the first three quadrants highlight, then settle on Post-Market Monitoring.*

Three of those stages end. This one never does. From the day a medicine reaches the
market, we're legally obliged to keep watching what it does to real people — not in
a trial, out in the world, for as long as it's on the shelf. That's
pharmacovigilance, and that's where Atheria works.

### 0:20 · What that obligation looks like

*Move to the channels slide. Bring in the left-hand column.*

The difficulty is that safety information never arrives tidily. It comes through
web forms and helplines, by email, in published research — and increasingly on
social media, where someone just mentions that a medicine made them unwell. Seven
channels, every one a different shape.

*Follow the flow into the centre, then bring in the reports on the right.*

**`[SHORT: cut this paragraph]`** All of it has to reach one place, structured the
same way, before we can look across the whole picture for a side effect turning up
more often than it should. And it ends in paperwork regulators demand, to deadlines
set by someone other than us.

A large, continuous, heavily regulated operation — and today almost all of it is
done by hand.

### 0:52 · What we're building

*Move to the four-stage slide.*

So we're building one platform across the whole chain, in four stages. Collect,
pulling information in from every channel. Review, working out what each report
actually is. Analyse, looking for a signal starting to emerge. And report,
producing the regulatory documents on time.

*Point to the line along the bottom.*

All driven by AI agents, with a human in the loop to verify. That last part isn't a
footnote we added to sound responsible — it's the principle the whole thing is built
around, and you'll see where it's enforced.

### 1:16 · Where we are today

*Highlight stages one and two.*

That's the destination. Here's where we are. We built the foundation first —
collect and review, on two channels — because everything after it depends on
getting one question right. Is this report a case we're legally required to report?
If that's wrong, every number downstream is wrong with it.

*Cut to the live product.*

Let me show you.

---

## Part two — the product

### 1:36 · Two front doors

*Sign-in page.*

Atheria has two front doors, because two very different people use it. The
reporter — a doctor, a pharmacist, a patient — who needs to tell us something
happened. And the pharmacovigilance expert, who decides what to do about it. Let's
come in as the reporter.

### 1:50 · Reporting by form

*Open the reporting form and scroll it.*

A reporter gets two ways to reach us. First, a form: who's reporting, who the
patient is, which medicine, what happened.

*Pause on the empty optional fields.*

Almost everything here is optional, deliberately. Real reports arrive half-finished
— someone remembers the drug but not the dose. A form that insists on complete
information doesn't get it. It just loses the report.

*Fill in the complete example and submit.*

So: a physician tells us about a woman in her fifties, a severe rash after starting
her medicine, kept in hospital overnight.

*The green Valid ICSR result appears.*

Two seconds, and it has an answer — a valid, reportable case. We'll come back to
how.

### 2:20 · Reporting by conversation

*Return to the reporter home and open the chat.*

But plenty of people will never fill in a form. They'd rather just tell you what
happened.

*Type: "my mum has been really dizzy since her new tablets."*

And here's something a form genuinely cannot do. The assistant reads that and
realises how much is missing.

*Let the agent ask its follow-up questions.*

How old is she. What's the medicine called. When did it start. It keeps going until
the account is complete — the difference between an abandoned form and a report we
can use.

*The conversation closes with its summary.*

But notice what it doesn't do. It gathers; it decides nothing. Every report goes to
the same rulebook — which is where our second user comes in.

### 2:52 · Through the expert's eyes

*Sign in as the PV expert.*

**`[SHORT: cut this paragraph]`** This is the expert's view, and it opens with the
only numbers they need: how much came in, how much is genuinely reportable, how much
needs a human, how much isn't our concern.

*Open the triage inbox.*

And here's the queue — form, conversation, literature, all in one list, most urgent
first.

### 3:12 · How it reached its decision

*Open the green Valid ICSR case.*

To be legally reportable, a report needs four things: an identifiable patient, an
identifiable reporter, a suspect medicine, and an adverse event. All four are here.

*Click an evidence quote so the source text highlights.*

And here's what I'd most like you to notice. Each one is backed by the actual words
from the report. Click it, and you're taken to the sentence it came from. There's no
black box asking to be trusted.

*Scroll to the rule panel showing val_001 v1.0.0.*

And the decision wasn't made by the AI at all. It was made by our own rulebook —
with a name, a version number, and no ability to improvise. The AI reads and
reports what it found. The rulebook decides. A person approves. That's the human in
the loop, made real.

### 3:52 · The case that matters most

*Open the amber, escalated case.*

Now the most important screen here. Someone has mentioned a medicine and a serious
side effect — but we've no idea who the patient was, or who's telling us.

*Zoom in on the rule's explanation.*

Read what it does with that. *We do not guess — escalating for human review rather
than asserting or discarding validity.*

It had easier options. It could have quietly filed this as not-a-case, and the
dashboard would look tidier. It could have filled the gaps with something plausible.
It does neither — it tells you exactly what it couldn't establish, and hands the
case to a person.

In safety work, a system that admits what it doesn't know is worth far more than one
that always has an answer ready.

### 4:32 · Watching the literature · **`[SHORT: cut this whole section]`**

*Run one of the standing literature searches.*

That was the first channel. This is the second — published research, which we're
also required to monitor. It searches the world's medical literature live and puts
every article through the same assessment.

*Point at a not-reportable result.*

Most review articles rightly come back as not reportable, because there's no
individual patient in them. That's the system being correct, not lazy.

### 4:58 · Back to where we started

*Return to the four-stage slide.*

So, back to that picture. Collect and review work today, on two channels, every
decision showing its evidence and naming the rule behind it.

*Highlight stages three and four.*

**`[SHORT: cut this paragraph]`** The remaining channels plug into the same intake,
because it was built from day one not to care where a report came from. And once
cases are structured this reliably, analysis and reporting are the natural next
things to build.

*Atheria title card.*

The AI reads. The rulebook decides. The expert approves. That's Atheria — the first
of four.

---

# Production notes

## Runtime

The full read is 984 spoken words — about 6:33 of narration, landing near 7:00 once
you allow for the live AI pauses and slide transitions. The vision slides account
for roughly a minute and a half of that.

Skipping everything marked `[SHORT: cut]` gives you 731 words, about 4:52 of
narration and roughly 5:15 in total. That's the version to record if you have a
five-minute slot.

If you need to go shorter still, the next thing to lose is the voice agent section
at 2:20 — but you'd be cutting a genuine differentiator, so only do it under
pressure. Don't cut the escalated case; it's forty seconds and it carries the whole
argument.

## The claim to be careful with

The channels slide shows seven ways information arrives. Two are built — the web
form and published research. Phone, email, Instagram, Facebook and X are not. If
asked, the honest answer is strong enough on its own: two are live, and the intake
layer was built so adding a channel is a connector rather than a rebuild, with
nothing downstream changing. That's architecturally true, so you can say it with a
straight face.

Same for the four stages. Collect and review are real; analysis and reporting are
roadmap. The vision is legitimate and the foundation genuinely exists — but
blurring those together is the fastest way to lose a compliance audience, and
they'll remember it.

## Before you can record

The role-based sign-in doesn't exist in the code yet. Right now there's a bypass
login and every page is visible to everyone. To shoot this as written you need a
sign-in page offering the two roles, a reporter view holding just the form and the
voice agent, an expert view holding the dashboard, inbox and literature sweep, and
the voice agent embedded in the reporter view — it's a separate service today and
isn't in this repository. Everything else works right now.

## Seed the data first

Beforehand, submit the complete example to get the green valid case, the incomplete
example for the amber escalated one, and the enquiry example for a not-reportable
result. Run one literature sweep. Then leave it all in place — on the day you
submit only one case live, which keeps the runtime down while giving you a full
queue to explore.

## Things that will spoil the take

On a free tier the first request after idle can take the better part of a minute,
so click something to wake it immediately before recording. The live AI calls take
around two seconds; don't edit them out, because that pause is proof it's really
running — just keep talking over it. Use synthetic data only, never real case
data. Zoom in on the evidence highlight and the rule name, because both are small
on screen and both are the moments that land. And close the terminal and dev
tools; a non-technical viewer reads any log output as an error.

## If you only have ninety seconds

Show the four-stage slide for ten seconds, submit the complete report, show the
four criteria, click one evidence quote, then open the escalated case and read the
"we do not guess" line aloud. That's the whole argument.

## Questions you'll be asked

**Is the AI making medical decisions?** No. It reads the report and points at what
it found. A fixed rulebook we own makes the decision, and a qualified person
approves it.

**What if the AI gets it wrong?** Every field shows the sentence it came from, so a
reviewer checks it in seconds instead of re-reading the whole report. And the AI
can't overrule the rulebook.

**Can it handle something it hasn't seen before?** If the information needed isn't
there, it escalates rather than guessing. That's designed behaviour, not a failure.

**Could we prove this to an inspector?** Every decision records which rule made it,
which version, and the evidence it relied on — and the trail can't be edited
afterwards.

**How many of those seven channels work today?** Two. Adding another is a
connector, not a rebuild.

**When do we get signal detection and the periodic reports?** They need reliable,
structured case data to work from, which is exactly what this stage produces. It's
why we built it first.

**What does it cost to run?** Fractions of a penny per report assessed.

**What happens to the voice conversation afterwards?** It should be archived as the
source document, so anything taken from it can be traced back. Worth confirming
that's wired up before go-live.

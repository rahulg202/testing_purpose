"""Synthetic FAERS-style dataset (Requirement 1).

Fixed seed => identical dataset every run. Causal features (onset, dechallenge,
rechallenge, confounders) live ONLY in the free-text narrative, never in
structured fields, so extraction is genuinely required.

Planted signals:
  - Hepatrix + Hepatotoxicity : true signal (clear timing, positive dechallenge)
  - Dormyl  + Pancreatitis    : confounded signal (alcohol, gallstones, co-meds)
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from datetime import date, timedelta

SEED = 42

DRUGS = ["Hepatrix", "Dormyl", "Cardiolin", "Nexamab", "Zelvora", "Plaxitin", "Oruvane", "Tamlesta"]
EVENTS = [
    "Hepatotoxicity", "Pancreatitis", "Rash", "Headache", "Nausea",
    "Dizziness", "Fatigue", "Insomnia", "Diarrhoea", "Arthralgia",
]
COUNTRIES = ["IN", "US", "GB", "DE", "FR", "JP", "BR", "CA"]


@dataclass(frozen=True)
class Report:
    report_id: str
    drug: str
    event: str
    age: int
    sex: str
    serious: bool
    country: str
    received_date: str
    narrative: str


def _patient(rng: random.Random, age: int, sex: str) -> str:
    noun = "woman" if sex == "F" else "man"
    return rng.choice([f"A {age}-year-old {noun}", f"The patient, a {age}-year-old {noun},", f"This {age}-year-old {noun}"])


def _background(rng: random.Random, drug: str, event: str, age: int, sex: str) -> str:
    who = _patient(rng, age, sex)
    ev = event.lower()
    templates = [
        f"{who} was receiving {drug} and reported {ev}. No further information was provided by the reporter.",
        f"{who} experienced {ev} while on {drug}. The outcome was reported as recovering. Medical history not reported.",
        f"Consumer report: {who} taking {drug} noticed {ev}. The reporter did not specify when symptoms started.",
        f"{who} started {drug} for an unspecified indication and later developed {ev}. Action taken with the drug was unknown.",
    ]
    return rng.choice(templates)


def _true_signal(rng: random.Random, drug: str, age: int, sex: str) -> str:
    who = _patient(rng, age, sex)
    onset = rng.randint(14, 45)
    alt = rng.randint(3, 12)
    parts = [
        f"{who} started {drug} 200 mg daily for chronic joint pain.",
        f"Approximately {onset} days after starting {drug}, the patient developed jaundice and fatigue.",
        f"Laboratory tests showed ALT elevated to {alt} times the upper limit of normal.",
        rng.choice([
            "Viral hepatitis serology was negative and the patient denied alcohol use.",
            "Hepatitis A, B and C serology were negative. No other hepatotoxic medications were taken.",
            "Abdominal ultrasound was unremarkable and there was no history of liver disease.",
        ]),
    ]
    if rng.random() < 0.85:
        weeks = rng.randint(2, 6)
        parts.append(f"{drug} was discontinued and liver enzymes returned to normal within {weeks} weeks.")
        if rng.random() < 0.3:
            parts.append(f"{drug} was later restarted by the patient and ALT rose again within 10 days, after which it was permanently stopped.")
    else:
        parts.append(f"The reporter did not state whether {drug} was stopped.")
    return " ".join(parts)


def _confounded(rng: random.Random, drug: str, age: int, sex: str) -> str:
    who = _patient(rng, age, sex)
    confounders = rng.sample([
        "The patient has a long history of heavy alcohol use, reporting around 8 drinks per day.",
        "Ultrasound revealed multiple gallstones with common bile duct dilatation.",
        "The patient was also taking azathioprine, which was started two weeks before the event.",
        "Serum triglycerides were markedly elevated at 1,450 mg/dL.",
        "The patient had a prior episode of pancreatitis three years earlier.",
    ], k=rng.choice([1, 2, 2, 3]))
    parts = [
        f"{who} started {drug} 10 mg at night for insomnia {rng.randint(3, 10)} weeks before presentation.",
        "The patient presented with severe epigastric pain and lipase was three times the upper limit of normal; acute pancreatitis was diagnosed.",
        *confounders,
        rng.choice([
            f"{drug} was continued throughout and the pancreatitis resolved with supportive care.",
            f"It is unknown whether {drug} was stopped.",
            f"The treating physician considered the event unrelated to {drug}.",
        ]),
    ]
    return " ".join(parts)


# ------------------------------------------------ additional planted signals ---
# Each is designed so the deterministic rules land on a different recommendation.

def _ild_true(rng: random.Random, drug: str, age: int, sex: str) -> str:
    """Nexamab + ILD: strong causal evidence, frequent positive rechallenge -> Validated."""
    who = _patient(rng, age, sex)
    parts = [f"{who} received {drug} infusions every 3 weeks for rheumatoid arthritis.",
             f"About {rng.randint(40, 90)} days after the first infusion the patient developed progressive dry cough and breathlessness.",
             "High-resolution CT showed bilateral ground-glass opacities consistent with interstitial lung disease.",
             rng.choice(["Infection was excluded by negative bronchoalveolar lavage cultures.",
                         "The patient was a lifelong non-smoker with no prior lung disease."]),
             f"{drug} was withdrawn and symptoms improved over the following {rng.randint(3, 8)} weeks."]
    if rng.random() < 0.5:
        parts.append(f"When {drug} was reintroduced, the cough and ground-glass changes recurred within two weeks.")
    return " ".join(parts)


def _qt_confounded(rng: random.Random, drug: str, age: int, sex: str) -> str:
    """Zelvora + QT prolongation: several QT-prolonging co-factors -> Not confirmed."""
    who = _patient(rng, age, sex)
    conf = rng.sample(["The patient was also taking citalopram 40 mg daily.",
                       "Ondansetron had been given intravenously the same morning.",
                       "Serum potassium was low at 2.9 mmol/L.",
                       "The patient has a documented family history of congenital long QT syndrome.",
                       "Methadone maintenance therapy was ongoing."], k=rng.choice([2, 2, 3]))
    return " ".join([f"{who} started {drug} for seasonal allergy.",
                     f"{rng.randint(2, 6)} days after starting {drug}, a routine ECG showed a QTc of {rng.randint(500, 540)} ms.",
                     *conf,
                     rng.choice([f"{drug} was continued and the QTc remained prolonged.",
                                 f"It was not reported whether {drug} was stopped."])])


def _sjs_true(rng: random.Random, drug: str, age: int, sex: str) -> str:
    """Plaxitin + SJS: typical latency, recovery after withdrawal -> Validated."""
    who = _patient(rng, age, sex)
    parts = [f"{who} started {drug} for partial seizures.",
             f"{rng.randint(7, 24)} days after starting {drug}, the patient developed fever, painful mucosal erosions and a blistering rash.",
             "A dermatologist diagnosed Stevens-Johnson syndrome covering about 8% of body surface area."]
    if rng.random() < 0.2:
        parts.append("The patient had also started allopurinol one week earlier.")
    parts.append(f"{drug} was stopped immediately and the skin lesions healed over {rng.randint(2, 5)} weeks.")
    return " ".join(parts)


def _aki_sparse(rng: random.Random, drug: str, age: int, sex: str) -> str:
    """Oruvane + AKI: poorly documented reports -> Insufficient information."""
    who = _patient(rng, age, sex)
    return rng.choice([
        f"{who} on {drug} was found to have acute kidney injury with raised creatinine. Dates of therapy were not provided.",
        f"Pharmacist report: {who} taking {drug} was hospitalised with acute kidney injury. No further details are available.",
        f"{who} developed acute kidney injury. The patient's medication list included {drug}. The reporter could not be contacted for follow-up.",
    ])


def _hypona_mixed(rng: random.Random, drug: str, age: int, sex: str) -> str:
    """Tamlesta + hyponatraemia: some clean cases, many with a diuretic -> Inconclusive."""
    who = _patient(rng, age, sex)
    parts = [f"{who} started {drug} for benign prostatic symptoms.",
             f"{rng.randint(10, 35)} days later, serum sodium was found to be {rng.randint(119, 128)} mmol/L with confusion."]
    if rng.random() < 0.6:
        parts.append("The patient was also taking hydrochlorothiazide 25 mg daily.")
        parts.append(rng.choice([f"{drug} was stopped and sodium normalised within a week.",
                                 f"It is unknown whether {drug} was stopped."]))
    else:
        parts.append(f"{drug} was stopped and sodium returned to normal within {rng.randint(4, 10)} days.")
    return " ".join(parts)


EXTRA_SIGNALS = [
    ("Nexamab", "Interstitial lung disease", _ild_true, 18),
    ("Zelvora", "QT prolongation", _qt_confounded, 20),
    ("Plaxitin", "Stevens-Johnson syndrome", _sjs_true, 16),
    ("Oruvane", "Acute kidney injury", _aki_sparse, 15),
    ("Tamlesta", "Hyponatraemia", _hypona_mixed, 20),
]


def generate(n_background: int = 1100, seed: int = SEED) -> list[Report]:
    rng = random.Random(seed)
    start = date(2025, 1, 1)
    reports: list[Report] = []

    def add(drug: str, event: str, narrative_fn) -> None:
        age = rng.randint(18, 85)
        sex = rng.choice(["F", "M"])
        reports.append(Report(
            report_id=f"R-{len(reports) + 1:05d}",
            drug=drug, event=event, age=age, sex=sex,
            serious=rng.random() < 0.35,
            country=rng.choice(COUNTRIES),
            received_date=(start + timedelta(days=rng.randint(0, 540))).isoformat(),
            narrative=narrative_fn(age, sex),
        ))

    for _ in range(n_background):
        # serious organ events are rarer in background reporting than headache/nausea
        drug, event = rng.choice(DRUGS), rng.choices(EVENTS, weights=[0.25, 0.25] + [1.0] * (len(EVENTS) - 2))[0]
        # keep the planted pairs from being diluted by vague background reports
        if (drug, event) in {("Hepatrix", "Hepatotoxicity"), ("Dormyl", "Pancreatitis")}:
            event = "Headache"
        add(drug, event, lambda a, s, d=drug, e=event: _background(rng, d, e, a, s))
    for _ in range(28):
        add("Hepatrix", "Hepatotoxicity", lambda a, s: _true_signal(rng, "Hepatrix", a, s))
    for _ in range(24):
        add("Dormyl", "Pancreatitis", lambda a, s: _confounded(rng, "Dormyl", a, s))

    # Appended after the original reports so their IDs and narratives are unchanged (cache stays valid)
    for drug, event, fn, n in EXTRA_SIGNALS:
        for _ in range(n):
            add(drug, event, lambda a, s, d=drug, f=fn: f(rng, d, a, s))
        for _ in range(4):  # a little background reporting of the same event with other drugs
            other = rng.choice([x for x in DRUGS if x != drug])
            add(other, event, lambda a, s, d=other, e=event: _background(rng, d, e, a, s))

    rng.shuffle(reports)
    return reports


def as_dicts(reports: list[Report]) -> list[dict]:
    return [asdict(r) for r in reports]

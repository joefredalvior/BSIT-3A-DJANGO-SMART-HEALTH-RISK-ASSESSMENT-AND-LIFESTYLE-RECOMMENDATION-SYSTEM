"""
Health Risk Assessment & Lifestyle Recommendation engine.

Produces a transparent, weighted risk score (0-100) from lifestyle and
biometric inputs, plus a banded risk level, personalised targets and
prioritised recommendations.

Clinical reference points (adult screening thresholds, not a diagnosis):
  BMI           WHO categories
  Blood pressure AHA / ACC categories
  Waist         WHO increased-risk cut-offs
  Waist-to-height ratio  NICE / WHO cut-offs (0.5 and 0.6)

The engine is pure: every function takes plain values and returns plain
values, so it can be unit-tested without touching the database.
"""

from dataclasses import dataclass, field

ENGINE_VERSION = "2.0"

# --- Tunables ---------------------------------------------------------------
# Every weight is a maximum number of points a single factor can contribute.
# The weights sum to 100, so a worst-case profile scores exactly 100.

WEIGHT_BMI = 12
WEIGHT_BLOOD_PRESSURE = 16
WEIGHT_WAIST = 9
WEIGHT_ACTIVITY = 12
WEIGHT_SMOKING = 13
WEIGHT_SLEEP = 7
WEIGHT_DIET = 8
WEIGHT_ALCOHOL = 5
WEIGHT_STRESS = 5
WEIGHT_FAMILY_HISTORY = 5
WEIGHT_CONDITIONS = 8

# Kept for backwards compatibility with callers that referenced the old name.
WEIGHT_WAIST_CIRCUMFERENCE = WEIGHT_WAIST

MAX_SCORE = (
    WEIGHT_BMI
    + WEIGHT_BLOOD_PRESSURE
    + WEIGHT_WAIST
    + WEIGHT_ACTIVITY
    + WEIGHT_SMOKING
    + WEIGHT_SLEEP
    + WEIGHT_DIET
    + WEIGHT_ALCOHOL
    + WEIGHT_STRESS
    + WEIGHT_FAMILY_HISTORY
    + WEIGHT_CONDITIONS
)


# --- Choice sets (values must stay in sync with the model field choices) ---

ACTIVITY_LEVELS = [
    ("sedentary", "Sedentary - little or no exercise"),
    ("light", "Lightly active - 1-3 days per week"),
    ("moderate", "Moderately active - 3-5 days per week"),
    ("active", "Very active - 6-7 days per week"),
]

SMOKING_STATUS = [
    ("never", "Never smoked"),
    ("former", "Former smoker"),
    ("occasional", "Occasional smoker"),
    ("current", "Current daily smoker"),
]

ALCOHOL_STATUS = [
    ("none", "Do not drink alcohol"),
    ("light", "1-3 drinks per week"),
    ("moderate", "4-14 drinks per week"),
    ("heavy", "15+ drinks per week"),
]

DIET_QUALITY = [
    ("poor", "Poor - heavily processed, low fruit/veg"),
    ("mixed", "Mixed - some fruit/veg, some processed food"),
    ("good", "Good - balanced, regular fruit and veg"),
]

SEX_CHOICES = [
    ("male", "Male"),
    ("female", "Female"),
]

BLOOD_PRESSURE_BANDS = [
    ("normal", "Normal - below 120/80"),
    ("elevated", "Elevated - 120-129 / below 80"),
    ("stage1", "Stage 1 hypertension - 130-139 / 80-89"),
    ("stage2", "Stage 2 hypertension - 140+ / 90+"),
    ("crisis", "Hypertensive crisis - over 180/120"),
]

FAMILY_HISTORY_CHOICES = [
    ("none", "No known family history"),
    ("cvd", "Family history of heart disease or stroke"),
    ("diabetes", "Family history of diabetes"),
    ("both", "Family history of heart disease and diabetes"),
]

CONDITION_CHOICES = [
    ("none", "None diagnosed"),
    ("prediabetes", "Prediabetes"),
    ("diabetes", "Type 2 diabetes"),
    ("hypertension", "High blood pressure"),
    ("heart", "Heart disease"),
    ("kidney", "Kidney disease"),
]

STRESS_CHOICES = [
    ("low", "Low - generally calm"),
    ("moderate", "Moderate - some pressure most weeks"),
    ("high", "High - frequently overwhelmed"),
]


# --- Result containers ------------------------------------------------------

@dataclass
class Finding:
    """A single scored observation contributing to the overall risk."""

    key: str
    label: str
    points: int
    max_points: int
    band: str
    detail: str
    advice: str
    target: str
    category: str = "Lifestyle"
    modifiable: bool = True

    @property
    def percentage(self):
        if not self.max_points:
            return 0
        return int(round((self.points / self.max_points) * 100))


@dataclass
class Assessment:
    score: int
    level: str
    bmi: float
    bmi_category: str
    whtr: float
    whtr_category: str
    age_factor: float
    findings: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    top_recommendations: list = field(default_factory=list)
    targets: list = field(default_factory=list)


RISK_LOW = "Low"
RISK_MODERATE = "Moderate"
RISK_HIGH = "High"
RISK_CRITICAL = "Critical"

LEVEL_COLOURS = {
    RISK_LOW: "success",
    RISK_MODERATE: "warning",
    RISK_HIGH: "danger",
    RISK_CRITICAL: "purple",
}

LEVEL_SUMMARY = {
    RISK_LOW: (
        "Your current lifestyle indicators are within recommended ranges. "
        "Keep up the habits that are working for you."
    ),
    RISK_MODERATE: (
        "Some of your indicators fall outside recommended ranges. Small, "
        "consistent changes now can meaningfully reduce your long-term risk."
    ),
    RISK_HIGH: (
        "Several indicators are in the high-risk range. Please prioritise the "
        "changes below and speak with a healthcare professional."
    ),
    RISK_CRITICAL: (
        "One or more indicators are in a range that needs prompt medical "
        "attention. Please contact your doctor or nearest clinic as soon as "
        "possible, regardless of the lifestyle changes listed here."
    ),
}

MEDICAL_DISCLAIMER = (
    "This assessment is an educational screening aid only. It is not a "
    "medical diagnosis and does not replace professional medical advice. "
    "Always consult a qualified healthcare provider before starting a new "
    "treatment or exercise programme."
)


# --- Helpers ----------------------------------------------------------------

def calculate_bmi(weight_kg, height_cm):
    """Return BMI rounded to 1dp. Returns None for impossible inputs."""
    try:
        weight_kg = float(weight_kg)
        height_cm = float(height_cm)
    except (TypeError, ValueError):
        return None
    if weight_kg <= 0 or height_cm <= 0:
        return None
    metres = height_cm / 100.0
    return round(weight_kg / (metres * metres), 1)


def bmi_category(bmi):
    if bmi is None:
        return "Unknown"
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Healthy weight"
    if bmi < 30:
        return "Overweight"
    if bmi < 35:
        return "Obesity class I"
    if bmi < 40:
        return "Obesity class II"
    return "Obesity class III"


def bmi_points(bmi):
    """0 = healthy. Scales up with how far into the risk band the BMI sits."""
    if bmi is None:
        return 0, "We could not calculate your BMI from the values entered."

    if bmi < 18.5:
        return min(max(2, int((18.5 - bmi) * 3)), WEIGHT_BMI), (
            f"Your BMI of {bmi} is in the underweight range (below 18.5). "
            "Low body weight can weaken immunity and bone health."
        )
    if bmi < 25:
        return 0, f"Your BMI of {bmi} is in the healthy weight range (18.5-24.9)."

    over = bmi - 25
    points = min(int(over * 1.2) + 2, WEIGHT_BMI)
    return points, (
        f"Your BMI of {bmi} is {bmi_category(bmi).lower()} (25.0 and above). "
        "Excess body weight raises the risk of type 2 diabetes, heart disease "
        "and joint problems."
    )


def calculate_whtr(waist_cm, height_cm):
    """Waist-to-height ratio. Healthy is below 0.5 for most adults."""
    try:
        waist_cm = float(waist_cm)
        height_cm = float(height_cm)
    except (TypeError, ValueError):
        return None
    if waist_cm <= 0 or height_cm <= 0:
        return None
    return round(waist_cm / height_cm, 2)


def whtr_category(ratio):
    if ratio is None:
        return "Unknown"
    if ratio < 0.4:
        return "Low"
    if ratio < 0.5:
        return "Healthy"
    if ratio < 0.6:
        return "Increased"
    return "High"


def whtr_points(ratio):
    if ratio is None:
        return 0
    if ratio < 0.5:
        return 0
    if ratio < 0.6:
        return min(int((ratio - 0.5) / 0.05) + 3, WEIGHT_WAIST)
    return WEIGHT_WAIST


def waist_points(waist_cm, sex):
    """WHO cut-offs: >=94 cm (male) / >=80 cm (female) = increased risk."""
    try:
        waist_cm = float(waist_cm)
    except (TypeError, ValueError):
        return 0, "Waist measurement not provided."

    limit = 94 if sex == "male" else 80
    if waist_cm < limit:
        return 0, (
            f"Your waist measurement of {waist_cm} cm is below the "
            f"{limit} cm increased-risk threshold."
        )

    points = min(int((waist_cm - limit) / 5) + 3, WEIGHT_WAIST)
    return points, (
        f"Your waist measurement of {waist_cm} cm exceeds the {limit} cm "
        "threshold for increased cardiovascular risk. Waist circumference "
        "reflects visceral fat, which is not always visible in overall weight."
    )


def blood_pressure_band(systolic, diastolic):
    """Derive the clinical band from the raw reading, so the stored band can
    never disagree with the stored numbers."""
    try:
        systolic = float(systolic)
        diastolic = float(diastolic)
    except (TypeError, ValueError):
        return "normal"
    if systolic >= 180 or diastolic >= 120:
        return "crisis"
    if systolic >= 140 or diastolic >= 90:
        return "stage2"
    if systolic >= 130 or diastolic >= 80:
        return "stage1"
    if systolic >= 120:
        return "elevated"
    return "normal"


def blood_pressure_points(systolic, diastolic):
    """Points driven by whichever reading is worse, using clinical categories."""
    try:
        systolic = float(systolic)
        diastolic = float(diastolic)
    except (TypeError, ValueError):
        return 0, "Blood pressure not provided."

    if systolic >= 180 or diastolic >= 120:
        return WEIGHT_BLOOD_PRESSURE, (
            f"Your reading of {int(systolic)}/{int(diastolic)} is in the "
            "hypertensive crisis range (180/120 or above). This needs urgent "
            "medical attention."
        )
    if systolic >= 140 or diastolic >= 90:
        return max(int(WEIGHT_BLOOD_PRESSURE * 0.85), 1), (
            f"Your reading of {int(systolic)}/{int(diastolic)} is in the "
            "stage 2 hypertension range (140/90 or above)."
        )
    if systolic >= 130 or diastolic >= 80:
        return max(int(WEIGHT_BLOOD_PRESSURE * 0.5), 1), (
            f"Your reading of {int(systolic)}/{int(diastolic)} is in the "
            "stage 1 hypertension range (130-139/80-89)."
        )
    if systolic >= 120:
        return max(int(WEIGHT_BLOOD_PRESSURE * 0.2), 1), (
            f"Your reading of {int(systolic)}/{int(diastolic)} is elevated "
            "(120-129 systolic)."
        )
    return 0, (
        f"Your reading of {int(systolic)}/{int(diastolic)} is in the normal "
        "range (below 120/80)."
    )


ACTIVITY_ADVICE = {
    "active": "You are meeting the recommended 150 minutes of activity per week.",
    "moderate": "You are close to the recommended 150 minutes of activity per week.",
    "light": "Aim to build up to at least 150 minutes of moderate activity per week.",
    "sedentary": "Build up gradually - even a 10-minute walk daily is a strong start.",
}

SMOKING_ADVICE = {
    "never": "You have never smoked. Keep it that way - it is the single largest "
             "preventable health risk.",
    "former": "You have quit, which is excellent. Quitting at any age lowers risk.",
    "occasional": "Even occasional smoking carries risk. Work towards quitting completely.",
    "current": "Quitting smoking is the single most effective step you can take. "
               "Support programmes and nicotine replacement are available.",
}

SLEEP_ADVICE = {
    "short": "Aim for 7-9 hours. Short sleep raises blood pressure and weight gain risk.",
    "normal": "You are getting an adequate amount of sleep (7-9 hours).",
    "long": "Aim for 7-9 hours. Consistently long sleep is also linked to health risks.",
}

DIET_ADVICE = {
    "poor": "Increase fruit and vegetables to at least 5 portions a day and cut back "
            "on highly processed foods.",
    "mixed": "Good start. Aim for 5 or more portions of fruit and vegetables daily.",
    "good": "Your diet is balanced - keep it up.",
}

ALCOHOL_ADVICE = {
    "none": "Staying alcohol-free is the healthiest option.",
    "light": "Your intake is within low-risk limits. Keep it that way.",
    "moderate": "Reduce intake to no more than 14 units per week.",
    "heavy": "Your intake is well above recommended limits. Please seek support to "
             "reduce this - cutting back significantly lowers liver and cardiovascular risk.",
}

STRESS_ADVICE = {
    "low": "Your stress level is low. Keep using the routines that help you unwind.",
    "moderate": "Build regular recovery time into your week - walking, breathing "
                "exercises or talking to someone you trust.",
    "high": "High stress affects blood pressure, sleep and eating patterns. Consider "
            "speaking with a counsellor or your doctor for support.",
}

FAMILY_HISTORY_ADVICE = {
    "none": "No known family history was reported.",
    "cvd": "Share your family history of heart disease with your doctor so they can "
           "advise on screening intervals.",
    "diabetes": "Ask your doctor when you should be screened for diabetes, given your "
                "family history.",
    "both": "Discuss both cardiovascular and diabetes screening with your doctor.",
}

CONDITION_ADVICE = {
    "none": "No diagnosed condition was reported.",
    "prediabetes": "Prediabetes can often be reversed. Focus on activity, diet and "
                   "regular check-ups to prevent progression.",
    "diabetes": "Keep blood glucose, blood pressure and cholesterol within the targets "
                "set by your care team.",
    "hypertension": "Monitor your blood pressure at home and take medication exactly as "
                    "prescribed.",
    "heart": "Follow your cardiology care plan, including medication, activity and diet.",
    "kidney": "Kidney health benefits from controlled blood pressure, blood sugar and "
              "reduced salt intake.",
}


def age_factor(age):
    """Cardiometabolic risk rises with age, so metabolic factor points are
    weighted modestly for older adults. This never adds a new factor."""
    try:
        age = float(age)
    except (TypeError, ValueError):
        return 1.0
    if age >= 65:
        return 1.22
    if age >= 55:
        return 1.15
    if age >= 40:
        return 1.08
    return 1.0


def activity_points(level):
    scores = {
        "active": 0,
        "moderate": int(WEIGHT_ACTIVITY * 0.3),
        "light": int(WEIGHT_ACTIVITY * 0.6),
        "sedentary": WEIGHT_ACTIVITY,
    }
    return scores.get(level, 0)


SMOKING_POINTS = {
    "never": 0,
    "former": int(WEIGHT_SMOKING * 0.3),
    "occasional": int(WEIGHT_SMOKING * 0.6),
    "current": WEIGHT_SMOKING,
}


def sleep_points(hours):
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        return 0
    if hours < 5:
        return WEIGHT_SLEEP
    if hours < 6:
        return int(WEIGHT_SLEEP * 0.7)
    if hours < 7:
        return int(WEIGHT_SLEEP * 0.4)
    if hours > 10:
        return int(WEIGHT_SLEEP * 0.7)
    if hours > 9:
        return int(WEIGHT_SLEEP * 0.4)
    return 0


def diet_points(quality, fruit_veg_servings=None):
    base = {"good": 0, "mixed": int(WEIGHT_DIET * 0.6), "poor": WEIGHT_DIET}.get(quality, 0)
    try:
        servings = int(float(fruit_veg_servings))
    except (TypeError, ValueError):
        servings = None
    if servings is not None:
        if servings < 3:
            base += 2
        elif servings < 5:
            base += 1
    return min(base, WEIGHT_DIET)


def alcohol_points(level):
    return {
        "none": 0,
        "light": 0,
        "moderate": int(WEIGHT_ALCOHOL * 0.6),
        "heavy": WEIGHT_ALCOHOL,
    }.get(level, 0)


def stress_points(level):
    return {
        "low": 0,
        "moderate": int(WEIGHT_STRESS * 0.6),
        "high": WEIGHT_STRESS,
    }.get(level, 0)


def family_history_points(history):
    return {
        "none": 0,
        "cvd": int(WEIGHT_FAMILY_HISTORY * 0.6),
        "diabetes": int(WEIGHT_FAMILY_HISTORY * 0.6),
        "both": WEIGHT_FAMILY_HISTORY,
    }.get(history, 0)


def conditions_points(condition):
    return {
        "none": 0,
        "prediabetes": int(WEIGHT_CONDITIONS * 0.5),
        "hypertension": int(WEIGHT_CONDITIONS * 0.75),
        "diabetes": WEIGHT_CONDITIONS,
        "heart": WEIGHT_CONDITIONS,
        "kidney": WEIGHT_CONDITIONS,
    }.get(condition, 0)


def hours_band(hours):
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        return "normal"
    if hours < 6:
        return "short"
    if hours > 9:
        return "long"
    return "normal"


def _scaled(points, maximum, factor):
    """Apply the age weighting without ever exceeding the factor weight."""
    return min(max(int(round(points * factor)), 0), maximum)


# --- Recommendation library -------------------------------------------------

RECOMMENDATION_LIBRARY = {
    "bmi": {
        "title": "Reach a healthier weight",
        "category": "Metabolic",
        "timeframe": "12-24 weeks",
        "steps": [
            "Choose one small, sustainable change you can repeat daily.",
            "Aim for a mix of aerobic activity and resistance training.",
            "Track your weight weekly rather than daily to avoid noise.",
        ],
    },
    "blood_pressure": {
        "title": "Lower your blood pressure",
        "category": "Cardiovascular",
        "timeframe": "4-12 weeks",
        "steps": [
            "Reduce added salt and processed foods high in sodium.",
            "Measure your blood pressure at a consistent time each day.",
            "Book a review with your doctor if readings stay high.",
        ],
    },
    "waist": {
        "title": "Reduce abdominal fat",
        "category": "Metabolic",
        "timeframe": "8-12 weeks",
        "steps": [
            "Add 150 minutes of moderate activity each week.",
            "Include two resistance sessions to build lean muscle.",
            "Limit sugary drinks and refined carbohydrates.",
        ],
    },
    "activity": {
        "title": "Move more each week",
        "category": "Lifestyle",
        "timeframe": "Ongoing",
        "steps": [
            "Start with a 10-minute walk after meals.",
            "Build towards 150 minutes of moderate activity weekly.",
            "Break activity into short blocks when time is tight.",
        ],
    },
    "smoking": {
        "title": "Stop smoking",
        "category": "Lifestyle",
        "timeframe": "Start now",
        "steps": [
            "Set a quit date within the next two weeks.",
            "Ask your doctor about nicotine replacement or medication.",
            "Tell someone you trust so they can support you.",
        ],
    },
    "sleep": {
        "title": "Improve your sleep",
        "category": "Lifestyle",
        "timeframe": "2-4 weeks",
        "steps": [
            "Keep a consistent sleep and wake time, including weekends.",
            "Avoid screens and caffeine close to bedtime.",
            "Keep the bedroom cool, dark and quiet.",
        ],
    },
    "diet": {
        "title": "Improve your diet quality",
        "category": "Lifestyle",
        "timeframe": "4-8 weeks",
        "steps": [
            "Aim for five portions of fruit and vegetables each day.",
            "Swap one processed meal per day for a home-cooked option.",
            "Choose water instead of sugary drinks.",
        ],
    },
    "alcohol": {
        "title": "Cut back on alcohol",
        "category": "Lifestyle",
        "timeframe": "4-12 weeks",
        "steps": [
            "Plan alcohol-free days each week.",
            "Keep no more than 14 units per week, spread across days.",
            "Seek support if cutting back feels difficult.",
        ],
    },
    "stress": {
        "title": "Manage stress",
        "category": "Lifestyle",
        "timeframe": "2-6 weeks",
        "steps": [
            "Schedule a short daily wind-down routine.",
            "Use breathing or grounding exercises when tension rises.",
            "Talk to a counsellor if stress is affecting daily life.",
        ],
    },
    "family_history": {
        "title": "Discuss screening with your doctor",
        "category": "Clinical",
        "timeframe": "At your next visit",
        "steps": [
            "Write down which relatives were affected and at what age.",
            "Ask about earlier or more frequent screening.",
            "Share the family history with any new clinician.",
        ],
    },
    "conditions": {
        "title": "Manage your existing condition",
        "category": "Clinical",
        "timeframe": "Ongoing",
        "steps": [
            "Take medication exactly as prescribed.",
            "Keep regular review appointments with your care team.",
            "Track the readings or symptoms your clinician asks about.",
        ],
    },
}


# --- Targets ----------------------------------------------------------------

def healthy_weight_range(height_cm):
    try:
        metres = float(height_cm) / 100.0
    except (TypeError, ValueError):
        return None, None
    if metres <= 0:
        return None, None
    return (
        round(18.5 * metres * metres, 1),
        round(24.9 * metres * metres, 1),
    )


def build_targets(*, height_cm, weight_kg, waist_cm, sex, systolic, diastolic,
                  sleep_hours, activity_level, fruit_veg_servings):
    low, high = healthy_weight_range(height_cm)
    waist_limit = 94 if sex == "male" else 80

    weight_status = "good"
    if low is None or high is None:
        weight_status = "unknown"
    else:
        try:
            if not (low <= float(weight_kg) <= high):
                weight_status = "warning"
        except (TypeError, ValueError):
            weight_status = "unknown"

    try:
        waist_ok = float(waist_cm) < waist_limit
    except (TypeError, ValueError):
        waist_ok = False

    bp_ok = blood_pressure_band(systolic, diastolic) == "normal"

    try:
        sleep_ok = 7 <= float(sleep_hours) <= 9
    except (TypeError, ValueError):
        sleep_ok = False

    activity_ok = activity_level in ("moderate", "active")

    try:
        fruit_ok = int(float(fruit_veg_servings)) >= 5
    except (TypeError, ValueError):
        fruit_ok = False

    return [
        {
            "label": "Weight",
            "current": f"{weight_kg} kg",
            "target": f"{low}-{high} kg" if low is not None else "Healthy BMI range",
            "status": "good" if weight_status == "good" else "warning",
        },
        {
            "label": "Waist",
            "current": f"{waist_cm} cm",
            "target": f"below {waist_limit} cm",
            "status": "good" if waist_ok else "warning",
        },
        {
            "label": "Blood pressure",
            "current": f"{systolic}/{diastolic} mmHg",
            "target": "below 120/80 mmHg",
            "status": "good" if bp_ok else "warning",
        },
        {
            "label": "Sleep",
            "current": f"{sleep_hours} h",
            "target": "7-9 hours per night",
            "status": "good" if sleep_ok else "warning",
        },
        {
            "label": "Physical activity",
            "current": dict(ACTIVITY_LEVELS).get(activity_level, "Not provided"),
            "target": "150+ minutes per week",
            "status": "good" if activity_ok else "warning",
        },
        {
            "label": "Fruit & vegetables",
            "current": f"{fruit_veg_servings} servings/day",
            "target": "5+ servings/day",
            "status": "good" if fruit_ok else "warning",
        },
    ]


# --- Main entry point -------------------------------------------------------

def assess(*, age, sex, height_cm, weight_kg, waist_cm, systolic,
           diastolic, activity_level, smoking_status, alcohol_status,
           diet_quality, sleep_hours, family_history="none",
           conditions="none", stress_level="low", fruit_veg_servings=5):
    """
    Build an Assessment from raw health inputs.

    The score is the sum of points contributed by each factor, normalised so
    the worst possible case lands at 100. Age is applied as a modest multiplier
    to cardiometabolic factors rather than as a separate scored factor.
    """
    findings = []
    factor = age_factor(age)

    bmi = calculate_bmi(weight_kg, height_cm)
    bmi_cat = bmi_category(bmi)
    whtr = calculate_whtr(waist_cm, height_cm)
    whtr_cat = whtr_category(whtr)
    low_weight, high_weight = healthy_weight_range(height_cm)
    waist_limit = 94 if sex == "male" else 80

    def add(key, label, points, maximum, band, detail, advice, target,
            category="Lifestyle", modifiable=True, age_weighted=False):
        if points <= 0:
            return
        if age_weighted:
            detail = f"{detail} (weighted for age)"
        findings.append(Finding(
            key=key,
            label=label,
            points=points,
            max_points=maximum,
            band=band,
            detail=detail,
            advice=advice,
            target=target,
            category=category,
            modifiable=modifiable,
        ))

    # Body mass index
    pts, detail = bmi_points(bmi)
    add("bmi", "Body mass index", _scaled(pts, WEIGHT_BMI, factor), WEIGHT_BMI,
        bmi_cat, detail,
        "Work towards a BMI in the healthy range through a balanced diet and "
        "regular activity. Gradual change is more sustainable than rapid loss.",
        f"BMI {low_weight}-{high_weight}" if low_weight is not None else "Healthy BMI range",
        category="Metabolic", age_weighted=pts > 0)

    # Blood pressure
    pts, detail = blood_pressure_points(systolic, diastolic)
    add("blood_pressure", "Blood pressure",
        _scaled(pts, WEIGHT_BLOOD_PRESSURE, factor), WEIGHT_BLOOD_PRESSURE,
        blood_pressure_band(systolic, diastolic), detail,
        "Reduce salt intake, stay active, and monitor your reading regularly. "
        "If readings stay high, speak with your doctor about treatment.",
        "Below 120/80 mmHg", category="Cardiovascular", age_weighted=pts > 0)

    # Waist circumference and waist-to-height ratio. Use the worse of the two
    # so the same fat deposit is not counted twice.
    waist_pts, waist_detail = waist_points(waist_cm, sex)
    whtr_pts = whtr_points(whtr)
    waist_total = max(waist_pts, whtr_pts)
    waist_detail = (
        f"{waist_detail} Waist-to-height ratio is {whtr} ({whtr_cat.lower()}; "
        "healthy is below 0.50)."
        if whtr is not None else waist_detail
    )
    add("waist", "Waist circumference", _scaled(waist_total, WEIGHT_WAIST, factor),
        WEIGHT_WAIST, whtr_cat, waist_detail,
        "Combine aerobic exercise with resistance training to reduce visceral "
        "fat. Waist size often improves before overall weight changes.",
        f"Below {waist_limit} cm",
        category="Metabolic", age_weighted=waist_total > 0)

    # Physical activity
    pts = activity_points(activity_level)
    add("activity", "Physical activity", pts, WEIGHT_ACTIVITY, activity_level,
        f"Your reported activity level is: "
        f"{dict(ACTIVITY_LEVELS).get(activity_level, 'unknown')}.",
        ACTIVITY_ADVICE.get(activity_level, ""),
        "150+ minutes per week")

    # Smoking
    pts = SMOKING_POINTS.get(smoking_status, 0)
    add("smoking", "Smoking", pts, WEIGHT_SMOKING, smoking_status,
        f"Your smoking status: "
        f"{dict(SMOKING_STATUS).get(smoking_status, 'unknown')}.",
        SMOKING_ADVICE.get(smoking_status, ""),
        "Not smoking", category="Lifestyle")

    # Sleep
    pts = sleep_points(sleep_hours)
    add("sleep", "Sleep", pts, WEIGHT_SLEEP, hours_band(sleep_hours),
        f"You reported {sleep_hours} hours of sleep per night.",
        SLEEP_ADVICE.get(hours_band(sleep_hours), ""),
        "7-9 hours per night")

    # Diet
    pts = diet_points(diet_quality, fruit_veg_servings)
    add("diet", "Diet", pts, WEIGHT_DIET, diet_quality,
        f"Your diet quality: {dict(DIET_QUALITY).get(diet_quality, 'unknown')}. "
        f"You reported {fruit_veg_servings} servings of fruit and vegetables per day.",
        DIET_ADVICE.get(diet_quality, ""),
        "5+ fruit and vegetable servings per day")

    # Alcohol
    pts = alcohol_points(alcohol_status)
    add("alcohol", "Alcohol", pts, WEIGHT_ALCOHOL, alcohol_status,
        f"Your alcohol intake: "
        f"{dict(ALCOHOL_STATUS).get(alcohol_status, 'unknown')}.",
        ALCOHOL_ADVICE.get(alcohol_status, ""),
        "No more than 14 units per week")

    # Stress
    pts = stress_points(stress_level)
    add("stress", "Stress", pts, WEIGHT_STRESS, stress_level,
        f"Your reported stress level: "
        f"{dict(STRESS_CHOICES).get(stress_level, 'unknown')}.",
        STRESS_ADVICE.get(stress_level, ""),
        "Daily recovery time")

    # Family history
    pts = family_history_points(family_history)
    add("family_history", "Family history", pts, WEIGHT_FAMILY_HISTORY,
        family_history,
        f"Family history: "
        f"{dict(FAMILY_HISTORY_CHOICES).get(family_history, 'unknown')}.",
        FAMILY_HISTORY_ADVICE.get(family_history, ""),
        "Agreed screening schedule",
        category="Clinical", modifiable=False)

    # Existing conditions
    pts = conditions_points(conditions)
    add("conditions", "Existing conditions",
        _scaled(pts, WEIGHT_CONDITIONS, factor), WEIGHT_CONDITIONS, conditions,
        f"Diagnosed condition: "
        f"{dict(CONDITION_CHOICES).get(conditions, 'unknown')}.",
        CONDITION_ADVICE.get(conditions, ""),
        "Within care-plan targets",
        category="Clinical", modifiable=False, age_weighted=pts > 0)

    raw = sum(f.points for f in findings)
    score = min(int(round((raw / MAX_SCORE) * 100)), 100)

    if score < 25:
        level = RISK_LOW
    elif score < 50:
        level = RISK_MODERATE
    elif score < 75:
        level = RISK_HIGH
    else:
        level = RISK_CRITICAL

    findings.sort(key=lambda f: (-f.points, f.label))

    recommendations = []
    for finding in findings:
        library = RECOMMENDATION_LIBRARY.get(finding.key, {})
        recommendations.append({
            "key": finding.key,
            "title": library.get("title", finding.label),
            "category": library.get("category", finding.category),
            "points_saved": finding.points,
            "priority": 0,
            "advice": finding.advice,
            "target": finding.target,
            "timeframe": library.get("timeframe", "Ongoing"),
            "action_steps": library.get("steps", [finding.advice]),
            "modifiable": finding.modifiable,
        })

    # Highest score impact first; ties favour factors the user can change.
    recommendations.sort(
        key=lambda r: (-r["points_saved"], not r["modifiable"], r["title"])
    )
    for index, rec in enumerate(recommendations, start=1):
        rec["priority"] = index

    targets = build_targets(
        height_cm=height_cm,
        weight_kg=weight_kg,
        waist_cm=waist_cm,
        sex=sex,
        systolic=systolic,
        diastolic=diastolic,
        sleep_hours=sleep_hours,
        activity_level=activity_level,
        fruit_veg_servings=fruit_veg_servings,
    )

    return Assessment(
        score=score,
        level=level,
        bmi=bmi,
        bmi_category=bmi_cat,
        whtr=whtr,
        whtr_category=whtr_cat,
        age_factor=factor,
        findings=findings,
        recommendations=recommendations,
        top_recommendations=recommendations[:3],
        targets=targets,
    )

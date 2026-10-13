"""
Health Risk Assessment & Lifestyle Recommendation engine.

Produces a transparent, weighted risk score (0-100) from lifestyle and
biometric inputs, plus a banded risk level and personalised recommendations.

Clinical reference points (adult screening thresholds, not a diagnosis):
  BMI           WHO categories
  Blood press.  AHA / ACC categories
  Waist         WHO increased-risk cut-offs
"""

from dataclasses import dataclass, field


# --- Tunables ---------------------------------------------------------------

WEIGHT_BMI = 20
WEIGHT_BLOOD_PRESSURE = 20
WEIGHT_WAIST = 10
WEIGHT_ACTIVITY = 15
WEIGHT_SMOKING = 15
WEIGHT_SLEEP = 10
WEIGHT_DIET = 5
WEIGHT_ALCOHOL = 5

MAX_SCORE = (
    WEIGHT_BMI
    + WEIGHT_BLOOD_PRESSURE
    + WEIGHT_WAIST
    + WEIGHT_ACTIVITY
    + WEIGHT_SMOKING
    + WEIGHT_SLEEP
    + WEIGHT_DIET
    + WEIGHT_ALCOHOL
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


# --- Result containers ------------------------------------------------------

@dataclass
class Finding:
    """A single scored observation contributing to the overall risk."""
    label: str
    points: int
    detail: str
    advice: str


@dataclass
class Assessment:
    score: int
    level: str
    bmi: float
    bmi_category: str
    findings: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)


RISK_LOW = "Low"
RISK_MODERATE = "Moderate"
RISK_HIGH = "High"
RISK_CRITICAL = "Critical"

# Tabler status colours
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
        return max(2, int((18.5 - bmi) * 3)), (
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


def activity_points(level):
    scores = {
        "active": 0,
        "moderate": int(WEIGHT_ACTIVITY * 0.3),
        "light": int(WEIGHT_ACTIVITY * 0.6),
        "sedentary": WEIGHT_ACTIVITY,
    }
    return scores.get(level, 0)


ACTIVITY_ADVICE = {
    "active": "You are meeting the recommended 150 minutes of activity per week.",
    "moderate": "You are close to the recommended 150 minutes of activity per week.",
    "light": "Aim to build up to at least 150 minutes of moderate activity per week.",
    "sedentary": "Build up gradually - even a 10-minute walk daily is a strong start.",
}

SMOKING_POINTS = {
    "never": 0,
    "former": int(WEIGHT_SMOKING * 0.3),
    "occasional": int(WEIGHT_SMOKING * 0.6),
    "current": WEIGHT_SMOKING,
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


def diet_points(quality):
    return {"good": 0, "mixed": int(WEIGHT_DIET * 0.6), "poor": WEIGHT_DIET}.get(quality, 0)


def alcohol_points(level):
    return {
        "none": 0,
        "light": 0,
        "moderate": int(WEIGHT_ALCOHOL * 0.6),
        "heavy": WEIGHT_ALCOHOL,
    }.get(level, 0)


# --- Main entry point -------------------------------------------------------

def assess(*, age, sex, height_cm, weight_kg, waist_cm, systolic,
           diastolic, activity_level, smoking_status, alcohol_status,
           diet_quality, sleep_hours):
    """
    Build an Assessment from raw health inputs.

    The score is the sum of points contributed by each factor, normalised so
    the worst possible case lands at 100.
    """
    findings = []
    recommendations = []

    def add(label, points, detail, advice):
        if points > 0:
            findings.append(Finding(label, points, detail, advice))
            recommendations.append((label, advice))

    bmi = calculate_bmi(weight_kg, height_cm)

    pts, detail = bmi_points(bmi)
    add("Body mass index", pts, detail,
        "Work towards a BMI in the healthy range through a balanced diet and "
        "regular activity. Gradual change is more sustainable than rapid loss.")

    pts, detail = blood_pressure_points(systolic, diastolic)
    add("Blood pressure", pts, detail,
        "Reduce salt intake, stay active, and monitor your reading regularly. "
        "If readings stay high, speak with your doctor about treatment.")

    pts, detail = waist_points(waist_cm, sex)
    add("Waist circumference", pts, detail,
        "Combine aerobic exercise with resistance training to reduce visceral "
        "fat. Waist size often improves before overall weight changes.")

    pts = activity_points(activity_level)
    add("Physical activity", pts,
        f"Your reported activity level is: {dict(ACTIVITY_LEVELS).get(activity_level, 'unknown')}.",
        ACTIVITY_ADVICE.get(activity_level, ""))

    pts = SMOKING_POINTS.get(smoking_status, 0)
    add("Smoking", pts,
        f"Your smoking status: {dict(SMOKING_STATUS).get(smoking_status, 'unknown')}.",
        SMOKING_ADVICE.get(smoking_status, ""))

    pts = sleep_points(sleep_hours)
    add("Sleep", pts,
        f"You reported {sleep_hours} hours of sleep per night.",
        SLEEP_ADVICE.get(hours_band(sleep_hours), ""))

    pts = diet_points(diet_quality)
    add("Diet", pts,
        f"Your diet quality: {dict(DIET_QUALITY).get(diet_quality, 'unknown')}.",
        DIET_ADVICE.get(diet_quality, ""))

    pts = alcohol_points(alcohol_status)
    add("Alcohol", pts,
        f"Your alcohol intake: {dict(ALCOHOL_STATUS).get(alcohol_status, 'unknown')}.",
        ALCOHOL_ADVICE.get(alcohol_status, ""))

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

    # Order recommendations by how much they would reduce the score.
    recommendations.sort(key=lambda item: item[1], reverse=True)

    return Assessment(
        score=score,
        level=level,
        bmi=bmi,
        bmi_category=bmi_category(bmi),
        findings=findings,
        recommendations=[{"title": t, "advice": a} for t, a in recommendations],
    )


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
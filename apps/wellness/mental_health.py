PHQ9_QUESTIONS = [
    'Little interest or pleasure in doing things',
    'Feeling down, depressed, or hopeless',
    'Trouble falling or staying asleep, or sleeping too much',
    'Feeling tired or having little energy',
    'Poor appetite or overeating',
    'Feeling bad about yourself or that you are a failure',
    'Trouble concentrating on things',
    'Moving or speaking slowly, or being fidgety/restless',
    'Thoughts that you would be better off dead or of hurting yourself',
]

GAD7_QUESTIONS = [
    'Feeling nervous, anxious, or on edge',
    'Not being able to stop or control worrying',
    'Worrying too much about different things',
    'Trouble relaxing',
    'Being so restless that it is hard to sit still',
    'Becoming easily annoyed or irritable',
    'Feeling afraid as if something awful might happen',
]

ANSWER_CHOICES = [
    (0, 'Not at all'),
    (1, 'Several days'),
    (2, 'More than half the days'),
    (3, 'Nearly every day'),
]

SCREENINGS = {
    'phq9': {
        'title': 'PHQ-9 depression screening',
        'questions': PHQ9_QUESTIONS,
        'max_score': 27,
    },
    'gad7': {
        'title': 'GAD-7 anxiety screening',
        'questions': GAD7_QUESTIONS,
        'max_score': 21,
    },
}


def severity_for(kind, score):
    if kind == 'phq9':
        if score <= 4:
            return 'minimal'
        if score <= 9:
            return 'mild'
        if score <= 14:
            return 'moderate'
        if score <= 19:
            return 'moderately_severe'
        return 'severe'
    if score <= 4:
        return 'minimal'
    if score <= 9:
        return 'mild'
    if score <= 14:
        return 'moderate'
    return 'severe'


def guidance_for(kind, severity):
    if severity in ('minimal', 'mild'):
        return 'Your responses suggest a low level of symptoms. Keep using the coping and self-care habits that work for you.'
    if severity == 'moderate':
        return 'Your responses suggest moderate symptoms. Consider speaking with a clinician or counsellor about how you are feeling.'
    return 'Your responses suggest significant symptoms. Please contact a healthcare professional or crisis service soon. If you are in immediate danger, contact local emergency services.'

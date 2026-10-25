"""Small, rule-based lifestyle plan used on the report page.

This is educational content, not a prescribed diet or exercise programme.
"""


def build_plan(record):
    bmi = record.bmi or 0
    activity = record.activity_level
    conditions = record.conditions
    servings = record.fruit_veg_servings or 0

    if bmi >= 30:
        plate = 'Fill half the plate with vegetables, a quarter with lean protein, and a quarter with whole grains.'
        snack = 'Choose fruit or plain yoghurt instead of sweetened snacks.'
    elif bmi >= 25:
        plate = 'Use the half-plate vegetable guide and keep portions moderate.'
        snack = 'Keep a small handful of nuts or a piece of fruit ready for hungry moments.'
    else:
        plate = 'Keep a balanced plate: vegetables, lean protein, and whole grains.'
        snack = 'Fruit, nuts, or yoghurt are simple everyday snacks.'

    if conditions == 'diabetes':
        plate += ' Choose high-fibre carbohydrates and avoid sugary drinks.'
        snack = 'Pair fruit with protein (for example, apple slices with peanut butter).'
    elif conditions == 'hypertension':
        plate += ' Limit salty sauces, processed meats, and instant noodles.'
        snack = 'Choose unsalted nuts or fresh fruit.'

    if servings < 5:
        produce_tip = 'Add one extra serving of vegetables or fruit to two meals today.'
    else:
        produce_tip = 'Keep your current fruit and vegetable routine going.'

    meals = [
        {
            'name': 'Breakfast',
            'idea': 'Oats or whole-grain bread with egg, tomato, and a piece of fruit.',
            'note': 'Water or unsweetened tea instead of sugary drinks.',
        },
        {
            'name': 'Lunch',
            'idea': 'Rice or root vegetable with fish/chicken, lentils, and plenty of vegetables.',
            'note': plate,
        },
        {
            'name': 'Dinner',
            'idea': 'Vegetable soup or stir-fry with lean protein and a modest grain portion.',
            'note': 'Try to finish eating 2-3 hours before bedtime.',
        },
        {
            'name': 'Snack',
            'idea': snack,
            'note': produce_tip,
        },
    ]

    if activity == 'sedentary':
        weekly_minutes = 90
        sessions = 'Start with 10-15 minute walks, 3 days this week.'
    elif activity == 'light':
        weekly_minutes = 150
        sessions = 'Build toward 30 minutes of moderate activity on 5 days.'
    elif activity == 'moderate':
        weekly_minutes = 200
        sessions = 'Keep 30-40 minute sessions and add one longer walk.'
    else:
        weekly_minutes = 250
        sessions = 'Maintain your routine and include one strength session.'

    if bmi >= 30:
        sessions += ' Choose low-impact activity such as walking, cycling, or swimming.'
    elif bmi >= 25:
        sessions += ' A brisk walk after meals is an easy way to add movement.'

    return {
        'meals': meals,
        'activity': {
            'weekly_minutes': weekly_minutes,
            'sessions': sessions,
            'examples': [
                'Brisk walking',
                'Cycling or stationary bike',
                'Bodyweight strength (sit-to-stand, wall push-ups)',
                'Stretching or mobility work',
            ],
        },
        'note': 'General wellness suggestions only. Ask your clinician before changing your diet or exercise, especially with a medical condition.',
    }

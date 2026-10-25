from .models import Achievement


BADGES = {
    'first_assessment': ('First check-in', 'Completed your first health assessment.', 'fa-heart-pulse'),
    'assessments_5': ('Consistent tracker', 'Completed five health assessments.', 'fa-repeat'),
    'first_vital': ('Vitals starter', 'Logged your first vital reading.', 'fa-chart-line'),
    'vitals_10': ('Data-driven', 'Logged ten vital readings.', 'fa-chart-simple'),
    'first_goal': ('Goal setter', 'Created your first health goal.', 'fa-bullseye'),
    'goals_3': ('Focused planner', 'Created three active health goals.', 'fa-list-check'),
    'profile_complete': ('Profile complete', 'Added your baseline health details.', 'fa-id-card'),
    'screening_done': ('Mind check', 'Completed a mental health screening.', 'fa-brain'),
}


def award_achievements(user):
    """Award any milestones the user has newly reached. Safe to call often."""
    if not user.is_authenticated:
        return []

    earned = []
    assessment_count = user.assessments.count()
    if assessment_count >= 1:
        earned.append('first_assessment')
    if assessment_count >= 5:
        earned.append('assessments_5')

    vital_count = user.vital_readings.count()
    if vital_count >= 1:
        earned.append('first_vital')
    if vital_count >= 10:
        earned.append('vitals_10')

    goal_count = user.health_goals.filter(is_active=True).count()
    if goal_count >= 1:
        earned.append('first_goal')
    if goal_count >= 3:
        earned.append('goals_3')

    profile = getattr(user, 'profile', None)
    if profile and profile.birthdate and profile.sex and profile.height_cm:
        earned.append('profile_complete')

    if user.mental_health_screenings.exists():
        earned.append('screening_done')

    created = []
    for code in earned:
        if code not in BADGES:
            continue
        title, description, icon = BADGES[code]
        _, was_created = Achievement.objects.get_or_create(
            user=user,
            code=code,
            defaults={'title': title, 'description': description, 'icon': icon},
        )
        if was_created:
            created.append(code)
    return created

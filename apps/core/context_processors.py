from django.core.exceptions import ObjectDoesNotExist

from .translations import LANGUAGE_NAMES, TRANSLATIONS


def account_state(request):
    """Expose the signed-in user's profile without creating rows per request."""
    if not request.user.is_authenticated:
        return {'account_profile': None}
    try:
        profile = request.user.profile
    except ObjectDoesNotExist:
        profile = None
    return {'account_profile': profile}


def ui_language(request):
    lang = request.session.get('ui_language', 'en')
    if lang not in TRANSLATIONS:
        lang = 'en'
    other = 'fil' if lang == 'en' else 'en'
    unread_messages = 0
    if request.user.is_authenticated:
        try:
            unread_messages = request.user.received_secure_messages.filter(read_at__isnull=True).count()
        except Exception:
            unread_messages = 0
    return {
        'LANG': lang,
        'UI': TRANSLATIONS[lang],
        'OTHER_LANG': other,
        'OTHER_LANG_NAME': LANGUAGE_NAMES[other],
        'UNREAD_MESSAGES': unread_messages,
    }

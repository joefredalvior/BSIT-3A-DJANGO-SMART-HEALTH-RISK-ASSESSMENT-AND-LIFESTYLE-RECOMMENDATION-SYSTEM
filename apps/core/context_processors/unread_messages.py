from apps.core.models import Message


def unread_message_count(request):
    """Return the count of unread messages for the current user."""
    if request.user.is_authenticated:
        return {
            'unread_messages': Message.objects.filter(
                recipient=request.user,
                is_read=False
            ).count()
        }
    return {'unread_messages': 0}
from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import Territory


@receiver(m2m_changed, sender=Territory.neighbors.through)
def guard_territory_neighbors(sender, instance, action, model, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    if instance.pk in pk_set:
        raise ValidationError("Територия не може да е съседна на себе си.")
    if model.objects.filter(pk__in=pk_set).exclude(game_id=instance.game_id).exists():
        raise ValidationError("Съседните територии трябва да са от същата игра.")

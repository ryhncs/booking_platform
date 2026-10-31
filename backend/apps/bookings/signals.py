"""Invalidate cached availability whenever anything it is derived from changes.

Availability for a staff member depends on their bookings, shifts, time off,
the services they offer (duration, active flag, who offers it), their own
active flag, and the business timezone. Using model signals rather than
sprinkling calls through the service layer also covers edits made through the
admin or the owner API.

Bulk ``QuerySet.update()`` / ``bulk_create()`` bypass signals; code that uses
them on these models must call ``availability.invalidate_staff`` itself.
"""

from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete
from django.dispatch import receiver

from apps.businesses.models import Business, Service, Staff, TimeOff, WorkingHours

from .availability import invalidate_staff_after_commit
from .models import Booking


def _invalidate(staff_ids) -> None:
    for staff_id in set(staff_ids):
        invalidate_staff_after_commit(staff_id)


@receiver([post_save, post_delete], sender=Booking)
@receiver([post_save, post_delete], sender=WorkingHours)
@receiver([post_save, post_delete], sender=TimeOff)
def staff_scoped_row_changed(sender, instance, **kwargs):
    _invalidate([instance.staff_id])


@receiver([post_save, post_delete], sender=Staff)
def staff_changed(sender, instance, **kwargs):
    _invalidate([instance.pk])


@receiver(post_save, sender=Business)
def business_changed(sender, instance, created, **kwargs):
    if not created:  # e.g. a timezone change moves every slot of every staff member
        _invalidate(instance.staff.values_list("pk", flat=True))


@receiver(post_save, sender=Service)
def service_saved(sender, instance, created, **kwargs):
    if not created:  # a new service has no staff yet; m2m_changed covers attaching them
        _invalidate(instance.staff.values_list("pk", flat=True))


@receiver(pre_delete, sender=Service)
def service_deleting(sender, instance, **kwargs):
    # pre_delete: by post_delete the m2m rows are already gone.
    _invalidate(instance.staff.values_list("pk", flat=True))


@receiver(m2m_changed, sender=Service.staff.through)
def service_staff_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "pre_clear"}:
        return
    if reverse:  # staff.services.add(...): instance is the Staff
        _invalidate([instance.pk])
    elif action == "pre_clear":  # service.staff.clear(): pk_set is None, read before it empties
        _invalidate(instance.staff.values_list("pk", flat=True))
    else:
        _invalidate(pk_set)

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User


class IsOwnerOrReadOnly(BasePermission):
    """Any authenticated user may read the catalog; only owners may write.

    Which *objects* an owner may write is decided by scoping the queryset
    (see ``CatalogViewSet``), so other owners' objects simply 404.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or user.role == User.Role.OWNER

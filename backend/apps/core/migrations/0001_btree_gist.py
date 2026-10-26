from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Enable btree_gist.

    The overlap exclusion constraints combine a range (GiST-native) with an
    equality check on a plain integer column (staff_id). Mixing the two in one
    GiST index requires the btree_gist extension.
    """

    initial = True
    dependencies = []
    operations = [BtreeGistExtension()]

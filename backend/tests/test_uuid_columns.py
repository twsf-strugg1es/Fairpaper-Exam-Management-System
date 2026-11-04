"""Ids come back from the test database unchanged, even ones whose hex reads as a number."""
import uuid

import pytest

from app import models


@pytest.mark.parametrize("org_id", [
    uuid.UUID("12345678-9012-4345-8789-0123456e8901"),  # a huge exponent: SQLite would store inf
    uuid.UUID("12345678-9012-4345-8789-012345678901"),  # all digits: SQLite would store a float
], ids=["exponent", "digits"])
def test_ids_that_read_as_numbers_come_back_unchanged(test_db, org_id):
    test_db.add(models.Organization(id=org_id, name="Numbers"))
    test_db.commit()
    test_db.expire_all()

    assert test_db.query(models.Organization).one().id == org_id

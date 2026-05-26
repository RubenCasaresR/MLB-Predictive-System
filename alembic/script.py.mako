"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from typing import Sequence, Union
from alembic import op
import logging

logger = logging.getLogger(__name__)

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "logger.info('No upgrade steps defined')"}


def downgrade() -> None:
    ${downgrades if downgrades else "logger.info('No downgrade steps defined')"}

"""Operator commands, run on a machine with database access.

    python -m app.cli grant-role you@example.com admin
    python -m app.cli list-admins

The first admin has to come from somewhere that is not the web: either this
command or ``PDE_BOOTSTRAP_ADMIN_EMAILS``. Both are server-side; nothing a browser
sends can create one.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.session import sessionmaker
from app.models.user import ROLES, AuditLog, User


async def grant_role(email: str, role: str) -> str:
    async with sessionmaker()() as db:
        user = await db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user is None:
            return f"No account for {email}. Sign up first, then run this again."
        previous = user.role
        user.role = role
        db.add(
            AuditLog(
                actor_user_id=None,
                action=f"role_change_cli:{previous}->{role}",
                entity="user",
                entity_id=user.id,
                at=datetime.now(UTC),
            )
        )
        await db.commit()
        return f"{email}: {previous} -> {role}"


async def list_admins() -> str:
    async with sessionmaker()() as db:
        emails = (await db.scalars(select(User.email).where(User.role == "admin"))).all()
        return "\n".join(emails) or "No admins yet."


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    grant = commands.add_parser("grant-role", help="Set a user's role")
    grant.add_argument("email")
    grant.add_argument("role", choices=ROLES)
    commands.add_parser("list-admins", help="List admin accounts")
    args = parser.parse_args()
    if args.command == "grant-role":
        print(asyncio.run(grant_role(args.email, args.role)))
    else:
        print(asyncio.run(list_admins()))


if __name__ == "__main__":
    main()

import re

import asyncpg
import bcrypt

DB_DSN = "postgresql://plantbot:plantbot@localhost:5432/plantchatbot"

MIN_USERNAME_LENGTH = 3
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_BYTES = 72
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")


def _validate_credentials(identifier: str, password: str) -> str | None:
    identifier = identifier.strip()
    if len(identifier) < MIN_USERNAME_LENGTH:
        return f"Kullanıcı adı en az {MIN_USERNAME_LENGTH} karakter olmalı."
    if not USERNAME_PATTERN.match(identifier):
        return "Kullanıcı adı yalnızca harf, rakam, nokta, tire ve alt çizgi içerebilir."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Şifre en az {MIN_PASSWORD_LENGTH} karakter olmalı."
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return "Şifre çok uzun."
    return None


async def register_user(identifier: str, password: str) -> tuple[bool, str]:
    identifier = identifier.strip()
    error = _validate_credentials(identifier, password)
    if error:
        return False, error

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = await asyncpg.connect(DB_DSN)
    try:
        try:
            await conn.execute(
                """
                INSERT INTO users (id, identifier, "createdAt", metadata, password_hash)
                VALUES (gen_random_uuid(), $1, now()::text, '{}'::jsonb, $2)
                """,
                identifier,
                password_hash,
            )
        except asyncpg.UniqueViolationError:
            return False, "Bu kullanıcı adı zaten alınmış."
        return True, "Kayıt başarılı. Şimdi giriş yapabilirsiniz."
    finally:
        await conn.close()


async def verify_user(identifier: str, password: str) -> bool:
    identifier = identifier.strip()
    if not identifier or not password:
        return False

    conn = await asyncpg.connect(DB_DSN)
    try:
        row = await conn.fetchrow(
            'SELECT password_hash FROM users WHERE identifier = $1', identifier
        )
    finally:
        await conn.close()

    if not row or not row["password_hash"]:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8"))

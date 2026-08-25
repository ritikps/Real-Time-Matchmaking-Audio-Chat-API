"""
Redis-backed waiting pool for real-time matchmaking.

The waiting pool is stored directly in Redis as:

    user_id -> preference JSON

A Redis lock is used so two users cannot match with the same waiting user
at the same time.
"""

import json

import redis.asyncio as redis

from django.conf import settings


POOL_KEY = "matchmaking:waiting_pool"
LOCK_KEY = "matchmaking:pool_lock"


def _get_client():
    """
    Create a Redis client from REDIS_URL.

    Local development:
        redis://127.0.0.1:6379

    Production:
        rediss://default:<password>@<upstash-host>:6379
    """

    redis_url = getattr(settings, "REDIS_URL", None)

    if not redis_url:
        raise RuntimeError(
            "REDIS_URL is not configured. "
            "Set REDIS_URL in your environment variables."
        )

    return redis.from_url(
        redis_url,
        decode_responses=True,
    )


def _compatible(me: dict, other: dict) -> bool:
    """
    Mutual-preference check:
    gender + age range must satisfy both users.
    """

    if (
        me["preferred_gender"]
        and other["gender"] != me["preferred_gender"]
    ):
        return False

    if (
        other["preferred_gender"]
        and me["gender"] != other["preferred_gender"]
    ):
        return False

    if not (
        me["min_age_pref"]
        <= other["age"]
        <= me["max_age_pref"]
    ):
        return False

    if not (
        other["min_age_pref"]
        <= me["age"]
        <= other["max_age_pref"]
    ):
        return False

    return True


async def find_and_lock_match(user_id: int, prefs: dict):
    """
    Atomically look for a compatible waiting user.

    If a compatible user is found, remove both users from the waiting pool
    while holding a Redis lock.

    Returns:
        matched user's ID
        or None if no compatible user is waiting.
    """

    r = _get_client()

    matched_id = None

    try:
        async with r.lock(
            LOCK_KEY,
            timeout=5,
            blocking_timeout=2,
        ):
            pool = await r.hgetall(POOL_KEY)

            for other_id_str, other_json in pool.items():

                other_id = int(other_id_str)

                if other_id == user_id:
                    continue

                other = json.loads(other_json)

                if _compatible(prefs, other):

                    await r.hdel(
                        POOL_KEY,
                        str(user_id),
                        str(other_id),
                    )

                    matched_id = other_id
                    break

    finally:
        await r.aclose()

    return matched_id


async def join_pool(user_id: int, prefs: dict):
    """
    Add a user to the matchmaking waiting pool.
    """

    r = _get_client()

    try:
        await r.hset(
            POOL_KEY,
            str(user_id),
            json.dumps(prefs),
        )
    finally:
        await r.aclose()


async def leave_pool(user_id: int):
    """
    Remove a user from the matchmaking waiting pool.
    """

    r = _get_client()

    try:
        await r.hdel(
            POOL_KEY,
            str(user_id),
        )
    finally:
        await r.aclose()
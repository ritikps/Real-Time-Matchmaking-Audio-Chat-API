"""
Redis-backed waiting pool for real-time matchmaking.

Channels' built-in channel layer is a pub/sub broadcast mechanism — it's
great for delivering a message to a known group, but it can't answer
"who else is currently waiting and what are their preferences?". That
requires a queryable shared data structure, so the waiting pool is kept
directly in Redis (separate from the Channels layer) as a hash of
user_id -> preference JSON, guarded by a Redis lock so two consumers
checking the pool at the same instant can never both match the same
third user.
"""
import json

import redis.asyncio as redis
from django.conf import settings

POOL_KEY = "matchmaking:waiting_pool"
LOCK_KEY = "matchmaking:pool_lock"

# NOTE: the Redis client is created lazily (per-call) rather than as a
# module-level singleton. redis-asyncio's connection pool is bound to the
# event loop that created it; a module-level client would break the moment
# it's reused from a *different* event loop (e.g. Django's async test
# runner, which spins up a fresh loop per test method), raising
# "RuntimeError: Event loop is closed". Building a lightweight client per
# call sidesteps that entirely and is cheap enough at this scale.
def _get_client():
    host, port = settings.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"][0]
    return redis.Redis(host=host, port=port, decode_responses=True)


def _compatible(me: dict, other: dict) -> bool:
    """Mutual-preference check: gender + age range must satisfy both sides."""
    if me["preferred_gender"] and other["gender"] != me["preferred_gender"]:
        return False
    if other["preferred_gender"] and me["gender"] != other["preferred_gender"]:
        return False
    if not (me["min_age_pref"] <= other["age"] <= me["max_age_pref"]):
        return False
    if not (other["min_age_pref"] <= me["age"] <= other["max_age_pref"]):
        return False
    return True


async def find_and_lock_match(user_id: int, prefs: dict):
    """
    Atomically: look for a compatible waiting user, and if found, remove
    BOTH users from the pool so no one else can also match with them.
    Returns the matched user's id, or None if no one currently waiting fits.
    """
    r = _get_client()
    matched_id = None
    async with r.lock(LOCK_KEY, timeout=5, blocking_timeout=2):
        pool = await r.hgetall(POOL_KEY)
        for other_id_str, other_json in pool.items():
            other_id = int(other_id_str)
            if other_id == user_id:
                continue
            other = json.loads(other_json)
            if _compatible(prefs, other):
                await r.hdel(POOL_KEY, str(user_id), str(other_id))
                matched_id = other_id
                break
    await r.aclose()
    return matched_id


async def join_pool(user_id: int, prefs: dict):
    r = _get_client()
    await r.hset(POOL_KEY, str(user_id), json.dumps(prefs))
    await r.aclose()


async def leave_pool(user_id: int):
    r = _get_client()
    await r.hdel(POOL_KEY, str(user_id))
    await r.aclose()

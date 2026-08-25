"""
Benchmarks the discovery query with vs without the composite index on
(gender, age, is_online), on a realistically sized profile table, to get
a real number for the resume claim instead of an invented one.
"""
import os, django, time, random
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test.runner import DiscoverRunner
from django.db import connection

runner = DiscoverRunner()
old_config = runner.setup_databases()

from django.contrib.auth import get_user_model
from accounts.models import Profile

User = get_user_model()

N = 20000
print(f"Seeding {N} profiles...")
genders = ["M", "F", "O"]
users = []
for i in range(N):
    u = User(username=f"bench_{i}")
    users.append(u)
User.objects.bulk_create(users, batch_size=2000)

user_ids = list(User.objects.values_list("id", flat=True))
profiles = []
for i, uid in enumerate(user_ids):
    profiles.append(Profile(
        user_id=uid,
        display_name=f"user{i}",
        age=random.randint(18, 60),
        gender=random.choice(genders),
        preferred_gender=random.choice(genders + [""]),
        min_age_pref=18, max_age_pref=99,
        is_online=random.random() < 0.3,
    ))
Profile.objects.bulk_create(profiles, batch_size=2000)
print("Seeded.")

def run_query():
    list(Profile.objects.filter(is_online=True, age__gte=25, age__lte=35, gender="F")[:50])

# Warm up
run_query()

def timeit(label, n=200):
    start = time.perf_counter()
    for _ in range(n):
        run_query()
    elapsed = time.perf_counter() - start
    per_query_ms = (elapsed / n) * 1000
    print(f"{label}: {per_query_ms:.3f} ms/query (avg over {n} runs)")
    return per_query_ms

with_index_ms = timeit("WITH composite index")

with connection.cursor() as cursor:
    cursor.execute("DROP INDEX IF EXISTS idx_profile_discovery")

without_index_ms = timeit("WITHOUT index (dropped)")

pct = (without_index_ms - with_index_ms) / without_index_ms * 100
print(f"\nLatency reduction from index: {pct:.1f}%")

runner.teardown_databases(old_config)

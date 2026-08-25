from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Profile

User = get_user_model()


class AuthAndProfileTests(APITestCase):
    def register(self, username="alice", gender="F"):
        resp = self.client.post("/api/auth/register/", {
            "username": username,
            "email": f"{username}@example.com",
            "password": "supersecret123",
            "display_name": username.title(),
            "age": 24,
            "gender": gender,
        })
        return resp

    def login(self, username="alice", password="supersecret123"):
        resp = self.client.post("/api/auth/login/", {"username": username, "password": password})
        return resp.data["access"]

    def test_register_creates_user_and_profile(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(User.objects.filter(username="alice").exists())
        self.assertTrue(Profile.objects.filter(user__username="alice").exists())

    def test_login_returns_jwt(self):
        self.register()
        resp = self.client.post("/api/auth/login/", {"username": "alice", "password": "supersecret123"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_profile_requires_auth(self):
        resp = self.client.get("/api/profile/me/")
        self.assertEqual(resp.status_code, 401)

    def test_profile_get_and_update(self):
        self.register()
        token = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = self.client.get("/api/profile/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["display_name"], "Alice")

        resp = self.client.patch("/api/profile/me/", {"preferred_gender": "M", "min_age_pref": 20, "max_age_pref": 30})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["preferred_gender"], "M")

    def test_discovery_excludes_self_and_filters_by_preference(self):
        # alice (F, prefers M) and bob (M) and carol (F)
        self.register("alice", gender="F")
        self.register("bob", gender="M")
        self.register("carol", gender="F")

        for uname in ["alice", "bob", "carol"]:
            p = Profile.objects.get(user__username=uname)
            p.is_online = True
            p.save()

        alice_profile = Profile.objects.get(user__username="alice")
        alice_profile.preferred_gender = "M"
        alice_profile.save()

        token = self.login("alice")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/discovery/")

        self.assertEqual(resp.status_code, 200)
        usernames = {row["username"] for row in resp.data}
        self.assertIn("bob", usernames)
        self.assertNotIn("carol", usernames)   # wrong gender for alice's preference
        self.assertNotIn("alice", usernames)   # never see yourself

from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Profile
from core.asgi import application

User = get_user_model()


def make_user(username, gender, preferred_gender, age=25):
    user = User.objects.create_user(username=username, password="pass12345")
    Profile.objects.create(
        user=user, display_name=username, age=age, gender=gender,
        preferred_gender=preferred_gender, min_age_pref=18, max_age_pref=99,
    )
    return user


class MatchmakingConsumerTests(TransactionTestCase):
    async def _connect(self, user):
        token = str(AccessToken.for_user(user))
        communicator = WebsocketCommunicator(application, f"/ws/matchmaking/?token={token}")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    async def test_two_compatible_users_get_matched(self):
        from channels.db import database_sync_to_async

        alice = await database_sync_to_async(make_user)("alice_ws", "F", "M")
        bob = await database_sync_to_async(make_user)("bob_ws", "M", "F")

        alice_ws = await self._connect(alice)
        first = await alice_ws.receive_json_from()
        self.assertEqual(first["type"], "waiting")

        bob_ws = await self._connect(bob)

        bob_event = await bob_ws.receive_json_from()
        alice_event = await alice_ws.receive_json_from()

        self.assertEqual(bob_event["type"], "match_found")
        self.assertEqual(alice_event["type"], "match_found")
        self.assertEqual(bob_event["room_name"], alice_event["room_name"])
        self.assertEqual(bob_event["partner_id"], alice.id)
        self.assertEqual(alice_event["partner_id"], bob.id)

        await alice_ws.disconnect()
        await bob_ws.disconnect()

    async def test_signal_relay_between_matched_peers(self):
        from channels.db import database_sync_to_async

        alice = await database_sync_to_async(make_user)("alice_sig", "F", "M")
        bob = await database_sync_to_async(make_user)("bob_sig", "M", "F")

        alice_ws = await self._connect(alice)
        await alice_ws.receive_json_from()  # waiting
        bob_ws = await self._connect(bob)
        await bob_ws.receive_json_from()    # match_found for bob
        await alice_ws.receive_json_from()  # match_found for alice

        await alice_ws.send_json_to({"type": "signal", "payload": {"sdp": "fake-offer"}})
        relayed = await bob_ws.receive_json_from()
        self.assertEqual(relayed["type"], "signal")
        self.assertEqual(relayed["payload"]["sdp"], "fake-offer")

        await alice_ws.disconnect()
        await bob_ws.disconnect()

    async def test_incompatible_users_stay_waiting(self):
        from channels.db import database_sync_to_async

        # both explicitly only want to match with men -> mutually incompatible
        alice = await database_sync_to_async(make_user)("alice_incompat", "F", "M")
        carol = await database_sync_to_async(make_user)("carol_incompat", "F", "M")

        alice_ws = await self._connect(alice)
        self.assertEqual((await alice_ws.receive_json_from())["type"], "waiting")

        carol_ws = await self._connect(carol)
        self.assertEqual((await carol_ws.receive_json_from())["type"], "waiting")

        self.assertTrue(await alice_ws.receive_nothing(timeout=0.2))

        await alice_ws.disconnect()
        await carol_ws.disconnect()

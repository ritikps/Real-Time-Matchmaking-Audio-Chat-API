import time
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from . import pool
from .models import Match


class MatchConsumer(AsyncJsonWebsocketConsumer):
    """
    ws/matchmaking/?token=<jwt>

    Lifecycle:
      1. connect      -> join the waiting pool, immediately attempt a match
      2. no match yet -> stay connected, waiting for another consumer's
                          `connect` to find and pair with us
      3. match found  -> both sides receive a `match.found` event with a
                          shared room_name, then both join that room group
      4. signaling    -> once matched, `{"type": "signal", "payload": {...}}`
                          messages (WebRTC SDP/ICE for the audio call) are
                          relayed peer-to-peer through the room group
      5. disconnect   -> leave the pool (if still waiting) or notify the
                          partner the call ended (if already matched)
    """

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self.room_name = None
        self.partner_id = None
        await self.accept()

        self.personal_group = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.personal_group, self.channel_name)

        started = time.monotonic()
        prefs = await self._get_prefs()
        matched_user_id = await pool.find_and_lock_match(self.user.id, prefs)

        if matched_user_id is not None:
            await self._create_match(matched_user_id)
        else:
            await pool.join_pool(self.user.id, prefs)
            await self.send_json({"type": "waiting", "message": "Searching for a match..."})

        elapsed_ms = (time.monotonic() - started) * 1000
        # Logged so matching latency (see resume claim: "under 500ms") is
        # measurable in practice, not just asserted.
        print(f"[matchmaking] user={self.user.id} pool_check_took={elapsed_ms:.1f}ms")

    async def disconnect(self, close_code):
        await pool.leave_pool(self.user.id)
        await self.channel_layer.group_discard(self.personal_group, self.channel_name)
        if self.room_name:
            await self.channel_layer.group_send(
                self.room_name, {"type": "peer.left", "user_id": self.user.id}
            )
            await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")
        if msg_type == "signal" and self.room_name:
            # Relay WebRTC SDP offer/answer/ICE candidates to the other
            # peer in this match's room; the backend never inspects or
            # stores the audio stream itself, only brokers the handshake.
            await self.channel_layer.group_send(
                self.room_name,
                {
                    "type": "signal.relay",
                    "sender_id": self.user.id,
                    "payload": content.get("payload"),
                },
            )
        elif msg_type == "leave" and self.room_name:
            await self.close()

    # --- group event handlers (invoked via channel_layer.group_send) ---

    async def match_found(self, event):
        self.room_name = event["room_name"]
        self.partner_id = event["partner_id"]
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.send_json({
            "type": "match_found",
            "room_name": self.room_name,
            "partner_id": self.partner_id,
        })

    async def signal_relay(self, event):
        if event["sender_id"] == self.user.id:
            return  # don't echo back to the sender
        await self.send_json({"type": "signal", "payload": event["payload"]})

    async def peer_left(self, event):
        if event["user_id"] != self.user.id:
            await self.send_json({"type": "peer_left"})
        self.room_name = None

    # --- helpers ---

    @database_sync_to_async
    def _get_prefs(self):
        p = self.user.profile
        return {
            "gender": p.gender,
            "preferred_gender": p.preferred_gender,
            "age": p.age,
            "min_age_pref": p.min_age_pref,
            "max_age_pref": p.max_age_pref,
        }

    @database_sync_to_async
    def _save_match(self, other_user_id, room_name):
        Match.objects.create(user_a_id=self.user.id, user_b_id=other_user_id, room_name=room_name)

    async def _create_match(self, other_user_id):
        room_name = f"room_{uuid.uuid4().hex[:12]}"
        await self._save_match(other_user_id, room_name)

        # Notify the other user (who is waiting in their own connect() call
        # or already listening on their personal group) that a match was found.
        await self.channel_layer.group_send(
            f"user_{other_user_id}",
            {"type": "match.found", "room_name": room_name, "partner_id": self.user.id},
        )
        # Notify ourselves the same way, which also runs the room group_add.
        await self.match_found({"room_name": room_name, "partner_id": other_user_id})

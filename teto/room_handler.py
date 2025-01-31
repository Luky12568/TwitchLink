from typing import TYPE_CHECKING, Optional, Dict, Any, List, TypedDict

if TYPE_CHECKING:
    from .ribbon_client import RibbonClient

class ChatMessage(TypedDict):
    content: str
    content_safe: str
    user: Dict[str, Any]
    pinned: bool
    system: bool

class RoomHandler:
    def __init__(self, client: 'RibbonClient'):
        self.client = client
        self.current_room: Optional[str] = None

    async def setup_handlers(self):
        await self.client.register_handler("room.chat", self.handle_chat)
        await self.client.register_handler("room.update", self.handle_update)
        await self.client.register_handler("room.player.add", self.handle_player_add)
        await self.client.register_handler("room.player.remove", self.handle_player_remove)
        await self.client.register_handler("room.join", self.handle_join)

    async def join_room(self, room_id: str) -> None:
        """Join a room by ID"""
        await self.client.send_message("room.join", room_id)
        self.current_room = room_id

    async def leave_room(self) -> None:
        """Leave the current room"""
        if self.current_room:
            await self.client.send_message("room.leave", {})
            self.current_room = None

    async def send_chat(self, message: str) -> None:
        """Send a chat message in the current room"""
        if not self.current_room:
            raise ValueError("Not in a room")
        await self.client.send_message("room.chat.send", {
            "content": message
        })

    async def handle_join(self, data: Dict[str, Any]) -> None:
        """Handle room join events"""
        print(f"Joined room: {data}")

    async def handle_leave(self, data: Dict[str, Any]) -> None:
        """Handle room leave events"""
        await self.client.send_message("room.leave", None)
        self.current_room = None

    async def handle_chat(self, data: ChatMessage) -> None:
        """Handle chat messages"""
        # ignore own messages and system messages
        if data["system"] or (data["user"]["_id"] == self.client.id):
            return
            
        await self.client.emit("client.room.chat", data)

    async def handle_update(self, data: Dict[str, Any]) -> None:
        """Handle room update events"""
        print(f"Room update: {data}")

    async def handle_player_add(self, data: Dict[str, Any]) -> None:
        """Handle player join events"""
        print(f"Player joined: {data}")
        await self.client.emit("client.room.player.add", data)

    async def handle_player_remove(self, data: Dict[str, Any]) -> None:
        """Handle player leave events"""
        print(f"Player left: {data}")

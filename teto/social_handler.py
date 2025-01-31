from typing import TYPE_CHECKING, Optional, Dict, Any

if TYPE_CHECKING:
    from .ribbon_client import RibbonClient

class SocialHandler:
    def __init__(self, client: 'RibbonClient'):
        self.client = client

    async def setup_handlers(self):
        await self.client.register_handler("social.notification", self.handle_notification)
        await self.client.register_handler("social.dm", self.handle_dm)
        await self.client.register_handler("social.invite", self.handle_invite)
        await self.client.register_handler("social.online", self.handle_online)

    async def send_dm(self, user_id: str, message: str) -> None:
        """Send a direct message to a user"""
        await self.client.send_message("social.dm", {
            "recipient": user_id,
            "msg": message
        })

    async def set_presence(self, status: str = "online", detail: str = "menus") -> None:
        """Update the bot's presence status"""
        await self.client.send_message("social.presence", {
            "status": status,
            "detail": detail
        })

    async def handle_notification(self, data: Dict[str, Any]) -> None:
        await self.client.emit('notification', data)

    async def handle_dm(self, data: Dict[str, Any]) -> None:
        message_data = data.get('data', {})
        if message_data['user'] == self.client.id:
            return  
        await self.client.emit('client.social.dm', {
            'user': message_data.get('user'),
            'content': message_data.get('content'),
            'system': message_data.get('system', False),
            'raw': data
        })

    async def handle_invite(self, data: Dict[str, Any]) -> None:
        print(data)
        if data['sender'] == self.client.id:
            return  
        await self.client.emit('client.social.invite', data)

    async def handle_online(self, data: Dict[str, Any]) -> None:
        await self.client.emit('client.social.online', data)

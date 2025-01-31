import asyncio
import websockets
import json
import aiohttp
import sys 
import signal 
from typing import Optional, Callable, Any, Dict, List
from collections import deque
from dataclasses import dataclass

BOT_CONFIG = { # replace with your bot's config but this is fine for initial connections
    "name": "twitchlink",
    "version": "1.0.0",
    "siteURL": "https://ch.tetr.io/u/twitchlink" 
}

USER_AGENT = f"Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; {BOT_CONFIG['name']}/{BOT_CONFIG['version']}; +{BOT_CONFIG['siteURL']}) tetrio-botclient/129.0.0.0 Safari/537.36"

@dataclass
class Environment:
    signature: dict

@dataclass
class Spool:
    name: str
    host: str
    flag: str
    location: str

@dataclass
class SpoolData:
    token: str
    spools: List[Spool] = None

@dataclass
class RibbonEndpoint:
    endpoint: str
    spools: Optional[SpoolData] = None

@dataclass
class Handling:
    arr: int = 0
    cancel: bool = False
    das: int = 5
    dcd: int = 0
    safelock: bool = False
    may20g: bool = True
    sdf: int = 41

@dataclass
class Session:
    ribbon_id: str = ""
    token_id: str = ""
    last_received: Optional[str] = None

@dataclass
class Migration:
    endpoint: str
    name: str
    flag: str

from .social_handler import SocialHandler
from .room_handler import RoomHandler

class RibbonClient:
    def __init__(self, token: str):
        self.token = token
        self.connection: Optional[websockets.WebSocketClientProtocol] = None
        self.message_handlers: Dict[str, Callable] = {}
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 1
        
        self.environment: Optional[Environment] = None
        self.endpoint: Optional[RibbonEndpoint] = None
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT
        }
        self.handling = Handling()
        self.session = Session()
        self._ping_task: Optional[asyncio.Task] = None

        self.username: str = ""
        self.role: str = ""
        self.id: str = ""

        self.migrating: bool = False

        signal.signal(signal.SIGINT, self._handle_sigint)

        # Initialize handlers
        self.social = SocialHandler(self)
        self.room = RoomHandler(self)

        self.event_handlers: Dict[str, List[Callable]] = {}

    async def emit(self, event: str, data: Any) -> None:
        """Emit an event to all registered handlers"""
        print(f"Emitting event: {event} with {len(self.event_handlers.get(event, []))} handlers")
        if event in self.event_handlers:
            for handler in self.event_handlers[event]:
                await handler(data)

    def on(self, event: str, handler: Callable) -> None:
        """Register an event handler"""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        self.event_handlers[event].append(handler)
        print(f"Registered handler for event: {event}")
    
    def off(self, event: str, handler: Callable) -> None:
        """Unregister an event handler"""
        if event in self.event_handlers:
            self.event_handlers[event].remove(handler)

    def _handle_sigint(self, signum, frame):
        print("Received SIGINT, shutting down gracefully...")
        asyncio.create_task(self.close())
        sys.exit(0)

    async def initialize(self) -> None:
        """Setup initial connection by fetching required data"""
        async with aiohttp.ClientSession() as session:
            # Get server environment
            async with session.get("https://tetr.io/api/server/environment", headers=self.headers) as resp:
                data = await resp.json()
                if not data.get("success"):
                    raise ValueError("Failed to get server environment")
                self.environment = Environment(signature=data.get("signature", {}))

            async with session.get("https://tetr.io/api/users/me", headers=self.headers) as resp:
                data = await resp.json()
                if not data.get("success"):
                    raise ValueError("Failed to get user data")
                
                user_data = data.get("user", {})
                if not user_data:
                    raise ValueError("No user data received")
                
                self.username = user_data.get("username", "")
                self.role = user_data.get("role", "").lower()
                self.id = user_data.get("_id", "")
                
                if self.role != "bot":
                    raise ValueError(f"This client can only be used with bot accounts. Got role: {self.role}")
                    sys.exit(1)


            async with session.get("https://tetr.io/api/server/ribbon", headers=self.headers) as resp:
                data = await resp.json()
                spools_data = None
                if data.get("spools"):
                    spools = [
                        Spool(
                            name=s["name"],
                            host=s["host"],
                            flag=s["flag"],
                            location=s["location"]
                        ) for s in data["spools"]["spools"]
                    ]
                    spools_data = SpoolData(
                        token=data["spools"]["token"],
                        spools=spools
                    )
                
                self.endpoint = RibbonEndpoint(
                    endpoint=data["endpoint"],
                    spools=spools_data
                )

    async def connect(self, ws_url: Optional[str] = None) -> None:
        """Connect to the Ribbon websocket"""
        if not self.endpoint and not ws_url:
            await self.initialize()
        
        try:
            connect_url = ws_url or f"wss://tetr.io{self.endpoint.endpoint}"
            print(f"Attempting to connect to: {connect_url}")
            
            self.connection = await websockets.connect(
                connect_url,
                additional_headers=self.headers
            )
            self._reconnect_attempts = 0
            
            if self.migrating and self.session.token_id:
                await self.send_message("session", {
                    "ribbonid": self.session.ribbon_id,
                    "tokenid": self.session.token_id
                })
                self.migrating = False
            else:
                await self.send_message("new", None)
            
            await self._listen()
        except Exception as e:
            print(f"Connection error details:\n{type(e).__name__}: {str(e)}")
            await self._handle_connection_error(e)

    async def send_message(self, command: str, data: Any = None) -> None:
        if not self.connection:
            raise ConnectionError("Not connected to Ribbon server")
        
        message = {"command": command}
        if data is not None:
            message["data"] = data
        
        try:
            if not command == "ping" and not command == "server.authorize":
                print(f"Sending message: {message}")
            await self.connection.send(json.dumps(message))
        except Exception as e:
            print(f"Failed to send message: {type(e).__name__}: {str(e)}")

    async def register_handler(self, message_type: str, handler: Callable) -> None:
        self.message_handlers[message_type] = handler

    async def close(self) -> None:
        if self.connection:
            await self.connection.close()
            self.connection = None

    def start_ping(self):
        print("Ping loop started")
        self.stop_ping() # make sure to stop any existing ping loop
        self._ping_task = asyncio.create_task(self._ping_loop())

    def stop_ping(self):
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None

    async def _ping_loop(self):
        while True:
            await self.send_message("ping", {"recvid": self.session.last_received})
            await asyncio.sleep(2)

    async def _listen(self) -> None:
        while True:
            try:
                message = await self.connection.recv()
                data = json.loads(message) if isinstance(message, str) else message
                
                if data.get("command") == "packets":
                    packets = data.get("data", {}).get("packets", [])
                    for packet in packets:
                        if packet.get("command") != "packets":
                            await self._handle_command(packet)
                else:
                    await self._handle_command(data)
            except websockets.ConnectionClosed:
                await self._handle_connection_error("Connection closed")
                await self.close()
                sys.exit(1)

    async def _handle_command(self, data: dict) -> None:
        if "id" in data:
            self.session.last_received = data["id"]
        
        command = data.get("command")
        if not command:
            return
        
        if command == "ping":
            return

        print(f"Handling command: {command}")
        
        if command == "kick":
            print(f"Kicked from server: {data.get('data', {}).get('reason', 'No reason provided')}")
            await self.close()
            sys.exit(1)
        elif command == "session":
            await self._handle_session(data.get("data", {}))
        elif command == "server.authorize":
            print("Connected and authorized successfully")
            await self.social.setup_handlers()
            await self.room.setup_handlers()
            await self.emit("client.ready", None)  

            await self.send_message("social.presence", {
                "status": "online",
                "detail": "menus"
            })
            self.start_ping()
        elif command == "server.migrate":
            await self.migrate(data.get("data", {}))
            return
        elif command == "server.migrated":
            print("Migration completed successfully")
            self.migrating = False
            
        if command in self.message_handlers:
            await self.message_handlers[command](data.get("data"))

    async def _handle_session(self, data: dict) -> None:
        ribbon_id = data.get("ribbonid", "")
        token_id = data.get("tokenid", "")
                
        if not self.session.token_id:
            print("New session, starting authorization flow")
            await self.send_message("server.authorize", {
                "token": self.token,
                "handling": {
                    "arr": self.handling.arr,
                    "cancel": self.handling.cancel,
                    "das": self.handling.das,
                    "dcd": self.handling.dcd,
                    "safelock": self.handling.safelock,
                    "may20g": self.handling.may20g,
                    "sdf": self.handling.sdf
                },
                "signature": self.environment.signature,
            })
            self.session.ribbon_id = ribbon_id
            self.session.token_id = token_id

    async def migrate(self, migration_data: dict) -> None:
        migration = Migration(
            endpoint=migration_data["endpoint"],
            name=migration_data["name"],
            flag=migration_data["flag"]
        )
        
        print(f"Migrating to server {migration.name} ({migration.flag})")
        
        self.migrating = True
        await self.close()
        
        new_url = f"wss://tetr.io{migration.endpoint}"
        await self.connect(new_url)

    async def _handle_connection_error(self, error: Any) -> None:
        print(f"Connection error: {type(error).__name__}: {str(error)}")
        await self.close()

        sys.exit(1)

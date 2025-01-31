#tetrio
import asyncio
from teto.client import RibbonClient


async def handle_room_chat(data):
    global twitch_chat, twitch_user
    await twitch_chat.send_message(twitch_user.login, f"From Tetr.io : {data['user']['username']}: {data['content']}")


async def on_ready(data):
    print("on_ready handler called")
    global roomid
    await client.room.join_room(roomid.upper())

async def handle_join(data):
    await client.room.send_chat("Hello there! Enjoy the game, but please keep it under 1.25 pps!")

#twitch
from twitchAPI.helper import first
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticationStorageHelper
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage
from twitchAPI.object.eventsub import ChannelFollowEvent
from twitchAPI.eventsub.websocket import EventSubWebsocket

APP_ID = 'twitch app id'
APP_SECRET = 'twitch app secret'
TARGET_SCOPES = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT, AuthScope.MODERATOR_READ_FOLLOWERS]


async def twitch_on_ready(ready_event: EventData):
    global twitch_user
    await ready_event.chat.join_room(twitch_user.login)


async def twitch_on_message(msg: ChatMessage):
    await client.room.send_chat(f"From Twitch: {msg.user.name}: {msg.text}")

async def on_follow(data: ChannelFollowEvent):
    await client.room.send_chat(f"{data.event.user_name} just followed me on Twitch! Everyone say hello to him!")



async def main():
    #twitch
    global twitch
    twitch = await Twitch(APP_ID, APP_SECRET)
    twitch_helper = UserAuthenticationStorageHelper(twitch, TARGET_SCOPES)
    await twitch_helper.bind()
    global twitch_user
    twitch_user = await first(twitch.get_users())
    global twitch_chat
    twitch_chat = await Chat(twitch)
    twitch_chat.register_event(ChatEvent.READY, twitch_on_ready)
    twitch_chat.register_event(ChatEvent.MESSAGE, twitch_on_message)
    twitch_chat.start()
    #tetrio
    token = "tetr.io bot token"

    global client, roomid
    client = RibbonClient(token)

    roomid = input("Enter room ID to join: ")

    client.on("client.room.chat", handle_room_chat)
    client.on("client.room.player.add", handle_join)

    print("Registering client.ready handler")
    client.on("client.ready", on_ready)
    print("Handler registered, connecting...")
    await client.connect()

    try:
        while True:
            a = 1
    except KeyboardInterrupt:
        if client.room.current_room:
            await client.room.leave_room()
        await client.close()
        twitch_chat.stop()
        # await twitch.update_custom_reward(user.id, rew_id, is_enabled=False)
        await twitch.close()


asyncio.run(main())

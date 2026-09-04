import asyncio

import chainlit as cl
from chainlit.data import get_data_layer as cl_get_data_layer
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.server import app
from fastapi.staticfiles import StaticFiles

from LocalStorage import UPLOAD_DIR, LocalStorageClient
from PlantLangGraph import PlantLangGraph

_agent: PlantLangGraph | None = None
_agent_lock = asyncio.Lock()


async def get_agent() -> PlantLangGraph:
    global _agent
    if _agent is None:
        async with _agent_lock:
            if _agent is None:
                _agent = await PlantLangGraph.create()
    return _agent


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(
        conninfo="postgresql+asyncpg://plantbot:plantbot@localhost:5432/plantchatbot",
        storage_provider=LocalStorageClient(),
    )


# Serve locally-persisted upload files (uploaded plant photos). Inserted at
# the front of the routing table so chainlit's own catch-all SPA route
# (`GET /{full_path:path}`, already registered via the `chainlit.server`
# import above) doesn't shadow it.
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.router.routes.insert(0, app.router.routes.pop())


@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    if username == "dev" and password == "dev":
        return cl.User(identifier="dev")
    return None


@cl.on_chat_start
async def on_chat_start():
    await get_agent()
    await cl.Message(content="Merhaba! 🌿 Başlamak için bir bitki fotoğrafı yükleyin.").send()


@cl.on_message
async def on_message(message: cl.Message):
    agent = await get_agent()
    thread_id = cl.context.session.thread_id
    image_elements = [el for el in message.elements if "image" in (el.mime or "")]

    has_plant = await agent.has_active_plant(thread_id)

    if not has_plant:
        if not image_elements:
            await cl.Message(content="Lütfen önce bir bitki fotoğrafı yükleyin.").send()
            return

        msg = cl.Message(content="")
        await msg.send()
        async for token in agent.identify_stream(
            thread_id, image_elements[0].path, caption=message.content or None
        ):
            await msg.stream_token(token)
        await msg.update()

        species = await agent.get_confirmed_species(thread_id)
        if species:
            data_layer = cl_get_data_layer()
            if data_layer:
                await data_layer.update_thread(thread_id, name=species)
        return

    if image_elements:
        await cl.Message(
            content=(
                "Bu sohbette zaten bir bitki üzerinde çalışıyoruz. Farklı bir "
                "bitki için sol üstten **Yeni Sohbet** başlatın."
            )
        ).send()
        return

    if not message.content.strip():
        await cl.Message(content="Herhangi bir şey yazmadınız -- ne sormak istersiniz?").send()
        return

    msg = cl.Message(content="")
    await msg.send()
    async for token in agent.ask_stream(thread_id, message.content):
        await msg.stream_token(token)
    await msg.update()
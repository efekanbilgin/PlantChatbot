import asyncio
import html

import chainlit as cl
from chainlit.data import get_data_layer as cl_get_data_layer
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.server import app
from fastapi import Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from Auth import register_user, verify_user
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


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.router.routes.insert(0, app.router.routes.pop())


@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    if await verify_user(username, password):
        return cl.User(identifier=username.strip())
    return None


REGISTER_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>Kayıt Ol -- Plantlik</title>
<style>
  body {{
    background: #0e0e10; color: #e6e6e6; font-family: system-ui, sans-serif;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; margin: 0;
  }}
  .card {{
    background: #17171a; padding: 2.5rem; border-radius: 12px;
    width: 320px; box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  }}
  h1 {{ font-size: 1.3rem; margin: 0 0 1.5rem; }}
  label {{ display: block; font-size: 0.85rem; margin-bottom: 0.3rem; color: #b3b3b3; }}
  input {{
    width: 100%; box-sizing: border-box; padding: 0.6rem 0.75rem; margin-bottom: 1rem;
    border-radius: 8px; border: 1px solid #333; background: #0e0e10; color: #e6e6e6;
  }}
  button {{
    width: 100%; padding: 0.7rem; border: none; border-radius: 8px;
    background: #ec1561; color: white; font-weight: 600; cursor: pointer;
  }}
  .msg {{ margin-bottom: 1rem; padding: 0.6rem 0.8rem; border-radius: 8px; font-size: 0.9rem; }}
  .msg.error {{ background: #3a1620; color: #ff8fa3; }}
  .msg.success {{ background: #14331f; color: #7ee2a8; }}
  a {{ color: #ec1561; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Plantlik'e Kayıt Ol</h1>
    {message_html}
    <form method="post" action="/register">
      <label for="username">Kullanıcı adı</label>
      <input id="username" name="username" type="text" required minlength="3" value="{username_value}">
      <label for="password">Şifre</label>
      <input id="password" name="password" type="password" required minlength="6">
      <button type="submit">Kayıt Ol</button>
    </form>
    <p style="margin-top:1.2rem; font-size:0.85rem;">
      Zaten hesabın var mı? <a href="/">Giriş yap</a>
    </p>
  </div>
</body>
</html>
"""


@app.get("/register")
async def register_page():
    return HTMLResponse(
        REGISTER_PAGE_TEMPLATE.format(message_html="", username_value="")
    )


@app.post("/register")
async def register_submit(username: str = Form(...), password: str = Form(...)):
    success, message = await register_user(username, password)
    css_class = "success" if success else "error"
    message_html = f'<div class="msg {css_class}">{html.escape(message)}</div>'
    username_value = "" if success else html.escape(username)
    return HTMLResponse(
        REGISTER_PAGE_TEMPLATE.format(message_html=message_html, username_value=username_value)
    )


for _ in range(2):
    app.router.routes.insert(0, app.router.routes.pop())


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
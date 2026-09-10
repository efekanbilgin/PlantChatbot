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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kayıt Ol -- Plantlik</title>
<style>
  :root {{
    --pl-bg: #11150f;
    --pl-paper: #1a2016;
    --pl-border: #2c3324;
    --pl-text: #ece6d8;
    --pl-text-secondary: #a6a08c;
    --pl-primary: #a9682f;
    --pl-primary-light: #c98a4f;
    --pl-primary-dark: #7c4a1e;
    --pl-error-bg: #3a2116;
    --pl-error-text: #e8a97a;
    --pl-success-bg: #1c2c17;
    --pl-success-text: #9fd18a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--pl-bg); color: var(--pl-text);
    font-family: system-ui, -apple-system, sans-serif;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; margin: 0; padding: 1.5rem;
  }}
  .card {{
    background: var(--pl-paper); border: 1px solid var(--pl-border);
    padding: 2.5rem; border-radius: 16px;
    width: 100%; max-width: 340px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.35);
  }}
  .logo {{
    display: block; width: 64px; height: 64px; border-radius: 14px;
    margin: 0 auto 1.25rem; object-fit: cover;
  }}
  h1 {{
    font-size: 1.25rem; margin: 0 0 1.5rem; text-align: center; font-weight: 600;
  }}
  label {{
    display: block; font-size: 0.85rem; margin-bottom: 0.35rem;
    color: var(--pl-text-secondary);
  }}
  input {{
    width: 100%; padding: 0.65rem 0.8rem; margin-bottom: 1.1rem;
    border-radius: 8px; border: 1px solid var(--pl-border);
    background: var(--pl-bg); color: var(--pl-text); font-size: 0.95rem;
    transition: border-color 0.15s ease;
  }}
  input:focus {{
    outline: none; border-color: var(--pl-primary);
  }}
  button {{
    width: 100%; padding: 0.75rem; border: none; border-radius: 8px;
    background: var(--pl-primary); color: #fff; font-weight: 600;
    font-size: 0.95rem; cursor: pointer; transition: background 0.15s ease;
  }}
  button:hover {{ background: var(--pl-primary-light); }}
  .msg {{
    margin-bottom: 1.1rem; padding: 0.65rem 0.85rem; border-radius: 8px;
    font-size: 0.88rem; line-height: 1.4;
  }}
  .msg.error {{ background: var(--pl-error-bg); color: var(--pl-error-text); }}
  .msg.success {{ background: var(--pl-success-bg); color: var(--pl-success-text); }}
  .footer-link {{
    margin-top: 1.4rem; font-size: 0.85rem; text-align: center;
    color: var(--pl-text-secondary);
  }}
  a {{ color: var(--pl-primary-light); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
  <div class="card">
    <img class="logo" src="/public/logo.png" alt="Plantlik">
    <h1>Plantlik'e Kayıt Ol</h1>
    {message_html}
    <form method="post" action="/register">
      <label for="username">Kullanıcı adı</label>
      <input id="username" name="username" type="text" required minlength="3" value="{username_value}" autofocus>
      <label for="password">Şifre</label>
      <input id="password" name="password" type="password" required minlength="6">
      <button type="submit">Kayıt Ol</button>
    </form>
    <p class="footer-link">Zaten hesabın var mı? <a href="/">Giriş yap</a></p>
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
import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from Agent import PlantChatbot
bot = PlantChatbot()
# NOT: Bu haliyle henüz Agent/LangGraph'a bağlı değil (pasif placeholder).
#
#


@cl.data_layer
def get_data_layer():
    """
    Thread geçmişi + sidebar bu satır sayesinde otomatik geliyor -- Chainlit
    kendi UI'ında sol panelde geçmiş sohbetleri, "New Chat" butonunu vs.
    kendisi render ediyor. Şimdilik SQLite; production'da tek değişecek
    şey bu conninfo string'i:
        "postgresql+asyncpg://user:pass@host/dbname"
    """
    return SQLAlchemyDataLayer(conninfo="sqlite+aiosqlite:///./chainlit.db")


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("image_path", None)
    await cl.Message(
        content="Merhaba! 🌿 Bir bitki görseli yükleyerek başlayabilirsin."
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    image_elements = [el for el in message.elements if "image" in (el.mime or "")]
    image_path = cl.user_session.get("image_path")

    # LangGraph bağlandığında checkpointer'a bu ID gidecek -- Chainlit'in
    # kendi thread ID'si, bizim ayrıca bir thread_id üretmemize gerek yok:
    # thread_id = cl.context.session.thread_id

    # 1) Bu thread'de henüz görsel yok -> görsel bekliyoruz
    if image_path is None:
        if not image_elements:
            await cl.Message(content="Önce bir bitki görseli yükler misin?").send()
            return

        new_image_path = image_elements[0].path
        cl.user_session.set("image_path", new_image_path)
        # --- Placeholder: result = bot.classify_image(new_image_path) ---
        result = bot.classify_image(new_image_path)
        await cl.Message(
            content=(
                "Görsel alındı.\n\n" f"{result}"
                "_(Sınıflandırma + LangGraph bağlantısı henüz aktif değil, "
                "bu bir placeholder cevap.)_\n\n"
                "Bu bitki hakkında soru sorabilirsin."
            )
        ).send()
        return

    # 2) Zaten aktif bir bitki var, kullanıcı yeni görsel göndermeye çalışıyor -> engelle
    if image_elements:
        await cl.Message(
            content=(
                "Bu konuşmada zaten bir bitki üzerinde çalışıyoruz. "
                "Yeni bir bitki için sol üstten **New Chat** ile yeni bir sohbet başlat."
            )
        ).send()
        return

    if not message.content.strip():
        await cl.Message(content="Bir şey yazmadın, ne sormak istersin?").send()
        return

    # --- Placeholder: graph.invoke(
    #         {"messages": [...], "image_path": image_path},
    #         config={"configurable": {"thread_id": cl.context.session.thread_id}},
    #     )  buraya gelecek ---
    await cl.Message(
        content=f"_(Placeholder)_ Şu soru LangGraph'a iletilecek: **{message.content}**"
    ).send()


@cl.on_chat_resume
async def on_chat_resume(thread):
    # Kullanıcı sol panelden eski bir sohbete dönerse çağrılıyor.
    # LangGraph bağlandığında image_path/state'i checkpointer'dan
    # (thread_id üzerinden) geri yükleyeceğiz; şimdilik sıfırlıyoruz.
    cl.user_session.set("image_path", None)
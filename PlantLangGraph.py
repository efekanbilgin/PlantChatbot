import asyncio
import re
from typing import Annotated, AsyncIterator, Literal, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from PlantClassifier import PlantClassifier
from PlantDatabase import PlantDatabase

CONFIDENCE_THRESHOLD = 0.83

CHECKPOINT_PATH = "best_model.pt"
CLASS_NAMES_PATH = "class_names.json"

PG_DSN = "postgresql://plantbot:plantbot@localhost:5432/plantchatbot"

QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "plant_article_chunks"
QDRANT_TOP_K = 4

EMBEDDING_MODEL = "text-embedding-qwen3-embedding-4b@q4_k_m"
EMBEDDING_BASE_URL = "http://127.0.0.1:4213/v1"

LLM_BASE_URL = "http://127.0.0.1:4213/v1"
LLM_MODEL = "google/gemma-4-12b-qat"

MAX_HISTORY_MESSAGES = 12


class PlantAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    image_path: str | None
    predicted_species: str | None
    confidence: float | None
    top_results: list[dict]
    trigger: Literal["classify", "question"]


IDENTIFY_SYSTEM_PROMPT = (
    "You are a botany expert assistant. The plant in the user's photo was "
    "identified as {species}.\n\n"
    "Below is the Wikipedia lead paragraph for this species. Use it as your "
    "SOURCE and introduce the plant to the user in a warm, natural tone. "
    "Start your reply by clearly stating the identified species name, then "
    "cover its general characteristics, where it grows or is naturally "
    "found, and any notable uses if mentioned.\n\n"
    "Do NOT invent anything that is not in the source. If the source is "
    "empty, say so plainly and only confirm the species name.\n\n"
    "This source material is YOUR OWN knowledge base -- the user did not "
    "supply it. Never phrase things as \"the sources/information you "
    "provided\" or similar (e.g. avoid 'sağladığınız kaynaklar', "
    "'verdiğiniz bilgiler'). Refer to it as your own knowledge instead.\n\n"
    "Do not mention any confidence score, percentage, or certainty level -- "
    "the user should never see a number like this; just state the "
    "identification plainly.\n\n"
    "Always respond in Turkish, regardless of what language the user's "
    "message below is written in.\n\n"
    "<wikipedia_summary>\n{summary}\n</wikipedia_summary>"
)

ANSWER_SYSTEM_PROMPT = (
    "You are a botany assistant with exactly ONE job: help the user with "
    "questions about ONE specific plant species: {species}. Nothing else.\n\n"
    "=== SCOPE (read carefully, this is your most important rule) ===\n"
    "IN SCOPE: {species}'s characteristics, habitat, care, biology, uses, "
    "and -- only when explicitly asked -- its pollen allergy data. Also "
    "plain conversational turns about THIS chat (greetings, thanks, asking "
    "you to repeat or clarify something already said).\n"
    "OFF-TOPIC (must be refused, no exceptions): literally anything else -- "
    "other plants/species, geography, directions/navigation, weather, "
    "capitals/politics, history, math, coding, general trivia, medical "
    "advice unrelated to this plant, or any other subject. This applies "
    "EVEN IF you happen to know the correct answer -- knowing it is "
    "irrelevant; if it is not about {species}, it is off-topic and you "
    "must refuse.\n"
    "IMPORTANT -- follow-up questions often drop the subject entirely (e.g. "
    "\"neden alerjiye neden olur?\" right after you discussed this plant's "
    "pollen). Before judging a short or subject-free question off-topic, "
    "check the conversation history below: if it's clearly a continuation "
    "of the ongoing {species} discussion, it is IN SCOPE, not off-topic.\n\n"
    "=== HARD RULE: NEVER USE YOUR OWN KNOWLEDGE ===\n"
    "You may ONLY use the three source blocks given below (structured "
    "data, Wikipedia summary, related passages) -- never your own general "
    "or world knowledge, for ANY question, on-topic or not. This applies "
    "even to on-topic questions: if the three sources below do not cover "
    "some detail about {species}, say honestly that you don't have enough "
    "information. Do not fill gaps from what you already know, and do not "
    "make anything up.\n\n"
    "=== WHEN TO REFUSE (two different cases -- do not mix them up) ===\n"
    "Case A -- OFF-TOPIC: the question is not about {species} at all (per "
    "SCOPE above). Respond with a short, clear scope refusal, e.g.: \"Bu "
    "konuda size yardımcı olamam -- ben yalnızca {species} bitkisiyle "
    "ilgili sorulara yanıt verebilirim.\"\n"
    "Case B -- ON-TOPIC but ungrounded: the question IS about {species}, "
    "but none of the three sources below actually address this specific "
    "detail. This is NOT the same as off-topic -- do NOT use the Case A "
    "refusal here. Instead say honestly, in your own words, that you don't "
    "have that specific piece of information in your sources (e.g. "
    "\"Elimdeki kaynaklarda bu konuda spesifik bir bilgi/açıklama yer "
    "almamaktadır.\"), optionally sharing whatever related information the "
    "sources DO contain.\n"
    "In neither case should you attempt a general-knowledge answer or "
    "make anything up.\n\n"
    "=== THE THREE SOURCES ===\n"
    "1) STRUCTURED (from Postgres, verified/authoritative): pollen allergy "
    "fields only. If a field is 'unknown', it genuinely is unknown -- NEVER "
    "interpret that as 'safe'. Only bring up this pollen data if the "
    "user's current question is specifically about pollen or allergies. Do "
    "not proactively mention it for other questions.\n"
    "2) WIKIPEDIA SUMMARY: the species' Wikipedia lead paragraph -- use it "
    "freely for general characteristics, habitat, and other overview "
    "facts, including when the user asks for more detail/depth.\n"
    "3) RELATED PASSAGES (from vector search over research articles): use "
    "these too, especially for anything not covered by the Wikipedia "
    "summary. Combine both freely; if either conflicts with the "
    "structured pollen data on pollen topics specifically, trust the "
    "STRUCTURED data.\n\n"
    "You do not have and must not discuss toxicity, poisoning, or safety-"
    "for-pets/humans information, even though it is not covered by the "
    "sources anyway. If the user asks about toxicity or poisoning, tell "
    "them plainly that this assistant does not cover that topic and "
    "suggest consulting a vet, doctor, or poison control center.\n\n"
    "This source material is YOUR OWN knowledge base -- the user did not "
    "supply it. Never phrase things as \"the sources/information you "
    "provided\" or similar (e.g. avoid 'sağladığınız kaynaklar', "
    "'verdiğiniz bilgiler'). Refer to it as your own knowledge instead "
    "(e.g. 'elimdeki kaynaklara göre', 'bildiğim kadarıyla').\n\n"
    "Always respond in Turkish, regardless of what language the user's "
    "message is written in.\n\n"
    "<structured_data>\n{structured}\n</structured_data>\n\n"
    "<wikipedia_summary>\n{wikipedia_summary}\n</wikipedia_summary>\n\n"
    "<related_passages>\n{passages}\n</related_passages>"
)


class PlantLangGraph:
    def __init__(
        self,
        classifier: PlantClassifier,
        llm: ChatOpenAI,
        vectorstore: QdrantVectorStore,
        db: PlantDatabase,
        checkpointer: AsyncPostgresSaver,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ):
        self.classifier = classifier
        self.llm = llm
        self.vectorstore = vectorstore
        self.db = db
        self.checkpointer = checkpointer
        self.confidence_threshold = confidence_threshold
        self.graph = self._build_graph()

    @classmethod
    async def create(
        cls,
        checkpoint_path: str = CHECKPOINT_PATH,
        class_names_path: str = CLASS_NAMES_PATH,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> "PlantLangGraph":
        pool = AsyncConnectionPool(
            conninfo=PG_DSN,
            max_size=10,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        )
        await pool.open()

        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()

        db = PlantDatabase(pool)

        classifier = PlantClassifier(
            checkpoint_path=checkpoint_path,
            class_names_path=class_names_path,
        )

        embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            base_url=EMBEDDING_BASE_URL,
            api_key="key",
            check_embedding_ctx_length=False,
        )
        qdrant_client = QdrantClient(url=QDRANT_URL)
        vectorstore = QdrantVectorStore(
            client=qdrant_client,
            collection_name=QDRANT_COLLECTION,
            embedding=embeddings,
        )

        llm = ChatOpenAI(
            api_key="key",
            base_url=LLM_BASE_URL,
            model=LLM_MODEL,
            reasoning_effort="none",
        )

        return cls(
            classifier=classifier,
            llm=llm,
            vectorstore=vectorstore,
            db=db,
            checkpointer=checkpointer,
            confidence_threshold=confidence_threshold,
        )

    def _build_graph(self):
        builder = StateGraph(PlantAgentState)

        builder.add_node("classify", self._classify_node)
        builder.add_node("ask_clarification", self._ask_clarification_node)
        builder.add_node("respond_identification", self._respond_identification_node)
        builder.add_node("answer_question", self._answer_question_node)

        builder.add_conditional_edges(
            START,
            self._route_entry,
            {"classify": "classify", "question": "answer_question"},
        )
        builder.add_conditional_edges(
            "classify",
            self._route_after_classify,
            {
                "ask_clarification": "ask_clarification",
                "respond_identification": "respond_identification",
            },
        )
        builder.add_edge("ask_clarification", END)
        builder.add_edge("respond_identification", END)
        builder.add_edge("answer_question", END)

        return builder.compile(checkpointer=self.checkpointer)

    def _route_entry(self, state: PlantAgentState) -> Literal["classify", "question"]:
        return state["trigger"]

    def _route_after_classify(
        self, state: PlantAgentState
    ) -> Literal["ask_clarification", "respond_identification"]:
        if state["confidence"] is not None and state["confidence"] >= self.confidence_threshold:
            return "respond_identification"
        return "ask_clarification"

    async def _classify_node(self, state: PlantAgentState) -> dict:
        results = await asyncio.to_thread(self.classifier.predict, state["image_path"], top_k=3)
        top = results[0]
        return {
            "top_results": results,
            "predicted_species": top["species"],
            "confidence": top["confidence"],
        }

    async def _ask_clarification_node(self, state: PlantAgentState) -> dict:
        alt_list = "\n".join(
            f"- {r['species']} ({r['confidence'] * 100:.1f}%)" for r in state["top_results"]
        )
        content = (
            f"Emin olamadım (en olası tahmin: {state['predicted_species']}, "
            f"%{state['confidence'] * 100:.1f} güven).\n\n{alt_list}\n\n"
            "Yaprağın daha net, daha yakın ve odakta olduğu bir fotoğraf "
            "paylaşabilir misiniz? İyi ışık ve yaprağın kareyi doldurması "
            "yardımcı olacaktır."
        )
        return {"messages": [{"role": "assistant", "content": content}]}

    async def _respond_identification_node(self, state: PlantAgentState) -> dict:
        species = state["predicted_species"]
        plant = await self.db.get_plant(species)
        summary = (plant or {}).get("summary") or "(No summary recorded for this species yet.)"

        system = SystemMessage(
            content=IDENTIFY_SYSTEM_PROMPT.format(
                species=species,
                summary=summary,
            )
        )
        response = await self.llm.ainvoke([system, state["messages"][-1]])
        return {"messages": [response]}

    async def _answer_question_node(self, state: PlantAgentState) -> dict:
        species = state["predicted_species"]
        question = state["messages"][-1].content

        plant = await self.db.get_plant(species)
        structured = self._format_structured(plant)
        wikipedia_summary = (plant or {}).get("summary") or "(No Wikipedia summary recorded for this species.)"

        docs = await asyncio.to_thread(self._search_chunks, question, species)
        passages = "\n\n---\n\n".join(d.page_content for d in docs) or "(No related passages found.)"

        system = SystemMessage(
            content=ANSWER_SYSTEM_PROMPT.format(
                species=species,
                structured=structured,
                wikipedia_summary=wikipedia_summary,
                passages=passages,
            )
        )
        history = state["messages"][-MAX_HISTORY_MESSAGES:]
        response = await self.llm.ainvoke([system] + history)
        return {"messages": [response]}

    def _search_chunks(self, query: str, species: str):
        return self.vectorstore.similarity_search(
            self._grounded_query(query, species),
            k=QDRANT_TOP_K,
            filter=self._species_filter(species),
        )

    @staticmethod
    def _grounded_query(query: str, species: str) -> str:
        return f"{species}: {query}"

    @staticmethod
    def _species_filter(species: str) -> qdrant_models.Filter:
        return qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="metadata.species",
                    match=qdrant_models.MatchValue(
                        value=PlantLangGraph._qdrant_species_key(species)
                    ),
                )
            ]
        )

    @staticmethod
    def _qdrant_species_key(species: str) -> str:
        return re.sub(r"\s+", "_", species.strip())

    @staticmethod
    def _format_structured(plant: dict | None) -> str:
        if not plant:
            return "(No Postgres record for this species.)"

        return (
            f"pollen_season: {plant.get('pollen_season_onset') or '?'} - "
            f"{plant.get('pollen_season_peak') or '?'}\n"
            f"pollen_severity: {plant.get('pollen_severity') or 'unknown'}\n"
            f"pollen_notes: {plant.get('pollen_notes') or 'none'} "
            f"(source: {plant.get('pollen_source') or 'unverified'})"
        )

    async def has_active_plant(self, thread_id: str) -> bool:
        return bool(await self.get_confirmed_species(thread_id))

    async def get_confirmed_species(self, thread_id: str) -> str | None:
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = await self.graph.aget_state(config)
        values = snapshot.values
        species = values.get("predicted_species")
        confidence = values.get("confidence")
        if species and confidence is not None and confidence >= self.confidence_threshold:
            return species
        return None

    async def identify(self, thread_id: str, image_path: str, caption: str | None = None) -> str:
        config = {"configurable": {"thread_id": thread_id}}
        result = await self.graph.ainvoke(
            {
                "messages": [HumanMessage(content=caption or "Please identify this plant.")],
                "image_path": image_path,
                "trigger": "classify",
            },
            config=config,
        )
        return result["messages"][-1].content

    async def ask(self, thread_id: str, question: str) -> str:
        config = {"configurable": {"thread_id": thread_id}}
        result = await self.graph.ainvoke(
            {"messages": [HumanMessage(content=question)], "trigger": "question"},
            config=config,
        )
        return result["messages"][-1].content

    async def identify_stream(
        self, thread_id: str, image_path: str, caption: str | None = None
    ) -> AsyncIterator[str]:
        config = {"configurable": {"thread_id": thread_id}}
        async for token in self._stream(
            {
                "messages": [HumanMessage(content=caption or "Please identify this plant.")],
                "image_path": image_path,
                "trigger": "classify",
            },
            config,
        ):
            yield token

    async def ask_stream(self, thread_id: str, question: str) -> AsyncIterator[str]:
        config = {"configurable": {"thread_id": thread_id}}
        async for token in self._stream(
            {"messages": [HumanMessage(content=question)], "trigger": "question"},
            config,
        ):
            yield token

    async def _stream(self, input_state: dict, config: dict) -> AsyncIterator[str]:
        got_token = False
        async for event in self.graph.astream_events(input_state, config, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    got_token = True
                    yield chunk.content

        if not got_token:
            snapshot = await self.graph.aget_state(config)
            messages = snapshot.values.get("messages", [])
            if messages:
                yield messages[-1].content

    async def close(self) -> None:
        await self.checkpointer.conn.close()


async def _manual_test():
    agent = await PlantLangGraph.create()
    thread_id = "test-thread-1"

    image_path = input("Test image path: ").strip()
    print("\n--- identify_stream ---")
    async for token in agent.identify_stream(thread_id, image_path):
        print(token, end="", flush=True)
    print()

    if await agent.has_active_plant(thread_id):
        question = input("\nQuestion: ").strip()
        print("\n--- ask_stream ---")
        async for token in agent.ask_stream(thread_id, question):
            print(token, end="", flush=True)
        print()

    await agent.close()


if __name__ == "__main__":
    asyncio.run(_manual_test())
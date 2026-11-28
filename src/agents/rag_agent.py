"""PostgreSQL-persisted LangGraph workflow for retrieval-augmented chat."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.postgres import PostgresStore

from database import get_sqlalchemy_database_url
from agents.utils.nodes import answer_node, question_node, retrieval_node
from agents.utils.state import WorkflowState


builder = StateGraph(WorkflowState)
builder.add_node("question", question_node)
builder.add_node("retrieval", retrieval_node)
builder.add_node("answer", answer_node)
builder.add_edge(START, "question")
builder.add_edge("question", "retrieval")
builder.add_edge("retrieval", "answer")
builder.add_edge("answer", END)


def _postgres_dsn() -> str:
    """Normalize the configured SQLAlchemy PostgreSQL URL for psycopg."""
    sqlalchemy_url = get_sqlalchemy_database_url()
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


def setup_persistence() -> None:
    """Create the LangGraph checkpoint/store tables; run once during setup."""
    dsn = _postgres_dsn()
    with ExitStack() as stack:
        checkpointer = stack.enter_context(PostgresSaver.from_conn_string(dsn))
        store = stack.enter_context(PostgresStore.from_conn_string(dsn))
        checkpointer.setup()
        store.setup()


@contextmanager
def create_workflow() -> Iterator[Any]:
    """Yield a compiled workflow with PostgreSQL-backed persistence.

    Keep the context open for the lifetime of graph use so the saver/store
    connections remain available. Call ``setup_persistence()`` once before the
    first run to create their tables.
    """
    dsn = _postgres_dsn()
    with ExitStack() as stack:
        checkpointer = stack.enter_context(PostgresSaver.from_conn_string(dsn))
        store = stack.enter_context(PostgresStore.from_conn_string(dsn))
        yield builder.compile(checkpointer=checkpointer, store=store)


# LangGraph CLI/server manages its own persistence for this exported graph.
graph = builder.compile()

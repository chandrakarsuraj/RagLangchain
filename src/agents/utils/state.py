"""Shared state schema for the LangGraph RAG workflow."""

from typing import NotRequired

from langchain_core.documents import Document
from langgraph.graph import MessagesState


class WorkflowState(MessagesState):
    """Message history and values passed between QA nodes."""

    # Retrieval configuration / chat input
    collection_name: NotRequired[str]
    query: NotRequired[str]
    top_k: NotRequired[int]

    # Node outputs
    retrieved_documents: NotRequired[list[Document]]
    context: NotRequired[str]
    answer: NotRequired[str]

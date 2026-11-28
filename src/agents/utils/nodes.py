"""LangGraph nodes for retrieval-augmented question answering."""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from config import settings
from vector_store.vector_database import get_vector_store

from .state import WorkflowState

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTION = "raglangchain"
_DEFAULT_TOP_K = 4

# Allows a workflow builder to import the graph state from this module if desired.
state = WorkflowState

CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "Answer using only the retrieved context below. If the context "
                "does not contain the answer, say you do not have enough "
                "information. Do not invent facts. Cite relevant source labels "
                "from the context when available.\n\nRetrieved context:\n{context}"
            ),
        ),
        MessagesPlaceholder(variable_name="chat_history"),
    ]
)




def question_node(workflow_state: WorkflowState) -> dict[str, str]:
    """Extract and validate the latest user question for the chat turn."""
    query = workflow_state.get("query")
    if not query:
        messages = workflow_state.get("messages", [])
        latest_human_message = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, HumanMessage)
            ),
            None,
        )
        if latest_human_message is not None:
            content = latest_human_message.content
            query = content if isinstance(content, str) else str(content)

    if not query or not query.strip():
        raise ValueError(
            "The question node requires 'query' or a HumanMessage in 'messages'."
        )

    logger.info("Accepted chat question (%d characters)", len(query))
    return {"query": query.strip()}


def retrieval_node(workflow_state: WorkflowState) -> dict[str, Any]:
    """Retrieve relevant chunks and format their content for the answer node."""
    query = workflow_state.get("query")
    if not query or not query.strip():
        raise ValueError("The retrieval node requires a non-empty 'query'.")

    top_k = workflow_state.get("top_k", _DEFAULT_TOP_K)
    if top_k <= 0:
        raise ValueError("'top_k' must be greater than zero.")

    collection_name = workflow_state.get("collection_name", _DEFAULT_COLLECTION)
    logger.info(
        "Retrieving up to %d chunk(s) from collection %r",
        top_k,
        collection_name,
    )
    retrieved_documents = get_vector_store(collection_name).similarity_search(
        query,
        k=top_k,
    )
    context = "\n\n".join(
        "Source: "
        + str(document.metadata.get("source", "unknown"))
        + "\n"
        + document.page_content
        for document in retrieved_documents
    )
    if not context:
        context = "No relevant documents were retrieved."

    logger.info("Retrieved %d relevant chunk(s)", len(retrieved_documents))
    return {
        "retrieved_documents": retrieved_documents,
        "context": context,
    }


def answer_node(workflow_state: WorkflowState) -> dict[str, Any]:
    """Generate an answer from the current question and retrieval context."""
    query = workflow_state.get("query")
    if not query or not query.strip():
        raise ValueError("The answer node requires a non-empty 'query'.")

    context = workflow_state.get("context")
    if not context:
        raise ValueError(
            "The answer node requires retrieval context; run retrieval_node first."
        )

    config = settings()
    if not config.openai_api_key:
        raise RuntimeError("Configure OPENAI_API_KEY before running the answer node.")

    messages = list(workflow_state.get("messages", []))
    if (
        not messages
        or not isinstance(messages[-1], HumanMessage)
        or messages[-1].content != query
    ):
        messages.append(HumanMessage(content=query))

    model = ChatOpenAI(
        model=config.chat_model,
        api_key=config.openai_api_key,
        temperature=0,
    )
    answer = (CHAT_PROMPT | model | StrOutputParser()).invoke(
        {"context": context, "chat_history": messages}
    )

    logger.info(
        "Generated answer using %d retrieved chunk(s)",
        len(workflow_state.get("retrieved_documents", [])),
    )
    return {
        "messages": [AIMessage(content=answer)],
        "answer": answer,
    }

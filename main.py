"""Streamlit UI for document upload and retrieval-augmented chat."""

import logging
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

import boto3
import requests
import streamlit as st
import streamlit.components.v1 as components
from botocore.exceptions import BotoCoreError, ClientError
from langgraph_sdk import get_sync_client

from src.config import settings

logger = logging.getLogger(__name__)

_firebase_auth_component = components.declare_component(
    "firebase_auth",
    path=str(Path(__file__).parent / "src" / "ui" / "firebase_auth"),
)


@st.cache_resource
def _get_langgraph_client(api_url: str, api_key: str | None):
    return get_sync_client(url=api_url, api_key=api_key, timeout=30)


def _resolve_firebase_project_id(config: Any) -> str:
    """Use an explicit project ID or infer it from Firebase's default auth domain."""
    project_id = (config.firebase_project_id or "").strip()
    if project_id:
        return project_id

    auth_domain = (config.firebase_auth_domain or "").strip().lower()
    auth_domain = auth_domain.removeprefix("https://").removeprefix("http://").strip("/")
    suffix = ".firebaseapp.com"
    if auth_domain.endswith(suffix):
        return auth_domain.removesuffix(suffix)
    return ""


def _lookup_firebase_user(config: Any, id_token: str) -> dict[str, str]:
    """Validate a Firebase ID token through Firebase Auth's lookup endpoint."""
    response = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:lookup",
        params={"key": config.firebase_api_key},
        json={"idToken": id_token},
        timeout=10,
    )
    if response.status_code != 200:
        raise ValueError("Firebase rejected the sign-in token.")

    users = response.json().get("users", [])
    if not users or not users[0].get("localId"):
        raise ValueError("Firebase did not return a valid user account.")

    firebase_user = users[0]
    return {
        "uid": firebase_user["localId"],
        "email": firebase_user.get("email", ""),
        "display_name": firebase_user.get("displayName", ""),
    }


def _active_firebase_user(config: Any) -> dict[str, Any] | None:
    """Return the session user, periodically revalidating its ID token."""
    user_session = st.session_state.get("firebase_auth_user")
    if not isinstance(user_session, dict) or not user_session.get("id_token"):
        return None

    now = time.time()
    if now - user_session.get("verified_at", 0) < 300:
        return user_session

    try:
        verified_user = _lookup_firebase_user(config, user_session["id_token"])
    except (ValueError, requests.RequestException):
        st.session_state.pop("firebase_auth_user", None)
        st.session_state.pop("chat_thread_id", None)
        st.session_state["firebase_auth_notice"] = (
            "Your Firebase session expired or could not be verified. Please sign in again."
        )
        return None

    user_session.update(verified_user)
    user_session["verified_at"] = now
    st.session_state["firebase_auth_user"] = user_session
    return user_session


def _create_s3_client(config: Any):
    client_options: dict[str, str] = {}
    if config.aws_region:
        client_options["region_name"] = config.aws_region

    access_key_id = config.aws_access_key_id
    secret_access_key = config.aws_secret_access_key
    if bool(access_key_id) != bool(secret_access_key):
        raise ValueError(
            "Set both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or use the "
            "normal AWS credential chain."
        )
    if access_key_id and secret_access_key:
        client_options["aws_access_key_id"] = access_key_id
        client_options["aws_secret_access_key"] = secret_access_key

    # If no keys are set, boto3 uses its standard profile/role credential chain.
    return boto3.client("s3", **client_options)


def _upload_page() -> None:
    config = settings()
    bucket = (config.s3_bucket or "").strip()
    trigger_url = (config.ingest_worker_url or "").strip()

    st.title("Upload documents")
    st.write(
        "Files are uploaded to S3 first. Afterward, ingestion starts either via "
        "the configured worker endpoint or an S3 bucket event notification."
    )
    st.caption(f"S3 bucket: {bucket or 'not configured'}")
    st.caption(f"Chat collection: {config.vector_collection_name}")

    if not bucket:
        st.warning("Set S3_BUCKET in .env to the bucket name (not an s3:// URL).")
    if not trigger_url:
        st.info(
            "For immediate HTTP triggering, set INGEST_WORKER_URL. Otherwise, "
            "configure an S3 event notification to start the ingestion worker."
        )

    uploaded_files = st.file_uploader(
        "Choose PDF or text files",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        key="document_uploads",
    )

    if st.button(
        "Upload to S3 and start ingestion",
        type="primary",
        disabled=not uploaded_files,
    ):
        if not bucket:
            st.error("Upload was not started. Configure S3_BUCKET first.")
            return

        try:
            s3_client = _create_s3_client(config)
        except (BotoCoreError, ValueError) as exc:
            logger.exception("Could not configure the S3 client")
            st.error(f"Could not configure S3 access ({type(exc).__name__}).")
            return

        headers: dict[str, str] = {}
        if config.ingest_worker_api_key:
            headers["Authorization"] = f"Bearer {config.ingest_worker_api_key}"

        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.getvalue()
            if len(file_bytes) > config.max_upload_bytes:
                st.error(
                    f"{uploaded_file.name} exceeds the configured limit of "
                    f"{config.max_upload_bytes / (1024 * 1024):.1f} MB."
                )
                continue

            filename = uploaded_file.name.replace("\\", "/").rsplit("/", 1)[-1]
            if not filename or filename in {".", ".."}:
                st.error("The uploaded file has an invalid filename.")
                continue

            prefix = config.s3_upload_prefix.strip("/")
            unique_name = f"{uuid4().hex}/{filename}"
            object_key = f"{prefix}/{unique_name}" if prefix else unique_name
            try:
                s3_client.put_object(
                    Bucket=bucket,
                    Key=object_key,
                    Body=file_bytes,
                    ContentType=uploaded_file.type or "application/octet-stream",
                )
            except (BotoCoreError, ClientError) as exc:
                logger.exception("S3 upload failed for %s", uploaded_file.name)
                st.error(
                    f"Could not upload {uploaded_file.name} to S3 "
                    f"({type(exc).__name__}). Check AWS credentials and s3:PutObject permission."
                )
                continue

            s3_uri = f"s3://{bucket}/{object_key}"
            if not trigger_url:
                st.success(f"Uploaded {uploaded_file.name} to {s3_uri}.")
                st.info(
                    "Ingestion will start automatically only if an S3 event "
                    "notification is configured for this bucket/prefix."
                )
                continue

            try:
                response = requests.post(
                    trigger_url,
                    json={
                        "bucket": bucket,
                        "key": object_key,
                        "collection_name": config.vector_collection_name,
                    },
                    headers=headers,
                    timeout=(10, 60),
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                logger.exception("Ingestion trigger failed for %s", s3_uri)
                status = getattr(getattr(exc, "response", None), "status_code", None)
                status_text = f" (HTTP {status})" if status else ""
                st.error(
                    f"Uploaded to S3, but could not trigger ingestion{status_text}. "
                    "Check the worker endpoint before retrying."
                )
            else:
                st.success(
                    f"Uploaded {uploaded_file.name} and triggered ingestion "
                    f"for {s3_uri} (HTTP {response.status_code})."
                )


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block
            if isinstance(block, str)
            else block.get("text", "")
            for block in content
            if isinstance(block, str)
            or (isinstance(block, dict) and isinstance(block.get("text"), str))
        )
    return ""


def _message_role(message: Any) -> str | None:
    if isinstance(message, dict):
        kind = message.get("type") or message.get("role")
    else:
        kind = getattr(message, "type", None) or getattr(message, "role", None)
    if kind in {"human", "user"}:
        return "user"
    if kind in {"ai", "assistant"}:
        return "assistant"
    return None


def _load_thread_messages(client: Any, thread_id: str) -> list[dict[str, str]]:
    state = client.threads.get_state(thread_id)
    values = state.get("values", {}) if isinstance(state, dict) else getattr(state, "values", {})
    messages = values.get("messages", []) if isinstance(values, dict) else []

    history = []
    for message in messages:
        role = _message_role(message)
        content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
        text = _content_text(content)
        if role and text:
            history.append({"role": role, "content": text})
    return history


def _extract_answer(result: Any) -> str:
    if isinstance(result, list):
        result = result[-1] if result else {}
    if not isinstance(result, dict):
        raise RuntimeError("The chat workflow returned an unexpected response.")

    answer = result.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer

    messages = result.get("messages", [])
    if messages:
        last_message = messages[-1]
        content = (
            last_message.get("content")
            if isinstance(last_message, dict)
            else getattr(last_message, "content", None)
        )
        answer = _content_text(content)
        if answer.strip():
            return answer
    raise RuntimeError("The chat workflow returned no answer.")


def _chat_page() -> None:
    config = settings()
    st.title("Chat with your documents")
    st.caption(f"Collection: {config.vector_collection_name}")

    client = _get_langgraph_client(config.langgraph_api_url, config.langgraph_api_key)

    if "chat_thread_id" not in st.session_state:
        st.session_state.chat_thread_id = None

    with st.sidebar:
        if st.button("New conversation", key="new_chat"):
            st.session_state.chat_thread_id = None
            st.rerun()

    if st.session_state.chat_thread_id is None:
        try:
            thread = client.threads.create()
            st.session_state.chat_thread_id = (
                thread.get("thread_id")
                if isinstance(thread, dict)
                else thread.thread_id
            )
        except Exception as exc:
            logger.exception("Could not create a LangGraph thread")
            st.error(
                "Could not reach the LangGraph server. Start it with `langgraph dev` "
                f"and verify LANGGRAPH_API_URL ({type(exc).__name__})."
            )
            return

    thread_id = st.session_state.chat_thread_id
    st.sidebar.caption(f"Thread: {thread_id}")

    try:
        history = _load_thread_messages(client, thread_id)
    except Exception:
        logger.exception("Could not load LangGraph thread history")
        history = []

    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask a question about your indexed documents")
    if not question:
        return

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching your documents..."):
            try:
                result = client.runs.wait(
                    thread_id,
                    config.langgraph_assistant_id,
                    input={
                        "messages": [{"role": "user", "content": question}],
                        "collection_name": config.vector_collection_name,
                    },
                )
                answer = _extract_answer(result)
            except Exception as exc:
                logger.exception("LangGraph chat request failed")
                st.error(
                    "The chat request failed. Check the LangGraph server and "
                    f"collection configuration ({type(exc).__name__})."
                )
            else:
                st.markdown(answer)


def main() -> None:
    st.set_page_config(page_title="Document QA", page_icon="📚", layout="wide")
    config = settings()
    firebase_config = {
        "api_key": config.firebase_api_key,
        "auth_domain": config.firebase_auth_domain,
        "project_id": _resolve_firebase_project_id(config),
    }
    firebase_env_names = {
        "api_key": "FIREBASE_API_KEY",
        "auth_domain": "FIREBASE_AUTH_DOMAIN",
        "project_id": "FIREBASE_PROJECT_ID",
    }
    missing_firebase_config = [
        firebase_env_names[name]
        for name, value in firebase_config.items()
        if not value
    ]
    if missing_firebase_config:
        st.error(
            "Firebase login is not configured. Missing: "
            + ", ".join(missing_firebase_config)
            + ". Add the exact variable names to .env."
        )
        return

    user = _active_firebase_user(config)
    if user:
        auth_result = _firebase_auth_component(
            **firebase_config,
            authenticated=True,
            key="firebase_auth_gate",
            default=None,
        )
    else:
        st.title("Sign in to Document QA")
        st.write("Sign in or create an account to access file uploads and chat.")
        notice = st.session_state.pop("firebase_auth_notice", None)
        if notice:
            st.warning(notice)
        auth_result = _firebase_auth_component(
            **firebase_config,
            authenticated=False,
            key="firebase_auth_gate",
            default=None,
        )

    if isinstance(auth_result, dict) and auth_result.get("signed_out"):
        st.session_state.pop("firebase_auth_user", None)
        st.session_state.pop("firebase_last_token", None)
        st.session_state.pop("chat_thread_id", None)
        st.rerun()

    if not user and isinstance(auth_result, dict):
        id_token = auth_result.get("id_token")
        if id_token and id_token != st.session_state.get("firebase_last_token"):
            st.session_state["firebase_last_token"] = id_token
            try:
                verified_user = _lookup_firebase_user(config, id_token)
            except ValueError:
                st.error("Firebase could not verify this sign-in. Please try again.")
            except requests.RequestException:
                st.error("Could not contact Firebase to verify your sign-in.")
            else:
                st.session_state["firebase_auth_user"] = {
                    **verified_user,
                    "id_token": id_token,
                    "verified_at": time.time(),
                }
                st.session_state.pop("chat_thread_id", None)
                st.rerun()
        elif auth_result.get("error"):
            st.error(f"Sign-in failed ({auth_result['error']}).")

    if not user:
        return

    st.sidebar.caption(
        f"Signed in as {user.get('email') or user.get('display_name') or user['uid']}"
    )
    pages = [
        st.Page(_upload_page, title="Upload files", icon="📤", default=True),
        st.Page(_chat_page, title="Chat", icon="💬"),
    ]
    st.navigation(pages, position="sidebar").run()


if __name__ == "__main__":
    main()

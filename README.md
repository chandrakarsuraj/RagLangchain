# Document QA with LangChain and LangGraph

A Streamlit application for authenticated, retrieval-augmented Q&A over documents. The UI uploads documents to S3; a separate ingestion worker indexes them in the configured PGVector collection. The LangGraph workflow handles chat only: question → retrieval → answer.

## Features

- Firebase Authentication with email/password sign-up and sign-in, plus Google sign-in.
- Streamlit pages for **Upload files** and **Chat**.
- S3 uploads for PDF and TXT files, with optional HTTP or S3-event worker triggering.
- PGVector retrieval and LangGraph-backed conversation threads.
- LangChain PII middleware that redacts common sensitive patterns before model calls and from model responses.

## Requirements

- Python 3.12+
- PostgreSQL with the `pgvector` extension for document vectors
- An AWS account and S3 bucket
- A Firebase project with Authentication enabled
- A separate ingestion worker that indexes uploaded objects into the same PGVector collection used by chat

## Setup

Install the project dependencies from the repository root:

```bash
uv sync
```

Create a local `.env` file in the repository root. Example settings:

```dotenv
# Required for Firebase login
FIREBASE_API_KEY=your-firebase-web-api-key
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
FIREBASE_PROJECT_ID=your-project-id

# Required for chat and document retrieval
OPENAI_API_KEY=your-openai-api-key
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/raglangchain

# LangGraph API server; this is the local default
LANGGRAPH_API_URL=http://127.0.0.1:2024
LANGGRAPH_ASSISTANT_ID=rag_agent

# S3 uploads
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name
S3_UPLOAD_PREFIX=uploads

# Set both for local access keys, or omit them when using an AWS profile/role.
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# Must match the collection populated by the ingestion worker
VECTOR_COLLECTION_NAME=raglangchain

# Optional direct worker trigger. Omit when using an S3 event notification.
INGEST_WORKER_URL=https://your-worker.example.com/ingest
INGEST_WORKER_API_KEY=your-worker-bearer-token
```

Use a real `.env` locally, but do not commit it. Firebase's web API key is part of the browser-facing Firebase configuration; it is not a service-account credential. Do not put a Firebase service-account private key in the Streamlit app.

`FIREBASE_PROJECT_ID` can be inferred when the auth domain uses Firebase's default `<project-id>.firebaseapp.com` format. Set it explicitly when using a custom auth domain.

In the Firebase Console:

1. Enable **Email/Password** and **Google** under **Authentication → Sign-in method**.
2. Add `localhost` and the deployed Streamlit hostname to **Authentication → Settings → Authorized domains**.
3. Confirm the Firebase web configuration values in **Project settings → General**.

The `.env` file must use valid `KEY=value` lines. Quote values containing special characters when appropriate; malformed dotenv lines may cause settings to be skipped.

## Run locally

Start the LangGraph API server in one terminal:

```bash
uv run langgraph dev
```

Start Streamlit from the repository root in another terminal:

```bash
uv run streamlit run main.py
```

Sign in or create an account first. Then use **Upload files** to submit documents and **Chat** to ask questions about documents already indexed by the worker.

## Upload and ingestion flow

1. The upload page validates the file type and configured size limit (10 MiB by default).
2. Streamlit uploads each file to `s3://S3_BUCKET/S3_UPLOAD_PREFIX/<unique-id>/<filename>`.
3. If `INGEST_WORKER_URL` is set, Streamlit sends the worker a JSON `POST` after the S3 upload:

   ```json
   {
     "bucket": "your-bucket-name",
     "key": "uploads/<unique-id>/document.pdf",
     "collection_name": "raglangchain"
   }
   ```

   The endpoint must accept this contract. If `INGEST_WORKER_API_KEY` is set, the request includes an `Authorization: Bearer ...` header.

4. If `INGEST_WORKER_URL` is omitted, the upload page only uploads the object. Ingestion will start only if the S3 bucket has an `ObjectCreated` notification configured to invoke or enqueue the ingestion worker for the upload prefix.

The Streamlit identity needs `s3:PutObject` access to the configured bucket/prefix. The separate ingestion worker needs `s3:GetObject` and permission to write to PGVector. The worker and chat workflow must use the same collection name (`VECTOR_COLLECTION_NAME`, default `raglangchain`).

For production, prefer an IAM role or other short-lived AWS credentials over long-lived access keys. Keep the LangGraph API server private or behind an authenticated gateway; Firebase gating in Streamlit does not protect a separately exposed API endpoint.

## Chat and persistence

The LangGraph graph is configured in `langgraph.json` and exported as `graph` from `src/agents/rag_agent.py`. It contains three QA nodes:

1. `question_node` extracts the latest user question.
2. `retrieval_node` searches the configured PGVector collection.
3. `answer_node` builds an answer with the configured chat model and PII middleware.

The LangGraph API server persists thread state. Reusing a thread ID keeps that conversation's message history. `langgraph dev` is intended for local development; use the LangGraph production server/PostgreSQL setup for durable deployed persistence. The project also exposes `setup_persistence()` and `create_workflow()` for direct Python use with `PostgresSaver` and `PostgresStore`.

PII redaction covers common patterns such as email addresses, credit cards, IP/MAC addresses, US SSNs, phone numbers, and selected API-token formats. Pattern-based detection is best-effort, not a complete DLP system. Raw user messages may still be stored in LangGraph checkpoints; the middleware protects model-bound input and model output.

## Troubleshooting

- **Firebase login says configuration is missing:** verify `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, and `FIREBASE_PROJECT_ID` are valid dotenv entries. The UI can derive the project ID only from the default `*.firebaseapp.com` auth domain.
- **Google sign-in fails:** verify Google is enabled as a Firebase provider and the current host is in Authorized domains. Browser popup restrictions may also prevent Google sign-in.
- **S3 upload fails:** check `AWS_REGION`, `S3_BUCKET`, the credential chain, bucket region, and `s3:PutObject` permission.
- **File uploads but is not ingested:** configure `INGEST_WORKER_URL` with the worker's JSON endpoint, or configure an S3 `ObjectCreated` notification. S3 upload alone does not invoke a worker.
- **Chat cannot connect:** start `langgraph dev` and check `LANGGRAPH_API_URL` and the graph ID `rag_agent`.
- **No documents are retrieved:** verify the ingestion worker completed indexing and used the same PGVector database and collection configured for chat.

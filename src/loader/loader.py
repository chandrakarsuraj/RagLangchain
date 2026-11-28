"""Load PDF and plain-text files into LangChain documents."""

from pathlib import Path

from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document


def load_documents(source: str | Path) -> list[Document]:
    """Load a PDF or text file, or all supported files in a directory.

    Directories are searched recursively for ``.pdf`` and ``.txt`` files.
    LangChain loader metadata (including the source path and PDF page number)
    is preserved on each returned document.

    Args:
        source: Path to a PDF/text file or a directory containing those files.

    Returns:
        The loaded LangChain documents.

    Raises:
        FileNotFoundError: If ``source`` does not exist.
        ValueError: If ``source`` is a file with an unsupported extension.
    """
    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Document source does not exist: {path}")

    if path.is_file():
        return load_file(path)

    if not path.is_dir():
        raise ValueError(f"Document source is not a file or directory: {path}")

    documents: list[Document] = []
    for pattern, loader_cls, loader_kwargs in (
        ("**/*.pdf", PyPDFLoader, {}),
        ("**/*.txt", TextLoader, {"encoding": "utf-8"}),
    ):
        directory_loader = DirectoryLoader(
            str(path),
            glob=pattern,
            loader_cls=loader_cls,
            loader_kwargs=loader_kwargs,
            recursive=True,
            silent_errors=False,
        )
        documents.extend(directory_loader.load())

    return documents


def load_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return PyPDFLoader(str(path)).load()
    if suffix == ".txt":
        return TextLoader(str(path), encoding="utf-8").load()

    raise ValueError(
        f"Unsupported document type {suffix!r} for {path}. Supported types: .pdf, .txt"
    )

"""The embedding model of the RAG part and its tokenizer (one place, so chunking and search use the same model)."""
from pathlib import Path

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "fastembed"


def embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(EMBED_MODEL, cache_dir=str(CACHE_DIR))


def token_counter():
    """text -> number of tokens the embedding model sees (without the 512-token cut-off)."""
    tok = embedder().model.tokenizer
    tok.no_truncation()
    return lambda text: len(tok.encode(text).ids)


RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


def reranker():
    """(query, [text]) -> [relevance score]: a cross-encoder that reads the query and a chunk together (512 tokens)."""
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    model = TextCrossEncoder(RERANK_MODEL, cache_dir=str(CACHE_DIR))
    return lambda query, texts: [float(s) for s in model.rerank(query, texts)]


def embed_fns():
    """(embed_docs, embed_query) of the embedding model; both return plain lists of floats."""
    model = embedder()
    docs = lambda texts: [v.tolist() for v in model.embed(texts, batch_size=32)]
    query = lambda text: next(iter(model.query_embed([text]))).tolist()
    return docs, query

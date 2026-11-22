"""Checks of the corpus tools with the real chunks and manifest of task 2 and a fake search (no network, no models):
python tests/test_corpus_tools.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.limits import Limits
from agent.llm import ChatResult, ToolCall
from agent.loop import run_agent
from agent.trace import Trace
from tools.corpus import Corpus
from tools.corpus_tools import TEXT_CHARS, make_corpus_tools
from tools.registry import ToolRegistry

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


class FakeRetriever:
    """Returns the given chunk ids with the given scores, filtered like the real search; records the calls."""

    def __init__(self, corpus, scored):
        self.corpus, self.scored, self.calls = corpus, scored, []

    def search(self, query, k, mode, filters):
        self.calls.append({"query": query, "k": k, "mode": mode, "filters": filters})
        out = []
        for cid, s in self.scored:
            c = self.corpus.chunks[cid]
            if all(c.get(f) == v for f, v in (filters or {}).items()):
                out.append({**c, "score": s})
        return out[:k]


corpus = Corpus()
ids = list(corpus.chunks)
pol = [c for c in ids if c.startswith("remote_work_policy#")]
pol23 = [c for c in ids if c.startswith("remote_work_policy_2023#")]
long_id = max(ids, key=lambda c: len(corpus.chunks[c]["text"]))


def tools_with(scored):
    corpus._retriever = FakeRetriever(corpus, scored)
    return ToolRegistry(make_corpus_tools(corpus, floor=-2.0)), corpus._retriever


def call(reg, name, args):
    return reg.execute(name, json.dumps(args), 5)


# --- schemas and descriptions
reg, _ = tools_with([])
names = [s["function"]["name"] for s in reg.schemas()]
check("three tools: search_corpus, get_passage, list_documents", names == ["search_corpus", "get_passage", "list_documents"])
check("descriptions come from prompts/tools/*.yaml with a version",
      all(t.version in ("v1", "v2") and "Do NOT" in t.description for t in reg.tools.values()))
check("all corpus tools are read-only and safe to repeat", all(t.safe and not t.side_effect for t in reg.tools.values()))
check("search schema: query required, k limited to 10",
      reg.schemas()[0]["function"]["parameters"]["required"] == ["query"]
      and reg.schemas()[0]["function"]["parameters"]["properties"]["k"]["maximum"] == 10)

# --- search_corpus
reg, fake = tools_with([(pol[1], 6.0), (pol23[1], 5.5), (long_id, 1.0), (ids[0], -5.0)])
out = call(reg, "search_corpus", {"query": "remote days per week", "k": 10})
data = json.loads(out.content)
refs = [r["ref"] for r in data["results"]]
check("search: hybrid_rerank with k passed through", fake.calls[-1]["mode"] == "hybrid_rerank" and fake.calls[-1]["k"] == 10)
check("search: hits below MIN_SCORE are dropped", ids[0] not in refs and refs == [pol[1], pol23[1], long_id])
check("search: results carry ref, document, section, page and score",
      {"ref", "doc_id", "title", "section", "page", "date", "score", "text"} <= set(data["results"][0]))
check("search: two policy versions are marked NEWEST / OLDER",
      data["results"][0]["version_mark"] == "NEWEST VERSION" and data["results"][1]["version_mark"] == "OLDER VERSION"
      and data["results"][2]["version_mark"] is None)
long_res = data["results"][2]
check(f"search: long text cut to {TEXT_CHARS} chars and marked truncated",
      len(long_res["text"]) == TEXT_CHARS and long_res["truncated"] is True and data["results"][0]["truncated"] is False)

reg, fake = tools_with([(pol[1], 6.0), (pol23[1], 5.5)])
data = json.loads(call(reg, "search_corpus", {"query": "remote days", "year": 2023}).content)
check("search: year filter reaches the search and the results",
      fake.calls[-1]["filters"] == {"year": 2023} and [r["ref"] for r in data["results"]] == [pol23[1]])
data = json.loads(call(reg, "search_corpus", {"query": "remote days", "doc_id": "remote_work_policy"}).content)
check("search: doc_id filter", fake.calls[-1]["filters"] == {"doc_id": "remote_work_policy"})

out = call(reg, "search_corpus", {"query": "remote days", "doc_id": "no_such_doc"})
check("search: unknown doc_id -> ERROR: invalid_args pointing to list_documents, no search made",
      out.error_kind == "invalid_args" and "list_documents" in out.content and fake.calls[-1]["filters"] != {"doc_id": "no_such_doc"})
check("search: k above 10 -> invalid_args", call(reg, "search_corpus", {"query": "x y z", "k": 50}).error_kind == "invalid_args")
out = call(reg, "search_corpus", {"query": "дні віддаленої роботи"})
check("search: a Cyrillic query -> invalid_args asking for English", out.error_kind == "invalid_args" and "English" in out.content)
check("search: too short query -> invalid_args", call(reg, "search_corpus", {"query": "x"}).error_kind == "invalid_args")

reg, _ = tools_with([(ids[0], -7.0), (ids[1], -3.0)])
data = json.loads(call(reg, "search_corpus", {"query": "vacation days of astronauts"}).content)
check("search: only weak hits -> empty results and a note to stop searching",
      data["results"] == [] and "2 weak hits dropped" in data["note"] and "do not cover" in data["note"])

# --- get_passage
reg, _ = tools_with([])
mid = pol[1]
data = json.loads(call(reg, "get_passage", {"ref": mid, "before": 1, "after": 1}).content)
check("get_passage: the passage with its neighbours in document order",
      [p["ref"] for p in data["passages"]] == [pol[0], pol[1], pol[2]])
check("get_passage: full text, not cut", data["passages"][1]["text"] == corpus.chunks[mid]["text"])
data = json.loads(call(reg, "get_passage", {"ref": pol[0], "before": 2}).content)
check("get_passage: no passages before the first one of a document", [p["ref"] for p in data["passages"]] == [pol[0]])
data = json.loads(call(reg, "get_passage", {"ref": long_id}).content)
check("get_passage: a long passage comes whole", len(data["passages"][0]["text"]) > TEXT_CHARS)
out = call(reg, "get_passage", {"ref": "remote_work_policy#9999"})
check("get_passage: unknown ref -> invalid_args pointing to search_corpus", out.error_kind == "invalid_args" and "search_corpus" in out.content)
check("get_passage: malformed ref -> invalid_args", call(reg, "get_passage", {"ref": "../../etc/passwd"}).error_kind == "invalid_args")
check("get_passage: at most 2 neighbours", call(reg, "get_passage", {"ref": mid, "after": 5}).error_kind == "invalid_args")

# --- list_documents
data = json.loads(call(reg, "list_documents", {}).content)
check("list_documents: all 42 documents of the corpus", data["total"] == 42 == len(data["documents"]))
check("list_documents: metadata only, no text", "text" not in data["documents"][0] and "title" in data["documents"][0])
data = json.loads(call(reg, "list_documents", {"title_contains": "remote work"}).content)
check("list_documents: title filter, any case, with the other version as near duplicate",
      [d["doc_id"] for d in data["documents"]] == ["remote_work_policy", "remote_work_policy_2023"]
      and data["documents"][0]["near_duplicates"] == ["remote_work_policy_2023"])
data = json.loads(call(reg, "list_documents", {"year": 2023}).content)
check("list_documents: year filter", "remote_work_policy_2023" in [d["doc_id"] for d in data["documents"]]
      and all(d["year"] == 2023 for d in data["documents"]))

# --- in the loop: search, then an answer that cites the ref
reg, _ = tools_with([(pol[1], 6.0)])


class Scripted:
    name = "scripted"

    def __init__(self, *results):
        self.results, self.n, self.seen = list(results), 0, []

    def chat(self, messages, tools, timeout_s=None):
        self.seen.append(messages)
        self.n += 1
        return self.results[min(self.n - 1, len(self.results) - 1)]


m = Scripted(ChatResult(None, [ToolCall("c0", "search_corpus", '{"query": "remote work days per week"}')], 100, 10, 0.0),
             ChatResult(f"Up to two days per week [{pol[1]}].", tokens_in=100, tokens_out=10))
r = run_agent("How many days can I work from home?", m, reg, Limits(), "sys", Trace())
check("loop: search result reaches the model and the answer cites its ref",
      r.stop_reason == "answered" and pol[1] in m.seen[1][-1]["content"] and pol[1] in r.answer)
check("loop: the search call is recorded", r.tool_calls[0]["name"] == "search_corpus")
t = Trace()
run_agent("q", Scripted(ChatResult("hi")), reg, Limits(), "sys", t)
check("trace: tool versions at the start", t.of("start")[0]["tool_versions"] == {"search_corpus": "v2", "get_passage": "v1", "list_documents": "v1"})

print(f"\n{'FAILED: ' + str(len(FAILED)) if FAILED else 'all checks passed'}")
sys.exit(1 if FAILED else 0)

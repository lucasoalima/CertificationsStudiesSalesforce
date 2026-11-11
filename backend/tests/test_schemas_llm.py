import pytest
from pydantic import ValidationError

from qgen.llm import FakeLLM, LLMError, complete_json, extract_json
from qgen.schemas import Question


def test_question_validation():
    q = Question(q="x?", o=["a", "b", "c", "d"], a=[2, 0])
    assert q.a == [0, 2] and q.answers() == [0, 2]
    assert Question(q="x?", o=["a", "b", "c"], a=[1]).a == 1
    with pytest.raises(ValidationError):
        Question(q="x?", o=["a", "a", "c"], a=0)
    with pytest.raises(ValidationError):
        Question(q="x?", o=["a", "b", "c"], a=5)
    assert Question(q="x?", o=["a", "b", "c"]).answers() == []


def test_extract_json_variants():
    assert extract_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert extract_json('Sure! Here it is: {"x": [1, 2]} hope it helps') == {"x": [1, 2]}
    with pytest.raises(LLMError):
        extract_json("no json at all")


def test_complete_json_retries_once():
    replies = iter(["oops", '{"ok": true}'])
    llm = FakeLLM(lambda p: next(replies))
    assert complete_json(llm, "give json") == {"ok": True}
    assert llm.usage.failures == 1 and llm.usage.calls == 2

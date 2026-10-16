import os

from youtube_fitnes_talyhs import youtube


def test_script_word_count_handles_contractions():
    assert youtube.script_word_count("Don't rush—move with control.") == 5


def test_target_word_range_for_short_lengths():
    assert youtube.target_word_range(30) == (52, 72)
    assert youtube.target_word_range(45) == (82, 105)
    assert youtube.target_word_range(60) == (112, 135)


def test_parse_list_supports_json_and_commas():
    assert youtube.parse_list('["push ups", "squat form"]') == ["push ups", "squat form"]
    assert youtube.parse_list("push ups, squat form") == ["push ups", "squat form"]


def test_caption_chunks_limits_words_and_line_length():
    chunks = youtube.caption_chunks("Build strength with slow controlled movements today".split())
    assert chunks
    assert all(len(chunk) <= 5 for chunk in chunks)
    assert all(len(" ".join(chunk)) <= 34 for chunk in chunks)


def test_ass_timestamp_format():
    assert youtube.ass_timestamp(1.239) == "0:00:01.23"


def test_captions_are_created_with_estimated_timing(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_WHISPER_CAPTIONS", "NO")
    target = tmp_path / "subtitles.ass"
    youtube.make_ass_captions("Move slowly and breathe with control.", 3.0, target)
    content = target.read_text(encoding="utf-8")
    assert "[Events]" in content
    assert "Dialogue:" in content
    assert r"{\kf" in content

def test_footage_queries_include_exact_topic_and_deduplicate():
    data = {
        "title": "Better Push-Up Form",
        "topic": "proper push-up form for beginners",
        "search_terms": ["push-up form demonstration", "push-up form demonstration"],
    }
    queries = youtube.footage_queries(data)
    assert queries[0] == "push-up form demonstration"
    assert len(queries) == len({query.casefold() for query in queries})
    assert any("proper push-up form" in query for query in queries)


def test_upload_requires_explicit_confirmation(monkeypatch, capsys):
    monkeypatch.setattr(youtube, "MODE", "prepare")
    youtube.upload("unused.mp4", {"title": "Test"}, [])
    assert "not uploaded" in capsys.readouterr().out

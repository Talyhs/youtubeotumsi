from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from studio.state import init_db, create_job, set_step, completed_step, list_jobs, add_calendar_item, list_calendar
from studio.media import AUDIO_PROFILES

def test_state_checkpoint_and_job(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    job_id = create_job("Beyin", "az", db)
    set_step(job_id, "script", "done", "test", db)
    assert completed_step(job_id, "script", db)
    assert list_jobs(db_path=db)[0]["topic"] == "Beyin"

def test_calendar(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    add_calendar_item("Kosmos", "az", "2026-11-01", "test", db)
    rows = list_calendar(db)
    assert len(rows) == 1 and rows[0]["topic"] == "Kosmos"

def test_audio_profiles_are_defined():
    assert {"natural", "clear_voice", "soft"} <= set(AUDIO_PROFILES)
    assert all(isinstance(v, str) and v for v in AUDIO_PROFILES.values())

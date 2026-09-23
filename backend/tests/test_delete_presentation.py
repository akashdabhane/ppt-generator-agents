import os
from datetime import datetime, timedelta

from app.models import Project, Presentation, PresentationSlide, PresentationStatus


def _make_presentation(env, status=PresentationStatus.COMPLETED, created_at=None):
    db, storage = env["db"], env["storage"]
    project = Project(user_id=env["owner"].id, name="Q3")
    db.add(project)
    db.commit()
    pres = Presentation(project_id=project.id, title="Deck", prompt="p", theme="Professional", status=status)
    if created_at:
        pres.created_at = created_at
    path = storage.get_presentation_path(project.id, "deck")
    with open(path, "wb") as f:
        f.write(b"pptx")
    pres.pptx_path = path
    db.add(pres)
    db.commit()
    db.add(PresentationSlide(presentation_id=pres.id, slide_number=1, slide_type="title", content_json={}))
    db.commit()
    return project.id, pres.id, path


def test_delete_presentation_removes_row_slides_and_file(api_env):
    project_id, pres_id, path = _make_presentation(api_env)

    res = api_env["client"].delete(f"/presentations/{pres_id}")

    assert res.status_code == 204
    db = api_env["db"]
    db.expire_all()
    assert db.get(Presentation, pres_id) is None
    assert db.query(PresentationSlide).filter_by(presentation_id=pres_id).count() == 0
    assert db.get(Project, project_id) is not None
    assert not os.path.exists(path)


def test_delete_presentation_of_another_user_is_404(api_env):
    _, pres_id, path = _make_presentation(api_env)
    api_env["current"]["user"] = api_env["other"]

    res = api_env["client"].delete(f"/presentations/{pres_id}")

    assert res.status_code == 404
    api_env["db"].expire_all()
    assert api_env["db"].get(Presentation, pres_id) is not None
    assert os.path.exists(path)


def test_delete_presentation_while_generating_is_409(api_env):
    _, pres_id, path = _make_presentation(api_env, status=PresentationStatus.GENERATING)

    res = api_env["client"].delete(f"/presentations/{pres_id}")

    assert res.status_code == 409
    assert os.path.exists(path)


def test_delete_stale_generating_presentation_is_allowed(api_env):
    _, pres_id, _ = _make_presentation(
        api_env,
        status=PresentationStatus.GENERATING,
        created_at=datetime.utcnow() - timedelta(hours=1),
    )

    res = api_env["client"].delete(f"/presentations/{pres_id}")

    assert res.status_code == 204

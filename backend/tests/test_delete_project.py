import os

from app.models import Project, Document


def _make_project_with_doc(env):
    db, storage = env["db"], env["storage"]
    project = Project(user_id=env["owner"].id, name="Q3")
    db.add(project)
    db.commit()
    path = os.path.join(storage.get_project_dir(project.id), "documents", "doc.txt")
    with open(path, "w") as f:
        f.write("private")
    doc = Document(project_id=project.id, filename="doc.txt", file_type="txt", file_size=7, storage_path=path)
    db.add(doc)
    db.commit()
    return project.id, doc.id, path


def test_delete_project_removes_rows_files_and_vectors(api_env):
    project_id, doc_id, path = _make_project_with_doc(api_env)

    res = api_env["client"].delete(f"/projects/{project_id}")

    assert res.status_code == 204
    api_env["db"].expire_all()
    assert api_env["db"].get(Project, project_id) is None
    assert api_env["db"].get(Document, doc_id) is None
    assert not os.path.exists(path)
    assert not os.path.exists(os.path.join(api_env["storage"].base_dir, "projects", project_id))
    assert api_env["vectors"].deleted == [(project_id, doc_id)]


def test_delete_project_of_another_user_is_404(api_env):
    project_id, _, path = _make_project_with_doc(api_env)
    api_env["current"]["user"] = api_env["other"]

    res = api_env["client"].delete(f"/projects/{project_id}")

    assert res.status_code == 404
    api_env["db"].expire_all()
    assert api_env["db"].get(Project, project_id) is not None
    assert os.path.exists(path)
    assert api_env["vectors"].deleted == []

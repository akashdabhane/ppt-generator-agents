import os
import shutil
from typing import BinaryIO
from app.core.config import settings


class StorageService:
    def __init__(self, base_dir: str = settings.STORAGE_DIR):
        self.base_dir = base_dir

    def get_project_dir(self, project_id: str) -> str:
        project_dir = os.path.join(self.base_dir, "projects", project_id)
        os.makedirs(os.path.join(project_dir, "documents"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "presentations"), exist_ok=True)
        return project_dir

    def save_document(self, project_id: str, document_id: str, filename: str, file_obj: BinaryIO) -> str:
        project_dir = self.get_project_dir(project_id)
        file_ext = os.path.splitext(filename)[1]
        save_name = f"{document_id}{file_ext}"
        full_path = os.path.join(project_dir, "documents", save_name)
        
        with open(full_path, "wb") as f:
            shutil.copyfileobj(file_obj, f)
            
        return full_path

    def get_presentation_path(self, project_id: str, presentation_id: str) -> str:
        project_dir = self.get_project_dir(project_id)
        return os.path.join(project_dir, "presentations", f"{presentation_id}.pptx")

    def delete_file(self, file_path: str) -> bool:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False


storage_service = StorageService()

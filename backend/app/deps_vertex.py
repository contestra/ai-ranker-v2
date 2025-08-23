import os
from vertexai import init as vertex_init
from .google_creds import creds_info, enforce_wif_if_required

def init_vertex():
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ.get("VERTEX_LOCATION", "europe-west4")
    info = creds_info()
    enforce_wif_if_required(info)
    vertex_init(project=project, location=location)
    return info
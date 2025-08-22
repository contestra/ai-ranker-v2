#!/bin/bash
cd backend
source ../venv/bin/activate
echo "Starting AI Ranker V2 Backend..."
echo "API Docs will be available at: http://localhost:8000/docs"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_and_get_tasks():
    resp = client.post('/tasks', json={'description':'Test task'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['description'] == 'Test task'

    resp = client.get('/tasks')
    assert resp.status_code == 200
    tasks = resp.json()
    assert any(t['description'] == 'Test task' for t in tasks)

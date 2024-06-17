import os

import pytest

import tests


@pytest.mark.routes
def test_openapi_json_output(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    with open(
        os.path.join(
            tests.conftest.test_outputs_dir,
            f"openapi.json",
        ),
        "wb",
    ) as f:
        f.write(response.content)

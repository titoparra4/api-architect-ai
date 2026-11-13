"""Black-box API tests for the Insurance Policy Management API (examples/api-design-example).

Run only against an APPROVED test environment:

    export API_BASE_URL=https://api.sandbox.example-insurer.com/v1
    export TOKEN_ORG_A=...        # policies:read policies:write, org A
    export TOKEN_ORG_B=...        # policies:read policies:write, org B
    export TOKEN_READ_ONLY=...    # policies:read only, org A
    export TOKEN_EXPIRED=...      # expired token issued by the same IdP
    python3 -m pip install "pytest>=8,<9" "requests>=2.32,<3" "jsonschema>=4.21,<5" "PyYAML>=6.0.1,<7"
    python3 -m pytest examples/api-testing-example/pytest-suite -v

The whole module is skipped when API_BASE_URL is not set, so it never runs by accident in CI.
Tokens are read from the environment and never printed.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

requests = pytest.importorskip("requests")
jsonschema = pytest.importorskip("jsonschema")
yaml = pytest.importorskip("yaml")

BASE = os.environ.get("API_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="API_BASE_URL not set (approved test environment required)")

CONTRACT = Path(__file__).resolve().parents[2] / "api-design-example" / "openapi.yaml"
TIMEOUT = 10


# ---------------------------------------------------------------- fixtures / helpers

@pytest.fixture(scope="session")
def spec():
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def schema_for(spec, name):
    """Return a component schema with local refs resolvable by jsonschema."""
    return {"$ref": "#/components/schemas/%s" % name, "components": spec["components"]}


def token(name):
    value = os.environ.get(name)
    if not value:
        pytest.skip("%s not configured" % name)
    return value


def headers(token_value, **extra):
    h = {"Authorization": "Bearer %s" % token_value, "Accept": "application/json"}
    h.update(extra)
    return h


def new_policy_payload():
    return {
        "productCode": "MOTOR-STD",
        "holder": {"customerId": "CUS-TEST-%s" % uuid.uuid4().hex[:8]},
        "effectiveDate": (date.today() + timedelta(days=7)).isoformat(),
        "premium": {"amount": "540.00", "currency": "EUR"},
    }


def assert_problem(response, status):
    assert response.status_code == status, response.text[:300]
    assert response.headers.get("Content-Type", "").startswith("application/problem+json")
    body = response.json()
    assert body.get("status") == status
    assert "title" in body
    serialized = response.text.lower()
    assert "stack" not in serialized and "exception" not in serialized and "sql" not in serialized


@pytest.fixture
def created_policy():
    payload = new_policy_payload()
    r = requests.post("%s/policies" % BASE, json=payload, timeout=TIMEOUT,
                      headers=headers(token("TOKEN_ORG_A"), **{"Idempotency-Key": str(uuid.uuid4())}))
    assert r.status_code == 201, r.text[:300]
    return payload, r


# ---------------------------------------------------------------- functional

def test_create_policy_returns_draft_with_location_etag_and_valid_schema(spec, created_policy):
    payload, r = created_policy
    body = r.json()
    jsonschema.validate(body, schema_for(spec, "Policy"))
    assert r.headers["Location"].endswith("/policies/%s" % body["id"])
    assert r.headers.get("ETag")
    assert body["status"] == "DRAFT"
    assert body["holder"] == payload["holder"]
    assert body["premium"] == payload["premium"]
    assert body["cancellation"] is None


def test_idempotent_retry_returns_same_policy(created_policy):
    payload = new_policy_payload()
    key = str(uuid.uuid4())
    h = headers(token("TOKEN_ORG_A"), **{"Idempotency-Key": key})
    first = requests.post("%s/policies" % BASE, json=payload, headers=h, timeout=TIMEOUT)
    second = requests.post("%s/policies" % BASE, json=payload, headers=h, timeout=TIMEOUT)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_same_idempotency_key_with_different_payload_is_rejected():
    key = str(uuid.uuid4())
    h = headers(token("TOKEN_ORG_A"), **{"Idempotency-Key": key})
    assert requests.post("%s/policies" % BASE, json=new_policy_payload(), headers=h, timeout=TIMEOUT).status_code == 201
    r = requests.post("%s/policies" % BASE, json=new_policy_payload(), headers=h, timeout=TIMEOUT)
    assert_problem(r, 422)


def test_read_only_fields_are_rejected_on_create():
    payload = dict(new_policy_payload(), status="ACTIVE", id=str(uuid.uuid4()))
    r = requests.post("%s/policies" % BASE, json=payload, timeout=TIMEOUT,
                      headers=headers(token("TOKEN_ORG_A"), **{"Idempotency-Key": str(uuid.uuid4())}))
    assert_problem(r, 400)


@pytest.mark.parametrize("limit,expected", [(1, 200), (100, 200), (0, 400), (101, 400)])
def test_limit_boundaries(limit, expected):
    r = requests.get("%s/policies" % BASE, params={"limit": limit}, headers=headers(token("TOKEN_ORG_A")), timeout=TIMEOUT)
    if expected == 200:
        assert r.status_code == 200
        assert len(r.json()["data"]) <= limit
        assert r.json()["page"]["limit"] == limit
    else:
        assert_problem(r, 400)


# ---------------------------------------------------------------- security

def test_other_organization_cannot_read_policy(created_policy):
    policy_id = created_policy[1].json()["id"]
    r = requests.get("%s/policies/%s" % (BASE, policy_id), headers=headers(token("TOKEN_ORG_B")), timeout=TIMEOUT)
    assert_problem(r, 404)
    assert not {"holder", "premium", "policyNumber", "productCode"} & set(r.json())


def test_other_organization_list_does_not_include_policy(created_policy):
    policy_id = created_policy[1].json()["id"]
    r = requests.get("%s/policies" % BASE, params={"limit": 100}, headers=headers(token("TOKEN_ORG_B")), timeout=TIMEOUT)
    assert r.status_code == 200
    assert policy_id not in {p["id"] for p in r.json()["data"]}


def test_missing_scope_cannot_cancel(created_policy):
    policy_id = created_policy[1].json()["id"]
    r = requests.post("%s/policies/%s/cancellation" % (BASE, policy_id),
                      json={"reason": "CUSTOMER_REQUEST", "effectiveDate": date.today().isoformat()},
                      headers=headers(token("TOKEN_READ_ONLY"), **{"Idempotency-Key": str(uuid.uuid4()), "If-Match": "*"}),
                      timeout=TIMEOUT)
    assert_problem(r, 403)


@pytest.mark.parametrize("auth", [None, "Bearer not-a-jwt", "EXPIRED"])
def test_invalid_credentials_are_rejected(auth):
    h = {"Accept": "application/json"}
    if auth == "EXPIRED":
        h["Authorization"] = "Bearer %s" % token("TOKEN_EXPIRED")
    elif auth:
        h["Authorization"] = auth
    r = requests.get("%s/policies" % BASE, headers=h, timeout=TIMEOUT)
    assert_problem(r, 401)
    assert "Bearer" in r.headers.get("WWW-Authenticate", "")


# ---------------------------------------------------------------- concurrency / state

def test_stale_etag_is_rejected_and_state_unchanged(created_policy):
    body = created_policy[1].json()
    url = "%s/policies/%s" % (BASE, body["id"])
    r = requests.patch(url, json={"premium": {"amount": "600.00", "currency": "EUR"}}, timeout=TIMEOUT,
                       headers=headers(token("TOKEN_ORG_A"), **{"If-Match": '"stale"',
                                                                 "Content-Type": "application/merge-patch+json"}))
    assert_problem(r, 412)
    after = requests.get(url, headers=headers(token("TOKEN_ORG_A")), timeout=TIMEOUT).json()
    assert after["premium"] == body["premium"]


def test_cannot_activate_cancelled_policy(created_policy):
    body = created_policy[1].json()
    base = "%s/policies/%s" % (BASE, body["id"])
    h = headers(token("TOKEN_ORG_A"))
    etag = requests.get(base, headers=h, timeout=TIMEOUT).headers["ETag"]
    activate = requests.post(base + "/activation", timeout=TIMEOUT,
                             headers=dict(h, **{"Idempotency-Key": str(uuid.uuid4()), "If-Match": etag}))
    if activate.status_code != 200:
        pytest.skip("activation not permitted for test data in this environment")
    etag = requests.get(base, headers=h, timeout=TIMEOUT).headers["ETag"]
    cancel = requests.post(base + "/cancellation", json={"reason": "CUSTOMER_REQUEST",
                                                         "effectiveDate": date.today().isoformat()},
                           timeout=TIMEOUT, headers=dict(h, **{"Idempotency-Key": str(uuid.uuid4()), "If-Match": etag}))
    if cancel.status_code == 403:
        pytest.skip("TOKEN_ORG_A lacks policies:cancel")
    assert cancel.status_code == 200 and cancel.json()["status"] == "CANCELLED"
    etag = requests.get(base, headers=h, timeout=TIMEOUT).headers["ETag"]
    again = requests.post(base + "/activation", timeout=TIMEOUT,
                          headers=dict(h, **{"Idempotency-Key": str(uuid.uuid4()), "If-Match": etag}))
    assert_problem(again, 409)

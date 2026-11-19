"""Client-controlled proxy headers cannot bypass throttling."""

import hashlib
import hmac


def test_unsigned_forwarded_headers_cannot_evade_limit(app_factory):
    client = app_factory(proxy_shared_secret="synthetic-proxy-secret", rate_limit_requests=2)
    codes = [client.post("/api/v1/chat", json={"message": "Hello", "conversation_id": "proxy-test-0001"},
                         headers={"X-Forwarded-For": f"198.51.100.{i}", "X-Dy-Client-IP": f"198.51.100.{i}",
                                  "X-Dy-Client-Signature": "forged"}).status_code for i in range(1, 4)]
    assert codes == [200, 200, 429]


def test_signed_client_identities_have_independent_limits(app_factory):
    secret = "synthetic-proxy-secret"
    client = app_factory(proxy_shared_secret=secret, rate_limit_requests=1)
    codes = []
    for ip in ("198.51.100.1", "198.51.100.2", "198.51.100.1"):
        signature = hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()
        codes.append(client.post("/api/v1/chat", json={"message": "Hello", "conversation_id": "proxy-test-0001"},
                                 headers={"X-Dy-Client-IP": ip, "X-Dy-Client-Signature": signature}).status_code)
    assert codes == [200, 200, 429]

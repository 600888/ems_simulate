"""Real encrypted sessions, explicit trust and viewer/operator authorization."""

import base64
import socket

from asyncua import ua
import pytest

from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.core.security import certificate_info, generate_certificate, password_hash
from src.proto.opcua.core.vault import protect
from src.proto.opcua.server import OpcUaServer


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def identity(uri):
    cert, key = generate_certificate(uri, "127.0.0.1")
    return (
        {
            "mode": "SignAndEncrypt",
            "application_uri": uri,
            "certificate": base64.b64encode(cert).decode(),
            "trusted": [],
        },
        {"private_key": base64.b64encode(key).decode()},
        certificate_info(cert)["fingerprint"],
    )


def test_secrets_are_protected_and_roundtrip(tmp_path):
    ciphertext = protect("private password", tmp_path)
    assert "private password" not in ciphertext
    assert protect(ciphertext, tmp_path, decrypt=True) == "private password"


@pytest.mark.asyncio
async def test_encrypted_trust_user_roles_and_rejected_unknown_certificate():
    server_config, server_credentials, server_fingerprint = identity("urn:ems:test:secure:server")
    client_config, client_credentials, client_fingerprint = identity("urn:ems:test:secure:client")
    server_config.update(
        trusted=[client_fingerprint],
        users=[{"username": "reader", "role": "viewer"}, {"username": "writer", "role": "operator"}],
    )
    server_credentials.update({"user:reader": password_hash("reader123"), "user:writer": password_hash("writer123")})
    client_config.update(trusted=[server_fingerprint], identity="username", username="reader")
    client_credentials["password"] = "reader123"
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:ems:secure",
        definitions=[
            {
                "node_id": "ns=2;s=power",
                "browse_name": "Power",
                "data_type": "Double",
                "initial_value": 2.0,
                "writable": True,
            }
        ],
        features={"security": server_config},
        credentials=server_credentials,
    )
    reader = OpcUaClient(server.endpoint_url, features={"security": client_config}, credentials=client_credentials)
    writer = OpcUaClient(
        server.endpoint_url,
        features={"security": {**client_config, "username": "writer"}},
        credentials={**client_credentials, "password": "writer123"},
    )
    unknown = OpcUaClient(
        server.endpoint_url, features={"security": {**client_config, "trusted": []}}, credentials=client_credentials
    )
    try:
        await server.start()
        with pytest.raises(Exception, match="BadCertificateUntrusted"):
            await unknown.start()
        await reader.start()
        assert (await reader.read("ns=2;s=power"))["value"] == 2.0
        with pytest.raises(ua.UaStatusCodeError, match="BadUserAccessDenied"):
            await reader.write("ns=2;s=power", 3.0)
        await writer.start()
        assert (await writer.write("ns=2;s=power", 4.0))["value"] == 4.0
        transport, connection = server._core._server, writer._core._client
        updated = {
            **server_config,
            "users": [{"username": "reader", "role": "operator"}, {"username": "writer", "role": "viewer"}],
        }
        await server.configure_access(updated, server_credentials)
        assert (await reader.write("ns=2;s=power", 5.0))["value"] == 5.0
        with pytest.raises(ua.UaStatusCodeError, match="BadUserAccessDenied"):
            await writer.write("ns=2;s=power", 6.0)
        await server.configure_access({**updated, "users": [updated["users"][0]], "trusted": []}, server_credentials)
        with pytest.raises(ua.UaStatusCodeError, match="BadUserAccessDenied"):
            await writer.read("ns=2;s=power")
        # Trust removal affects new connections; the active secure session remains usable.
        assert (await reader.read("ns=2;s=power"))["value"] == 5.0
        fresh = OpcUaClient(server.endpoint_url, features={"security": client_config}, credentials=client_credentials)
        try:
            with pytest.raises(Exception, match="BadCertificateUntrusted"):
                await fresh.start()
        finally:
            await fresh.stop()
        assert server._core._server is transport and writer._core._client is connection
    finally:
        await unknown.stop()
        await writer.stop()
        await reader.stop()
        await server.stop()

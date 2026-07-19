"""Functional-constraint mapping regression tests."""

from unittest.mock import patch

from pyiec61850 import pyiec61850 as iec61850

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.proto.iec61850.core.connection import (
    Iec61850AssociationParameters,
    Iec61850Connection,
    Iec61850Timeouts,
)


def test_writable_functional_constraints_use_native_values():
    connection = Iec61850Connection.__new__(Iec61850Connection)

    assert connection.get_fc_value("SP") == iec61850.IEC61850_FC_SP
    assert connection.get_fc_value("SE") == iec61850.IEC61850_FC_SE
    assert connection.get_fc_value("SV") == iec61850.IEC61850_FC_SV
    assert connection.get_fc_value("CF") == iec61850.IEC61850_FC_CF


def test_connect_applies_both_connect_and_request_timeouts():
    native_connection = object()
    timeouts = Iec61850Timeouts(connect_ms=1200, request_ms=2300)
    connection = Iec61850Connection("127.0.0.1", 102, model_name="IED", timeouts=timeouts)

    with (
        patch.object(iec61850, "IedConnection_create", return_value=native_connection),
        patch.object(iec61850, "IedConnection_setConnectTimeout") as set_connect_timeout,
        patch.object(iec61850, "IedConnection_setRequestTimeout") as set_request_timeout,
        patch.object(connection, "_apply_association_parameters"),
        patch.object(iec61850, "IedConnection_connect", return_value=iec61850.IED_ERROR_OK),
        patch.object(connection, "_infer_model_name") as infer_model_name,
    ):
        assert connection.connect(auto_discover=False) is True

    set_connect_timeout.assert_called_once_with(native_connection, 1200)
    set_request_timeout.assert_called_once_with(native_connection, 2300)
    infer_model_name.assert_called_once_with()


def test_connect_caches_remote_domains_even_with_configured_model_name():
    """A configured IED name must not suppress remote MMS domain discovery."""
    native_connection = object()
    connection = Iec61850Connection("127.0.0.1", 102, model_name="ZCA-110")

    with (
        patch.object(iec61850, "IedConnection_create", return_value=native_connection),
        patch.object(iec61850, "IedConnection_setConnectTimeout"),
        patch.object(iec61850, "IedConnection_setRequestTimeout"),
        patch.object(connection, "_apply_association_parameters"),
        patch.object(iec61850, "IedConnection_connect", return_value=iec61850.IED_ERROR_OK),
        patch.object(connection, "browse_logical_devices", return_value=["LC001PCS06"]),
    ):
        assert connection.connect(auto_discover=False) is True

    assert connection._discovered_lds == ["LC001PCS06"]
    assert connection.build_dataset_ref("LC001PCS06/LLN0$dsPcs6Data1") == "LC001PCS06/LLN0$dsPcs6Data1"


def test_tls_connection_uses_native_creator_and_synchronous_connect():
    native_connection = object()
    tls_configuration = type("TlsConfiguration", (), {"native": object()})()
    connection = Iec61850Connection(
        "127.0.0.1",
        102,
        tls_configuration=tls_configuration,
        timeouts=Iec61850Timeouts(connect_ms=100, request_ms=100),
    )

    with (
        patch.object(
            iec61850,
            "IedConnection_createWithTlsSupport",
            return_value=native_connection,
        ) as create_with_tls,
        patch.object(iec61850, "IedConnection_setConnectTimeout"),
        patch.object(iec61850, "IedConnection_setRequestTimeout"),
        patch.object(connection, "_apply_association_parameters"),
        patch.object(iec61850, "IedConnection_connect", return_value=iec61850.IED_ERROR_OK) as connect_sync,
        patch.object(connection, "_infer_model_name"),
    ):
        assert connection.connect(auto_discover=False) is True

    create_with_tls.assert_called_once_with(tls_configuration.native)
    connect_sync.assert_called_once_with(native_connection, "127.0.0.1", 102)


def test_connection_applies_iso_addresses_and_password_authentication():
    association = Iec61850AssociationParameters(
        remote_ap_title="1,1,1,999,1",
        remote_ae_qualifier=12,
        local_ap_title="1,1,1,999,1",
        local_ae_qualifier=12,
        authentication_enabled=True,
        authentication_password="ied-secret",
    )
    connection = Iec61850Connection("127.0.0.1", 102, association_parameters=association)
    connection._connection = object()
    mms_connection = object()
    iso_parameters = object()
    selectors = [object() for _ in range(6)]

    with (
        patch.object(iec61850, "IedConnection_getMmsConnection", return_value=mms_connection),
        patch.object(iec61850, "MmsConnection_getIsoConnectionParameters", return_value=iso_parameters),
        patch.object(connection, "_selector", side_effect=selectors),
        patch.object(iec61850, "IsoConnectionParameters_setRemoteApTitle") as set_remote_ap,
        patch.object(iec61850, "IsoConnectionParameters_setLocalApTitle") as set_local_ap,
        patch.object(iec61850, "IsoConnectionParameters_setRemoteAddresses") as set_remote_addresses,
        patch.object(iec61850, "IsoConnectionParameters_setLocalAddresses") as set_local_addresses,
        patch.object(iec61850, "AcseAuthenticationParameter_create", return_value="auth") as create_auth,
        patch.object(iec61850, "AcseAuthenticationParameter_setAuthMechanism") as set_mechanism,
        patch.object(iec61850, "AcseAuthenticationParameter_setPassword") as set_password,
        patch.object(iec61850, "IsoConnectionParameters_setAcseAuthenticationParameter") as set_auth,
    ):
        connection._apply_association_parameters(iec61850)

    set_remote_ap.assert_called_once_with(iso_parameters, "1.1.1.999.1", 12)
    set_local_ap.assert_called_once_with(iso_parameters, "1.1.1.999.1", 12)
    set_remote_addresses.assert_called_once_with(iso_parameters, *selectors[:3])
    set_local_addresses.assert_called_once_with(iso_parameters, *selectors[3:])
    create_auth.assert_called_once_with()
    set_mechanism.assert_called_once_with("auth", iec61850.ACSE_AUTH_PASSWORD)
    set_password.assert_called_once_with("auth", "ied-secret")
    set_auth.assert_called_once_with(iso_parameters, "auth")


def test_handler_passes_persisted_authentication_to_runtime_client():
    handler = IEC61850ClientHandler()
    runtime = {
        "connect_timeout_ms": 3000,
        "command_timeout_ms": 3000,
        "model_discovery_timeout_s": 600,
        "mms_capture_enabled": False,
        "authentication_enabled": True,
        "authentication_password": "persisted-secret",
        "remote_ap_title": "1,1,1,999,1",
        "remote_ae_qualifier": 12,
        "remote_p_selector": "00 00 00 01",
        "remote_s_selector": "00 01",
        "remote_t_selector": "00 01",
        "local_ap_title": "1,1,1,999,1",
        "local_ae_qualifier": 12,
        "local_p_selector": "00 00 00 01",
        "local_s_selector": "00 01",
        "local_t_selector": "00 01",
    }

    with (
        patch("src.proto.iec61850.tls.create_client_tls_configuration", return_value=None),
        patch("src.proto.iec61850.iec61850_client.IEC61850Client") as client_class,
    ):
        handler.initialize(
            {
                "ip": "127.0.0.1",
                "port": 102,
                "model_name": "IED",
                "runtime": runtime,
                "security": {"tls_enabled": False},
            }
        )

    association = client_class.call_args.kwargs["association_parameters"]
    assert association.authentication_enabled is True
    assert association.authentication_password == "persisted-secret"
    assert association.remote_p_selector == "00 00 00 01"

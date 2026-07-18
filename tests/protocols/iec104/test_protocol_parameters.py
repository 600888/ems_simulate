from src.proto.iec104.iec104client import IEC104Client
from src.proto.iec104.iec104server import IEC104Server


def _parameter_values(parameters):
    return {
        "k": parameters.send_window_size,
        "w": parameters.receive_window_size,
        "t0": parameters.connection_timeout,
        "t1": parameters.message_timeout,
        "t2": parameters.confirm_interval,
        "t3": parameters.keep_alive_interval,
    }


def test_client_applies_link_parameters_and_originator_address():
    client = IEC104Client(
        send_window_size=16,
        receive_window_size=10,
        connection_timeout=4,
        message_timeout=5,
        confirm_interval=2,
        keep_alive_interval=21,
        originator_address=7,
    )

    assert client.client.originator_address == 7
    assert client.connection.originator_address == 7
    assert _parameter_values(client.connection.protocol_parameters) == {
        "k": 16,
        "w": 10,
        "t0": 4,
        "t1": 5,
        "t2": 2,
        "t3": 21,
    }


def test_server_applies_all_link_parameters():
    server = IEC104Server(
        ip="127.0.0.1",
        port=0,
        send_window_size=18,
        receive_window_size=11,
        connection_timeout=6,
        message_timeout=7,
        confirm_interval=3,
        keep_alive_interval=22,
    )

    assert _parameter_values(server.server.protocol_parameters) == {
        "k": 18,
        "w": 11,
        "t0": 6,
        "t1": 7,
        "t2": 3,
        "t3": 22,
    }

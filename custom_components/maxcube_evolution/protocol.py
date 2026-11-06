"""MAX! Cube parameter telegrams, derived from Dmitry Kazakov's GPLv2+ Ada source
(used under GPL-3.0-or-later, see LICENSE and NOTICE).

No network I/O in encoding functions. Configuration is only writable when a
complete C response for the exact device was received in the current session.
"""
from __future__ import annotations
import base64
from dataclasses import dataclass, replace
import socket
import time


@dataclass(frozen=True)
class ThermostatConfig:
    address: int
    room_id: int
    comfort_temperature: float
    eco_temperature: float
    max_temperature: float
    min_temperature: float
    temperature_offset: float
    window_open_temperature: float
    window_open_duration: int  # minutes
    boost_duration: int  # minutes
    boost_valve_position: int  # percent
    decalc_day: int  # 0=Saturday, 1=Sunday, 2=Monday ... 6=Friday (as in Kazakov's Encode/Decode)
    decalc_hour: int
    max_valve_position: int  # percent
    valve_offset: int  # percent


def decode_c_line(line: str, expected_address: int) -> ThermostatConfig | None:
    """Decode complete C-response for a radiator thermostat (including schedule).

    C:HEX_RF_ADDRESS,base64(1 byte length, 3 byte address, 1 type,
    1 room, 2 reserved, 10 serial, 7 thermostat bytes, 4 valve bytes, schedule).
    """
    if not line.startswith('C:') or ',' not in line:
        return None
    addr, encoded = line[2:].split(',', 1)
    if int(addr, 16) != expected_address:
        return None
    raw = base64.b64decode(encoded.strip(), validate=True)
    if len(raw) < 1 or raw[0] != len(raw) - 1 or len(raw) < 1+3+1+1+2+10+11:
        raise ValueError('Incomplete or malformed MAX! C response')
    if int.from_bytes(raw[1:4], 'big') != expected_address:
        raise ValueError('RF address mismatch in C response')
    if raw[4] not in (1, 2):
        return None
    room_id = raw[5]
    pos = 1 + 3 + 1 + 1 + 2 + 10
    vals = raw[pos:pos+11]
    # 7 parameter bytes followed by boost, decalcification, max valve, valve offset.
    boost = vals[7]
    return ThermostatConfig(
        address=expected_address, room_id=room_id,
        comfort_temperature=vals[0]/2, eco_temperature=vals[1]/2,
        max_temperature=vals[2]/2, min_temperature=vals[3]/2,
        temperature_offset=vals[4]/2-3.5,
        window_open_temperature=vals[5]/2,
        window_open_duration=vals[6]*5,
        boost_duration=60 if boost >> 5 == 7 else (boost >> 5)*5,
        boost_valve_position=(boost & 31)*5,
        decalc_day=vals[8] >> 5, decalc_hour=vals[8] & 31,
        max_valve_position=round(vals[9]*100/255),
        valve_offset=round(vals[10]*100/255),
    )


def _half(value: float) -> int:
    v = round(value*2)
    if not 0 <= v <= 255 or abs(v/2-value) > 0.001:
        raise ValueError('Temperature must be a representable half degree')
    return v


def encode_config(config: ThermostatConfig, family: str) -> bytes:
    if not 0 <= config.address <= 0xffffff or not 0 <= config.room_id <= 255:
        raise ValueError('Invalid device address or room')
    common = bytes.fromhex('000412000000' if family == 'valve' else '000011000000')
    prefix = common + config.address.to_bytes(3,'big') + bytes([config.room_id])
    if family == 'valve':
        if config.boost_duration not in (0,5,10,15,20,25,30,60):
            raise ValueError('Unsupported boost duration')
        if not 0 <= config.boost_valve_position <= 100 or config.boost_valve_position % 5:
            raise ValueError('Boost valve must be 0..100 in steps of 5')
        if not 0 <= config.decalc_day <= 6 or not 0 <= config.decalc_hour <= 23:
            raise ValueError('Invalid decalcification time')
        if not 0 <= config.max_valve_position <= 100 or not 0 <= config.valve_offset <= 100:
            raise ValueError('Invalid valve percentage')
        duration_code = 7 if config.boost_duration == 60 else config.boost_duration//5
        data = bytes([duration_code*32+config.boost_valve_position//5,
                      config.decalc_day*32+config.decalc_hour,
                      round(config.max_valve_position*255/100),
                      round(config.valve_offset*255/100)])
    elif family == 'temperature':
        if not -3.5 <= config.temperature_offset <= 3.5 or config.window_open_duration % 5:
            raise ValueError('Invalid temperature offset or window duration')
        if not 0 <= config.window_open_duration <= 1275:
            raise ValueError('Invalid window duration')
        if config.min_temperature > config.max_temperature:
            raise ValueError('Minimum temperature exceeds maximum')
        data = bytes([_half(config.comfort_temperature), _half(config.eco_temperature),
                      _half(config.max_temperature), _half(config.min_temperature),
                      _half(config.temperature_offset+3.5),
                      _half(config.window_open_temperature),
                      config.window_open_duration//5])
    else:
        raise ValueError('Unknown command family')
    return b's:' + base64.b64encode(prefix+data) + b'\r\n'


def exchange(host: str, port: int, request: bytes, address: int | None = None) -> list[str]:
    """Single short-lived connection, collect responses; never pretend an ACK is a readback."""
    lines = []
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.settimeout(1.5)
        # Cube emits an initial H/M/C/L burst; drain briefly before command.
        deadline = time.monotonic()+2.0
        buffer=b''
        while time.monotonic()<deadline:
            try:
                chunk=sock.recv(8192)
                if not chunk: break
                buffer+=chunk
                if len(buffer)>262144: raise ValueError('Cube response too large')
            except socket.timeout:
                break
        sock.sendall(request)
        buffer=b''
        deadline=time.monotonic()+4.0
        while time.monotonic()<deadline:
            try:
                chunk=sock.recv(8192)
                if not chunk: break
                buffer+=chunk
                if len(buffer)>262144: raise ValueError('Cube response too large')
                while b'\n' in buffer:
                    raw,buffer=buffer.split(b'\n',1)
                    line=raw.decode('ascii',errors='replace').strip()
                    lines.append(line)
                    if address is not None and line.startswith(f'C:{address:06x},'):
                        return lines
            except socket.timeout:
                break
    return lines


def fetch_config(host: str, port: int, address: int) -> ThermostatConfig:
    lines = exchange(host,port,f'c:{address:06x}\r\n'.encode('ascii'),address)
    for line in lines:
        if line.startswith('C:'):
            parsed=decode_c_line(line,address)
            if parsed is not None: return parsed
    raise RuntimeError('No complete thermostat configuration returned by Cube')


def send_config(host: str, port: int, config: ThermostatConfig, family: str) -> tuple[int, bool, int] | None:
    lines=exchange(host,port,encode_config(config,family))
    # S: is status, not a positive confirmation of changed device settings.
    status = next((decoded for line in reversed(lines) if (decoded := decode_status_line(line)) is not None), None)
    return status


def encode_boost(address: int, room_id: int) -> bytes:
    """Boost command from Kazakov's Ada Set_Thermostat_Boost_Unchecked.

    Unlike temperature/mode updates, BOOST has no temperature byte.
    """
    if not 0 <= address <= 0xFFFFFF or not 0 <= room_id <= 255:
        raise ValueError("Invalid RF address or room ID")
    packet = bytes.fromhex("000440000000") + address.to_bytes(3, "big") + bytes((room_id, 0xC0))
    return b"s:" + base64.b64encode(packet) + b"\r\n"


def send_boost(host: str, port: int, address: int, room_id: int) -> tuple[int, bool, int] | None:
    """Send BOOST; transport success is not RF delivery confirmation."""
    lines = exchange(host, port, encode_boost(address, room_id))
    return next((decoded for line in reversed(lines) if (decoded := decode_status_line(line)) is not None), None)


def decode_status_line(line: str) -> tuple[int, bool, int] | None:
    """S: duty(hex), error(decimal), free slots(hex), per Ada Get_S."""
    if not line.startswith("S:"):
        return None
    fields = line[2:].strip().split(",")
    if len(fields) < 3:
        return None
    try:
        duty = int(fields[0], 16)
        error = int(fields[1], 10)
        slots = int(fields[2], 16)
    except ValueError:
        return None
    if duty < 0 or slots < 0:
        return None
    return min(duty, 100), error != 0, slots

def read_cube_header(host: str, port: int) -> int:
    """Read H: duty without issuing any RF or configuration command."""
    with socket.create_connection((host, port), timeout=3) as sock:
        sock.settimeout(2)
        data = b""
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and len(data) < 65536:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            data += chunk
            for raw in data.split(b"\n"):
                if raw.startswith(b"H:") and raw.endswith(b"\r"):
                    fields = raw[2:-1].decode("ascii").split(",")
                    if len(fields) >= 6:
                        duty = int(fields[5], 16)
                        if 0 <= duty <= 100:
                            return duty
        raise RuntimeError("Cube H response did not contain a valid duty cycle")

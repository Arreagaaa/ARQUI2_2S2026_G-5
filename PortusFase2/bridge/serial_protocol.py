"""
Modulo de protocolo de comunicacion serial para PORTUS Fase 2.
Maneja tramas delimitadas con numero de secuencia y CRC16-CCITT.
Tambien cuenta con un extractor de compatibilidad hacia los mensajes
de consola de texto plano emitidos por la Fase 1.
"""

def crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


class SerialProtocol:
    FRAME_START = "["
    FRAME_END = "]"
    FIELD_SEP = ":"

    @staticmethod
    def build_frame(seq: int, tipo: str, cmd: str, payload: str = "") -> str:
        """
        Construye una trama en el formato: [SEQ:TIPO:CMD:PAYLOAD:CRC]\n
        """
        tipo = tipo.upper()
        content = f"{seq}:{tipo}:{cmd}:{payload}"
        crc = crc16_ccitt(content.encode("utf-8"))
        crc_hex = f"{crc:04X}"
        return f"[{content}:{crc_hex}]\n"

    @classmethod
    def parse_frame(cls, line: str):
        """
        Parsea una linea recibida.
        Retorna diccionario con:
          valid: bool
          seq: int
          tipo: str ('EVT', 'CMD', 'ACK', 'NAK', 'HB', 'LEGACY')
          cmd: str
          payload: str
          crc: str
          raw: str
        """
        raw = line.strip()
        if not raw:
            return None

        # Verificar si es trama estructurada de Fase 2: [...]
        if raw.startswith(cls.FRAME_START) and raw.endswith(cls.FRAME_END):
            inner = raw[1:-1]
            parts = inner.split(cls.FIELD_SEP)
            if len(parts) >= 5:
                # Si payload contenia separadores, los primeros 3 y el ultimo son fijos
                seq_str = parts[0]
                tipo = parts[1].upper()
                cmd = parts[2]
                crc_recv = parts[-1].upper()
                payload = cls.FIELD_SEP.join(parts[3:-1])

                content_to_check = f"{seq_str}:{tipo}:{cmd}:{payload}"
                computed_crc = f"{crc16_ccitt(content_to_check.encode('utf-8')):04X}"

                try:
                    seq_int = int(seq_str)
                except ValueError:
                    seq_int = -1

                is_valid = (crc_recv == computed_crc)
                return {
                    "valid": is_valid,
                    "seq": seq_int,
                    "tipo": tipo,
                    "cmd": cmd,
                    "payload": payload,
                    "crc": crc_recv,
                    "raw": raw,
                    "is_legacy": False
                }

        # Manejo de compatibilidad con impresiones de consola de Fase 1
        return cls._parse_legacy(raw)

    @classmethod
    def _parse_legacy(cls, raw: str):
        """
        Interpreta salidas directas de la Fase 1 si el microcontrolador
        aun corre el sketch sin extension estructurada.
        """
        # Eventos de Garita
        if "[GARITA] RECHAZO:" in raw:
            motivo = raw.split("[GARITA] RECHAZO:")[-1].strip()
            return {
                "valid": True,
                "seq": 0,
                "tipo": "EVT",
                "cmd": "GaritaValidacion",
                "payload": f"resultado=RECHAZADO;causa={motivo}",
                "crc": "0000",
                "raw": raw,
                "is_legacy": True
            }
        if "Tarjeta leida, UID:" in raw:
            uid = raw.split("Tarjeta leida, UID:")[-1].strip().replace(" ", "")
            return {
                "valid": True,
                "seq": 0,
                "tipo": "EVT",
                "cmd": "GaritaIdentificacion",
                "payload": f"uid={uid}",
                "crc": "0000",
                "raw": raw,
                "is_legacy": True
            }

        # Eventos de Pesaje
        if "Peso leido:" in raw:
            # Ejemplo: Peso leido: 25.50 kg (declarado: 25.00 kg, tolerancia: +-5.00 kg)
            return {
                "valid": True,
                "seq": 0,
                "tipo": "EVT",
                "cmd": "PesajeLectura",
                "payload": f"detalle={raw}",
                "crc": "0000",
                "raw": raw,
                "is_legacy": True
            }

        # Eventos de Grua
        if "[GRUA] estado ->" in raw:
            est = raw.split("[GRUA] estado ->")[-1].strip()
            return {
                "valid": True,
                "seq": 0,
                "tipo": "EVT",
                "cmd": "GruaEstado",
                "payload": f"estado={est}",
                "crc": "0000",
                "raw": raw,
                "is_legacy": True
            }

        # Paro de emergencia
        if "PARO DE EMERGENCIA ACTIVO" in raw or "crane_emergencyHalt" in raw:
            return {
                "valid": True,
                "seq": 0,
                "tipo": "EVT",
                "cmd": "ParoEmergencia",
                "payload": "activo=1",
                "crc": "0000",
                "raw": raw,
                "is_legacy": True
            }

        # Mensaje no reconocido
        return {
            "valid": False,
            "seq": -1,
            "tipo": "RAW",
            "cmd": "INFO",
            "payload": raw,
            "crc": "0000",
            "raw": raw,
            "is_legacy": True
        }


if __name__ == "__main__":
    frame = SerialProtocol.build_frame(1, "CMD", "AbrirTalanquera", "motivo=operador")
    print("Ejemplo de trama generada:", frame.strip())
    parsed = SerialProtocol.parse_frame(frame)
    print("Trama parseada:", parsed)
    assert parsed["valid"] is True
    assert parsed["cmd"] == "AbrirTalanquera"
    print("Test unitario de protocolo serial completado con exito.")

"""Read-only adapter for the console actually installed on the Fase 1 Mega.

ESTADO is delimited by its count and final cause. Never reconcile a partial
response: missing lines must not make a vehicle disappear from the dashboard.
"""
import re


class LegacyTelemetry:
    def __init__(self):
        self.snapshot = None

    def feed(self, line):
        line = line.strip()
        if line.startswith("@PORTUS "):
            parts = line[8:].split(";")
            values = dict(part.split("=", 1) for part in parts[1:] if "=" in part)
            return parts[0], values
        match = re.fullmatch(r"Turnos activos: (\d+)", line)
        if match:
            self.snapshot = {"cantidad": int(match[1]), "turnos": [], "paro": False}
            return ("SnapshotInicio", {})
        match = re.fullmatch(r"Turno (\d+) \| Camion (\S+) \| Estacion (\d+) \| Retenido: (SI|NO) \| PesajeInicial: ([-\d.]+) \| PesajeFinal: ([-\d.]+)", line)
        if match and self.snapshot is not None:
            self.snapshot["turnos"].append(dict(zip(
                ("turno_local", "placa", "estacion", "retenido", "entrada_kg", "salida_kg"), match.groups())))
            return ("SnapshotParte", {})
        if "PARO DE EMERGENCIA ACTIVO" in line:
            if self.snapshot is not None:
                self.snapshot["paro"] = True
            return ("ParoEmergencia", {"activo": True})
        if line.startswith("Ultima causa registrada:"):
            snap, self.snapshot = self.snapshot, None
            if snap is not None and len(snap["turnos"]) == snap["cantidad"]:
                snap["causa"] = line.split(":", 1)[1].strip()
                return ("SnapshotFase1", snap)
            return ("SnapshotIncompleto", {})
        patterns = [
            (r"Peso en vivo: ([-\d.]+) kg", "PesajeEnVivo", ("peso",)),
            (r"Peso leido: ([-\d.]+) kg.*declarado: ([-\d.]+) kg.*", "PesajeLectura", ("peso", "declarado_kg")),
            (r"\[SALIDA\] cambio de estado -> (\d+)", "SalidaEstado", ("estado",)),
            (r"\[GRUA\] estado -> (\d+)", "GruaEstado", ("estado",)),
            (r"Posicion (\d+): estado=(\w+) niveles=(\d+)", "PatioEstado", ("posicion", "estado", "niveles")),
            (r"Referenciada: (SI|NO)", "GruaReferencia", ("referenciada",)),
            (r"Libre \(idle\): (SI|NO)", "GruaLibre", ("libre",)),
        ]
        for pattern, kind, keys in patterns:
            match = re.fullmatch(pattern, line)
            if match:
                return kind, dict(zip(keys, match.groups()))
        if "Reanudado automaticamente por boton de paro" in line or line == "Rearme completado.":
            return "ParoEmergencia", {"activo": False}
        return None

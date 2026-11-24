"""Une los 7 archivos de una sesión y corre el análisis por músculo."""
from __future__ import annotations

from .lectura import Registro, identicos
from .procesamiento import MOMENTOS, Parametros, acondicionar, analizar_musculo

CLAVES = {
    ("Llegada", "reposo"): "1_reposo", ("Llegada", "contracciones"): "1_contracciones",
    ("Ejercicio", "ejercicio"): "ejercicio",
    ("Post-ejercicio", "reposo"): "2_reposo", ("Post-ejercicio", "contracciones"): "2_contracciones",
    ("Post-enfriamiento", "reposo"): "3_reposo", ("Post-enfriamiento", "contracciones"): "3_contracciones",
}


def analizar_sesion(registros: dict, ganancias: dict, p: Parametros = Parametros()):
    """registros: {'1_reposo': Registro, ...}; ganancias: {'TFL': 207.87, ...}.
    Devuelve {musculo: ResultadoMusculo} y una lista de avisos generales."""
    avisos = []
    nombres = list(registros)
    for i, a in enumerate(nombres):
        for b in nombres[i + 1:]:
            if identicos(registros[a], registros[b]):
                avisos.append(f"«{a}» y «{b}» son idénticos: revisen que no hayan copiado el mismo archivo.")
    musculos = sorted({m for r in registros.values() for m in r.canales}, key=lambda m: (m != "TFL", m))
    res = {}
    for mus in musculos:
        if mus not in ganancias:
            continue

        def prep(clave):
            r: Registro = registros.get(clave)
            if r is None or mus not in r.canales:
                return None
            x = acondicionar(r.canales[mus], r.fs, ganancias[mus], p)
            if len(r.marcas):                              # con marcas: versión causal para la latencia
                return (x, r.fs, r.marcas, acondicionar(r.canales[mus], r.fs, ganancias[mus], p, causal=True))
            return (x, r.fs, r.marcas)

        rep = [prep(CLAVES[(m, "reposo")]) for m in MOMENTOS]
        con = [prep(CLAVES[(m, "contracciones")]) for m in MOMENTOS]
        ej = prep("ejercicio")
        if all(c is None for c in con):
            continue
        R = analizar_musculo(mus, rep, con, ej, p)
        avisos += R.avisos
        res[mus] = R
    return res, avisos

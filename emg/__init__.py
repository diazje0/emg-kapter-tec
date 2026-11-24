"""Procesamiento de sEMG para el Reto Kapter-TEC (BI2005B)."""
from .lectura import Registro, leer_registro, identicos
from .procesamiento import MOMENTOS, Parametros, acondicionar, analizar_musculo

__all__ = ["Registro", "leer_registro", "identicos", "MOMENTOS", "Parametros", "acondicionar", "analizar_musculo"]

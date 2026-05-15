
import os
import random
import string
import shutil
import functools
import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId

# PATRÓN SINGLETON — Conexión única a MongoDB
class ConexionBaseDatos:
    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            
            MONGO_URI = os.getenv(
                "MONGO_URI",
                "mongodb+srv://erickslonga24_db_user:ltg9xCcFwERsCsJL"
                "@todolistcluster.hrygcsc.mongodb.net/?appName=TodoListCluster"
            )
            cls._instancia.cliente        = MongoClient(MONGO_URI)
            cls._instancia.base           = cls._instancia.cliente["incidencias_db"]
            cls._instancia.incidencias    = cls._instancia.base["incidencias"]
            cls._instancia.notificaciones = cls._instancia.base["notificaciones"]
        return cls._instancia

    def verificar(self):
        self.cliente.admin.command("ping")

bd = ConexionBaseDatos()


# PATRÓN OBSERVER — Sistema de notificaciones

class ObservadorBase:
    def actualizar(self, evento: str, datos: dict):
        raise NotImplementedError

class ObservadorBitacora(ObservadorBase):
    def actualizar(self, evento: str, datos: dict):
        registro = {
            "evento":    evento,
            "datos":     datos,
            "timestamp": datetime.now().isoformat(),
        }
        bd.notificaciones.insert_one(registro)
        print(f"[BITÁCORA] {evento} → {datos.get('codigo_incidencia', '')}")

class ObservadorCorreo(ObservadorBase):
    def actualizar(self, evento: str, datos: dict):
        print(f"[CORREO] Notificando a {datos.get('correo', 'N/A')} — evento: {evento}")

class SistemaNotificaciones:
    def __init__(self):
        self._observadores: List[ObservadorBase] = []

    def suscribir(self, obs: ObservadorBase):
        self._observadores.append(obs)

    def notificar(self, evento: str, datos: dict):
        for obs in self._observadores:
            obs.actualizar(evento, datos)

notificador = SistemaNotificaciones()
notificador.suscribir(ObservadorBitacora())
notificador.suscribir(ObservadorCorreo())


# PATRÓN DECORATOR — Logging de operaciones
def decorador_log(nombre_operacion: str):
    def envolvente(func):
        @functools.wraps(func)          
        async def envoltura_async(*args, **kwargs):
            print(f"[INICIO] {nombre_operacion}")
            try:
                resultado = await func(*args, **kwargs)
                print(f"[OK]    {nombre_operacion}")
                return resultado
            except Exception as error:
                print(f"[ERROR] {nombre_operacion}: {error}")
                raise

        @functools.wraps(func)
        def envoltura_sync(*args, **kwargs):
            print(f"[INICIO] {nombre_operacion}")
            try:
                resultado = func(*args, **kwargs)
                print(f"[OK]    {nombre_operacion}")
                return resultado
            except Exception as error:
                print(f"[ERROR] {nombre_operacion}: {error}")
                raise

        if asyncio.iscoroutinefunction(func):
            return envoltura_async
        return envoltura_sync
    return envolvente


# APLICACIÓN FastAPI
aplicacion = FastAPI(
    title="IncidenciaVial API",
    description="Sistema de registro de incidencias en la vía pública — Lima, Perú",
    version="1.0.2",
)

aplicacion.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración única de la carpeta de medios
CARPETA_MEDIOS = "medios"
os.makedirs(CARPETA_MEDIOS, exist_ok=True)
aplicacion.mount("/medios", StaticFiles(directory=CARPETA_MEDIOS), name="medios")


def serializar(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc

def generar_codigo() -> str:
    sufijo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"INC-{sufijo}"

CATEGORIAS_VALIDAS = {"bache", "alumbrado", "basura", "seguridad", "emergencia"}
ESTADOS_VALIDOS    = {"pendiente", "en_proceso", "resuelto", "rechazado"}

@decorador_log("inicializar_base_de_datos")
def inicializar_bd():
    bd.verificar()
    bd.incidencias.create_index("codigo_incidencia", unique=True)
    bd.incidencias.create_index([("categoria", 1), ("estado", 1)])

try:
    inicializar_bd()
    print("Conectado a MongoDB Atlas y colecciones verificadas.")
except Exception as e:
    print(f"Error de conexión: {e}")

class UbicacionModelo(BaseModel):
    latitud:  float
    longitud: float

class CiudadanoModelo(BaseModel):
    nombres:  str
    correo:   str
    telefono: str = ""

class IncidenciaCrear(BaseModel):
    categoria:   str
    descripcion: str
    direccion:   str
    ubicacion:   UbicacionModelo
    prioridad:   str = "media"
    ciudadano:   CiudadanoModelo

class ActualizarEstado(BaseModel):
    estado:      str
    observacion: Optional[str] = ""


# ENDPOINTS
@aplicacion.get("/", tags=["Root"])
def raiz():
    return {"mensaje": "IncidenciaVial API v1.0.2 — Sistema de reporte ciudadano"}

@aplicacion.post("/api/incidencias/registrar", tags=["Incidencias"])
@decorador_log("registrar_incidencia")
def registrar_incidencia(incidencia: IncidenciaCrear):
    if incidencia.categoria not in CATEGORIAS_VALIDAS:
        raise HTTPException(400, f"Categoría inválida. Opciones: {CATEGORIAS_VALIDAS}")

    codigo = generar_codigo()
    while bd.incidencias.find_one({"codigo_incidencia": codigo}):
        codigo = generar_codigo()

    documento = {
        "codigo_incidencia":   codigo,
        "categoria":           incidencia.categoria,
        "descripcion":         incidencia.descripcion,
        "direccion":           incidencia.direccion,
        "ubicacion":           {"latitud": incidencia.ubicacion.latitud, "longitud": incidencia.ubicacion.longitud},
        "estado":              "pendiente",
        "prioridad":           incidencia.prioridad,
        "ciudadano":           {"nombres": incidencia.ciudadano.nombres, "correo": incidencia.ciudadano.correo, "telefono": incidencia.ciudadano.telefono},
        "fecha_registro":      datetime.now().isoformat(),
        "fecha_actualizacion": None,
        "medios":              [],
        "historial":           [],
    }

    bd.incidencias.insert_one(documento)

    notificador.notificar("INCIDENCIA_REGISTRADA", {
        "codigo_incidencia": codigo,
        "categoria":         incidencia.categoria,
        "correo":            incidencia.ciudadano.correo,
    })

    return {
        "codigo_incidencia": codigo,
        "mensaje":           "Incidencia registrada exitosamente",
        "estado":            "pendiente",
        "fecha_registro":    documento["fecha_registro"],
    }


@aplicacion.post("/api/incidencias/{codigo}/subir-medio", tags=["Incidencias"])
async def subir_medio(codigo: str, archivo: UploadFile = File(...)):
    """Sube un archivo multimedia y lo vincula a una incidencia existente."""
    incidencia = bd.incidencias.find_one({"codigo_incidencia": codigo.upper()})
    if not incidencia:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")

    # Detectar tipo de archivo basado en el content_type
    tipo_archivo = "desconocido"
    if archivo.content_type:
        if archivo.content_type.startswith("image/"):
            tipo_archivo = "imagen"
        elif archivo.content_type.startswith("video/"):
            tipo_archivo = "video"
        elif archivo.content_type.startswith("audio/"):
            tipo_archivo = "audio"

    extension    = archivo.filename.rsplit(".", 1)[-1] if "." in archivo.filename else "bin"
    nombre_arch  = f"{codigo.upper()}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"
    ruta_archivo = os.path.join(CARPETA_MEDIOS, nombre_arch)

    with open(ruta_archivo, "wb") as destino:
        shutil.copyfileobj(archivo.file, destino)

    entrada_medio = {
        "tipo":      tipo_archivo,
        "nombre":    archivo.filename,
        "ruta":      f"/medios/{nombre_arch}",
        "subido_en": datetime.now().isoformat(),
    }

    bd.incidencias.update_one(
        {"codigo_incidencia": codigo.upper()},
        {"$push": {"medios": entrada_medio}}
    )

    notificador.notificar("MEDIO_ADJUNTADO", {
        "codigo_incidencia": codigo,
        "tipo":    tipo_archivo,
        "archivo": nombre_arch,
    })

    return {"mensaje": "Archivo subido correctamente", "medio": entrada_medio}


@aplicacion.get("/api/incidencias/{codigo}", tags=["Incidencias"])
def obtener_incidencia(codigo: str):
    doc = bd.incidencias.find_one({"codigo_incidencia": codigo.upper()})
    if not doc:
        raise HTTPException(404, "Incidencia no encontrada")
    return serializar(doc)

@aplicacion.patch("/api/incidencias/{codigo}/estado", tags=["Incidencias"])
@decorador_log("actualizar_estado")
def actualizar_estado(codigo: str, cuerpo: ActualizarEstado):
    if cuerpo.estado not in ESTADOS_VALIDOS:
        raise HTTPException(400, f"Estado inválido. Opciones: {ESTADOS_VALIDOS}")

    doc = bd.incidencias.find_one({"codigo_incidencia": codigo.upper()})
    if not doc:
        raise HTTPException(404, "Incidencia no encontrada")

    entrada_historial = {
        "estado_anterior": doc["estado"],
        "estado_nuevo":    cuerpo.estado,
        "observacion":     cuerpo.observacion,
        "fecha":           datetime.now().isoformat(),
    }

    bd.incidencias.update_one(
        {"codigo_incidencia": codigo.upper()},
        {
            "$set":  {"estado": cuerpo.estado, "fecha_actualizacion": datetime.now().isoformat()},
            "$push": {"historial": entrada_historial},
        }
    )

    return {"codigo_incidencia": codigo, "estado_nuevo": cuerpo.estado, "mensaje": "Estado actualizado"}

@aplicacion.get("/api/incidencias", tags=["Incidencias"])
def listar_incidencias(
    categoria: Optional[str] = Query(None),
    estado:    Optional[str] = Query(None),
    limite:    int = Query(50, ge=1, le=200),
):
    filtro = {}
    if categoria: filtro["categoria"] = categoria
    if estado:    filtro["estado"]    = estado
    docs = bd.incidencias.find(filtro).sort("fecha_registro", -1).limit(limite)
    return [serializar(d) for d in docs]

@aplicacion.get("/api/estadisticas", tags=["Dashboard"])
def obtener_estadisticas():
    por_categoria = {r["_id"]: r["total"] for r in bd.incidencias.aggregate([
        {"$group": {"_id": "$categoria", "total": {"$sum": 1}}}
    ])}
    por_estado = {r["_id"]: r["total"] for r in bd.incidencias.aggregate([
        {"$group": {"_id": "$estado", "total": {"$sum": 1}}}
    ])}
    return {
        "total":         bd.incidencias.count_documents({}),
        "por_categoria": por_categoria,
        "por_estado":    por_estado,
    }

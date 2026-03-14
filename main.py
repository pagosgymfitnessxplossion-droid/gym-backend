import os
import re
import uuid
import hashlib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client

# ================= CREDENCIALES SUPABASE =================
# Asegúrate de que estas sean las credenciales correctas de tu proyecto
SUPABASE_URL = "https://cxmwymmgsggzilcwotjv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4bXd5bW1nc2dnemlsY3dvdGp2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzExNDAxMDEsImV4cCI6MjA4NjcxNjEwMX0.-3a_zppjlwprHG4qw-PQfdEPPPee2-iKdAlXLaQZeSM"

app = FastAPI()

# Inicializar conexión a Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Conexión a Supabase Inicializada Correctamente")
except Exception as e:
    print(f"❌ Error Crítico conectando a Supabase: {e}")

# Modelo de datos que espera recibir de MacroDroid
class WebhookPayload(BaseModel):
    message: str
    sender: str | None = "Desconocido"

@app.get("/")
def home():
    return {"status": "Backend GYM XPLOSSION - ACTIVO (Modo Redundancia Anti-Duplicados)"}

def limpiar_monto(texto_monto):
    """Limpia el texto extraído y deja solo el formato numérico del dinero"""
    # Elimina todo lo que no sea dígito, coma o punto
    limpio = re.sub(r'[^\d,.]', '', texto_monto).rstrip('.')
    return limpio

@app.post("/webhook")
async def receive_webhook(payload: WebhookPayload):
    """
    Endpoint principal que recibe los datos de MacroDroid.
    Está diseñado para recibir en 'payload.message' una combinación de:
    [sms_message] + [not_title] + [not_text]
    """
    raw_msg = payload.message
    sender = payload.sender
    
    # Limpiamos el mensaje: mayúsculas y quitamos espacios extra/saltos de línea
    text = raw_msg.upper().replace("\n", " ").replace("  ", " ").strip()
    
    # Si el mensaje está prácticamente vacío (ej. MacroDroid envió variables vacías)
    if not text or len(text) < 5:
        print(f"⚠️ Mensaje ignorado por estar vacío. Origen: {sender}")
        return {"status": "ignorado", "reason": "mensaje_vacio"}

    print(f"\n[{sender}] 📩 RECIBIDO: {text}")
    
    ref = "N/A"
    monto = "0.00"

    # ==========================================
    # 1. EXTRACCIÓN DEL MONTO
    # ==========================================
    # Buscar primero con decimales (formato dinero estándar: 1.200,50 o 150.00)
    posibles_montos_decimales = re.findall(r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b', text)
    
    if posibles_montos_decimales:
        monto = limpiar_monto(posibles_montos_decimales[0])
    else:
        # Si no hay decimales, buscar números enteros antecedidos por palabras clave de moneda
        match_entero = re.search(r'(?:BS|USD|VES|\$)\W*(\d+)', text)
        if match_entero:
            monto = match_entero.group(1)

    # ==========================================
    # 2. EXTRACCIÓN DE LA REFERENCIA
    # ==========================================
    # Buscamos todos los números que tengan entre 4 y 12 dígitos
    todos_numeros = re.findall(r'\b\d{4,12}\b', text)
    candidatos_ref = []
    
    monto_limpio_para_comparar = monto.replace('.', '').replace(',', '')

    for num in todos_numeros:
        # Descartar números de teléfono comunes en Venezuela
        if len(num) == 11 and (num.startswith("04") or num.startswith("02")): 
            continue
        if len(num) == 12 and num.startswith("58"): 
            continue
        # Descartar si el número es exactamente igual al monto sin separadores
        if num == monto_limpio_para_comparar: 
            continue
            
        candidatos_ref.append(num)

    # Si encontramos candidatos viables, usualmente la referencia es el último número del mensaje
    if candidatos_ref:
        ref = candidatos_ref[-1]
        
    # BÚSQUEDA FUERTE (Sobrescribe lo anterior): Si la palabra REF o similar está explícita
    match_ref_explicita = re.search(r'(?:REF|REFERENCIA|SEC|NRO|DOCUMENTO)\D*(\d{4,12})', text)
    if match_ref_explicita:
        ref = match_ref_explicita.group(1)
    
    # ==========================================
    # 3. MANEJO DE REFERENCIAS INEXISTENTES (GENERACIÓN DETERMINISTA)
    # ==========================================
    # Si detectamos dinero, pero NO hay referencia en el mensaje...
    if (ref == "N/A" or ref == "") and monto != "0.00":
        # Generamos una referencia basándonos en el contenido del mensaje.
        # ¿Por qué? Si 2 teléfonos reciben la misma notificación sin referencia, 
        # ambos generarán el MISMO hash, creando la MISMA referencia falsa, 
        # y así la base de datos bloqueará el duplicado correctamente.
        texto_base = text[:40] + str(monto) # Usamos los primeros 40 chars + el monto
        hash_texto = hashlib.md5(texto_base.encode('utf-8')).hexdigest()[:6].upper()
        ref = f"AUTO-{hash_texto}"
        print(f"🪄 Referencia no encontrada. Generada por Hash: {ref}")

    # ==========================================
    # 4. GUARDADO EN BASE DE DATOS (CON PROTECCIÓN ANTI-DUPLICADOS)
    # ==========================================
    if monto != "0.00":
        try:
            # Preparamos los datos a guardar. Asumimos Pago Móvil por defecto.
            data_to_insert = {
                "referencia": ref,
                "monto": monto,
                "metodo_pago": "Pago Móvil",
                "servicio": None,      # El recepcionista lo llenará en el Frontend
                "tipo_cliente": None,  # El recepcionista lo llenará en el Frontend
                "nombre_cliente": None,
                "cedula_cliente": None
            }
            
            # Intentamos insertar en Supabase
            # Si el "candado" de referencia única (UNIQUE constraint) está activo en Supabase,
            # y esta referencia ya existe, esta línea lanzará una excepción (error).
            response = supabase.table("pagos").insert(data_to_insert).execute()
            
            print(f"✅ PAGO GUARDADO EXITOSAMENTE | Ref: {ref} | Monto: {monto} Bs")
            return {"status": "success", "msg": "Pago registrado", "ref": ref}
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Detectamos si el error fue causado por el candado de duplicados de la Base de Datos
            if "duplicate key" in error_msg or "unique constraint" in error_msg or "23505" in error_msg:
                print(f"♻️ DUPLICADO BLOQUEADO: La referencia {ref} ya existe. Ignorando este mensaje de {sender}.")
                # Devolvemos un 200 OK a MacroDroid para que no de error en el celular, 
                # pero le decimos que fue ignorado por duplicado.
                return {"status": "ignored", "msg": "Referencia duplicada bloqueada por BD", "ref": ref}
            else:
                # Si es otro tipo de error (ej. se cayó Supabase), lo mostramos y devolvemos 500
                print(f"🔥 ERROR SQL INESPERADO: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error en BD: {str(e)}")
    else:
        print("⚠️ Ignorado: No se detectó ningún monto válido en el mensaje.")
        return {"status": "ignored", "reason": "sin_monto_detectado"}

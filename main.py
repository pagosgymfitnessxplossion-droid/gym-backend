import os
import re
import time
import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client, Client

# === CREDENCIALES SUPABASE ===
SUPABASE_URL = "https://cxmwymmgsggzilcwotjv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4bXd5bW1nc2dnemlsY3dvdGp2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzExNDAxMDEsImV4cCI6MjA4NjcxNjEwMX0.-3a_zppjlwprHG4qw-PQfdEPPPee2-iKdAlXLaQZeSM"

app = FastAPI()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error BD: {e}")

class SMSPayload(BaseModel):
    message: str
    sender: str | None = None

@app.get("/")
def home():
    return {"status": "Backend Notificaciones Activo v4.0"}

def limpiar_monto(texto_monto):
    # Elimina todo menos números, puntos y comas
    return re.sub(r'[^\d,.]', '', texto_monto).rstrip('.')

@app.post("/webhook")
async def receive(payload: SMSPayload):
    # Unimos título y texto y limpiamos
    text = payload.message.upper().replace("\n", " ").replace("  ", " ")
    sender = payload.sender or "App Banco"
    print(f"--- NOTIFICACIÓN RECIBIDA ---\nTexto: {text}")
    
    ref = "N/A"
    monto = "0.00"

    # 1. BUSCAR MONTO (Dinero)
    # Busca patrones como: Bs 100, USD 20, Monto: 500.00
    match_monto = re.search(r'(?:BS|USD|VES|MONTO|ABONO|RECIBISTE|CREDITO|ACREDITADO)\W*([\d.,]+)', text)
    if match_monto:
        monto = limpiar_monto(match_monto.group(1))
    else:
        # Intento secundario: buscar cualquier formato numérico de dinero (Ej: 1.200,00)
        posibles = re.findall(r'\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b', text)
        if posibles:
            monto = limpiar_monto(posibles[0])

    # 2. BUSCAR REFERENCIA
    # Busca números largos que NO sean el monto
    todos_numeros = re.findall(r'\b\d{4,12}\b', text)
    candidatos = []
    
    monto_limpio = monto.replace('.', '').replace(',', '')
    
    for num in todos_numeros:
        # Filtros para ignorar cédulas, teléfonos o el mismo monto
        if len(num) == 11 and (num.startswith("04") or num.startswith("02")): continue
        if len(num) == 12 and num.startswith("58"): continue
        if num == monto_limpio: continue
        candidatos.append(num)

    # Si encontramos candidatos, tomamos el último (usualmente es la ref)
    if candidatos:
        ref = candidatos[-1]

    # Prioridad máxima si dice explícitamente REF o REFERENCIA
    match_ref = re.search(r'(?:REF|REFERENCIA|SEC|NRO|DOCUMENTO)\D*(\d{4,12})', text)
    if match_ref:
        ref = match_ref.group(1)

    # 3. LÓGICA DE SALVAMENTO (Referencia Aleatoria)
    # Si hay dinero pero no hay referencia, INVENTAMOS UNA para no perder el pago
    if monto != "0.00" and ref == "N/A":
        # Genera algo como: AUTO-A1B2
        ref = f"AUTO-{str(uuid.uuid4())[:4].upper()}"
        print(f"⚠️ Referencia no encontrada. Generada automática: {ref}")

    # 4. GUARDAR EN SUPABASE
    if monto != "0.00":
        try:
            data = {
                "referencia": ref,
                "monto": monto,
                "metodo_pago": "Pago Móvil", # Asumimos Pago Móvil por defecto
                "servicio": None,
                "tipo_cliente": None
            }
            supabase.table("pagos").insert(data).execute()
            print(f"✅ REGISTRADO: Ref {ref} - Monto {monto}")
            return {"status": "ok", "ref": ref}
        except Exception as e:
            print(f"❌ Error DB: {e}")
            # Si falla por referencia duplicada (raro), intentamos de nuevo con otra ref
            try:
                ref_fallback = f"ERR-{str(uuid.uuid4())[:6]}"
                data["referencia"] = ref_fallback
                supabase.table("pagos").insert(data).execute()
                return {"status": "ok_fallback", "ref": ref_fallback}
            except:
                return {"status": "error", "detail": str(e)}
    
    return {"status": "ignorado", "reason": "sin monto detectado"}

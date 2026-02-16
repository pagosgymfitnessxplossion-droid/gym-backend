import os
import re
import time
import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client, Client

# ================= CREDENCIALES =================
# 1. TU NUEVA URL
SUPABASE_URL = "https://cxmwymmgsggzilcwotjv.supabase.co"

# 2. TU KEY
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4bXd5bW1nc2dnemlsY3dvdGp2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzExNDAxMDEsImV4cCI6MjA4NjcxNjEwMX0.-3a_zppjlwprHG4qw-PQfdEPPPee2-iKdAlXLaQZeSM"

app = FastAPI()

# Conexión BD
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error iniciando Supabase: {e}")

class SMSPayload(BaseModel):
    message: str
    sender: str | None = None

@app.get("/")
def home():
    return {"status": "Backend GYM FITNESS XPLOSSION - ACTIVO"}

def limpiar_monto(texto_monto):
    # Elimina letras y deja solo números, puntos y comas
    solo_nums = re.sub(r'[^\d,.]', '', texto_monto)
    return solo_nums.rstrip('.')

@app.post("/webhook")
async def receive(payload: SMSPayload):
    text = payload.message.upper().replace("\n", " ").replace("  ", " ")
    print(f"--- NUEVO PAGO GYM ---\nTexto: {text}")
    
    ref = "N/A"
    monto = "0.00"

    # --- 1. DETECCIÓN DE MONTO ---
    match_monto = re.search(r'(?:BS|USD|VES|MONTO|ABONO|RECIBISTE)\W*([\d.,]+)', text)
    if match_monto:
        monto = limpiar_monto(match_monto.group(1))
    else:
        # Buscamos formatos huérfanos tipo 1.200,00
        posibles = re.findall(r'\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b', text)
        if posibles:
            monto = limpiar_monto(posibles[0])

    # --- 2. DETECCIÓN DE REFERENCIA ---
    todos_los_numeros = re.findall(r'\b\d{4,12}\b', text)
    candidatos = []

    for num in todos_los_numeros:
        # Filtros anti-teléfonos y cédulas comunes
        if len(num) == 11 and (num.startswith("04") or num.startswith("02")): continue 
        if len(num) == 12 and num.startswith("58"): continue
        
        # Evitar confundir el monto con la referencia
        monto_limpio = monto.replace('.', '').replace(',', '')
        if num == monto_limpio: continue

        if len(num) < 5: continue
        candidatos.append(num)

    if candidatos:
        ref = candidatos[-1] # Usualmente la referencia está al final
    
    # Búsqueda fuerte de etiqueta "REF"
    match_etiqueta = re.search(r'(?:REF|REFERENCIA|SEC|DOCUMENTO|NRO)\D*(\d{4,12})', text)
    if match_etiqueta:
        ref = match_etiqueta.group(1)

    # Generar referencia automática si es Bancamiga o falla la lectura pero hay dinero
    if ref == "N/A" and monto != "0.00":
        timestamp_corto = str(int(time.time()))[-6:]
        ref = f"AUTO-{timestamp_corto}"

    # --- 3. GUARDAR EN SUPABASE ---
    if ref != "N/A" and monto != "0.00":
        try:
            # Insertamos solo ref y monto. El 'servicio' (Plan) se asigna en el panel web.
            data = {"referencia": ref, "monto": monto}
            supabase.table("pagos").insert(data).execute()
            print(f"✅ Guardado: Ref {ref} - {monto}")
            return {"status": "guardado", "ref": ref}
        except Exception as e:
            print(f"❌ Error DB: {e}")
            return {"status": "error_db", "detalle": str(e)}
            
    return {"status": "ignorado", "razon": "datos insuficientes"}
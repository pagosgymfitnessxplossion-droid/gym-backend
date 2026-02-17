import os
import re
import time
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client

# === TUS CREDENCIALES ===
SUPABASE_URL = "https://cxmwymmgsggzilcwotjv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4bXd5bW1nc2dnemlsY3dvdGp2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzExNDAxMDEsImV4cCI6MjA4NjcxNjEwMX0.-3a_zppjlwprHG4qw-PQfdEPPPee2-iKdAlXLaQZeSM"

app = FastAPI()

# Intentar conexión con Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Conexión Supabase Inicializada")
except Exception as e:
    print(f"❌ Error Crítico conectando a Supabase: {e}")

class SMSPayload(BaseModel):
    message: str
    sender: str | None = None

@app.get("/")
def home():
    return {"status": "Backend V5 - Modo Diagnostico"}

def limpiar_monto(texto_monto):
    # Deja solo números, puntos y comas
    return re.sub(r'[^\d,.]', '', texto_monto).rstrip('.')

@app.post("/webhook")
async def receive(payload: SMSPayload):
    # 1. LOG INICIAL
    raw_msg = payload.message
    print(f"📩 Recibido: {raw_msg}")
    
    text = raw_msg.upper().replace("\n", " ").replace("  ", " ")
    
    ref = "N/A"
    monto = "0.00"

    # 2. ESTRATEGIA AGRESIVA DE MONTO
    # Busca cualquier número con decimales (ej: 100,00 o 50.00)
    # Expresión regular: Digitos + (punto o coma + digitos) opcional
    posibles_montos = re.findall(r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b', text)
    
    if posibles_montos:
        # Tomamos el primero que encuentre
        monto = limpiar_monto(posibles_montos[0])
    else:
        # Si no hay decimales, busca números enteros solos asociados a moneda
        match_entero = re.search(r'(?:BS|USD|\$)\W*(\d+)', text)
        if match_entero:
            monto = match_entero.group(1)

    # 3. ESTRATEGIA DE REFERENCIA
    # Busca números de 4 a 12 dígitos
    todos_numeros = re.findall(r'\b\d{4,12}\b', text)
    candidatos = []
    monto_clean = monto.replace('.', '').replace(',', '')

    for num in todos_numeros:
        # Filtros básicos
        if len(num) == 11 and (num.startswith("04") or num.startswith("02")): continue # Tlf
        if len(num) == 12 and num.startswith("58"): continue # Tlf int
        if num == monto_clean: continue # Es el mismo monto
        candidatos.append(num)

    if candidatos:
        ref = candidatos[-1]
    
    # Si sigue sin referencia, generamos una
    if ref == "N/A" or ref == "":
        ref = f"AUTO-{str(uuid.uuid4())[:5].upper()}"

    # 4. INTENTO DE GUARDADO (CRÍTICO)
    if monto != "0.00":
        try:
            data = {
                "referencia": ref,
                "monto": monto,
                "metodo_pago": "Pago Móvil",
                "servicio": None,
                "tipo_cliente": None
            }
            # Ejecutamos insert
            response = supabase.table("pagos").insert(data).execute()
            
            print(f"💾 Guardado en BD: {response}")
            return {"status": "success", "msg": "Pago Registrado", "data": data}
            
        except Exception as e:
            # ESTE ERROR ES EL QUE NECESITAMOS VER SI FALLA
            print(f"🔥 ERROR SQL: {str(e)}")
            # Devolvemos el error a MacroDroid para que lo veas en el log del tlf
            raise HTTPException(status_code=500, detail=f"Error BD: {str(e)}")
    else:
        print("⚠️ No se detectó monto en el mensaje")
        return {
            "status": "warning", 
            "msg": "No se encontró monto. Revisa el formato.", 
            "texto_recibido": text
        }

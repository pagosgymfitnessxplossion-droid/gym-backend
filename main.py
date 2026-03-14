import os
import re
import uuid
import hashlib
import json
from fastapi import FastAPI, Request, HTTPException
from supabase import create_client, Client

# ================= CREDENCIALES SUPABASE =================
SUPABASE_URL = "https://cxmwymmgsggzilcwotjv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN4bXd5bW1nc2dnemlsY3dvdGp2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzExNDAxMDEsImV4cCI6MjA4NjcxNjEwMX0.-3a_zppjlwprHG4qw-PQfdEPPPee2-iKdAlXLaQZeSM"

app = FastAPI()

try:
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✅ Conexión a Supabase Inicializada")
except Exception as e:
print(f"❌ Error conectando a Supabase: {e}")

@app.get("/")
def home():
return {"status": "Backend GYM - Modo Indestructible Activo (V7)"}

def limpiar_monto(texto_monto):
limpio = re.sub(r'[^\d,.]', '', texto_monto).rstrip('.')
return limpio

@app.post("/webhook")
async def receive_webhook(request: Request):
# 1. Leemos el mensaje en crudo (A prueba de errores)
body_bytes = await request.body()
raw_body = body_bytes.decode('utf-8', errors='ignore')

message_text = raw_body
sender = "App_BDV"

# 2. Intentamos extraer si viene en formato JSON
try:
data = json.loads(raw_body)
if isinstance(data, dict):
message_text = data.get("message", raw_body)
sender = data.get("sender", "App_BDV")
except:
pass # Si falla el JSON, no importa, usamos el texto crudo

if len(message_text) < 5:
return {"status": "ignorado", "reason": "vacio"}

# 3. Limpieza de saltos de línea y mayúsculas
text = message_text.upper().replace("\n", " ").replace("\r", " ").replace(" ", " ")
print(f"\n📩 PROCESANDO: {text}")

ref = "N/A"
monto = "0.00"

# ================= EXTRACCIÓN DEL MONTO =================
posibles_montos_decimales = re.findall(r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b', text)
if posibles_montos_decimales:
monto = limpiar_monto(posibles_montos_decimales[0])
else:
match_entero = re.search(r'(?:BS|USD|VES|\$)\W*(\d+)', text)
if match_entero:
monto = match_entero.group(1)

# ================= EXTRACCIÓN DE REFERENCIA =================
todos_numeros = re.findall(r'\b\d{4,12}\b', text)
candidatos_ref = []
monto_limpio_para_comparar = monto.replace('.', '').replace(',', '')

for num in todos_numeros:
if len(num) == 11 and (num.startswith("04") or num.startswith("02")): continue
if len(num) == 12 and num.startswith("58"): continue
if num == monto_limpio_para_comparar: continue
candidatos_ref.append(num)

if candidatos_ref:
ref = candidatos_ref[-1]

match_ref_explicita = re.search(r'(?:REF|REFERENCIA|SEC|NRO|DOCUMENTO)\D*(\d{4,12})', text)
if match_ref_explicita:
ref = match_ref_explicita.group(1)

# ================= REFERENCIA AUTOMÁTICA =================
if (ref == "N/A" or ref == "") and monto != "0.00":
texto_base = text[:40] + str(monto)
hash_texto = hashlib.md5(texto_base.encode('utf-8')).hexdigest()[:6].upper()
ref = f"AUTO-{hash_texto}"

# ================= GUARDADO EN BASE DE DATOS =================
if monto != "0.00":
try:
data_to_insert = {
"referencia": ref,
"monto": monto,
"metodo_pago": "Pago Móvil",
"servicio": None,
"tipo_cliente": None
}
response = supabase.table("pagos").insert(data_to_insert).execute()
print(f"✅ GUARDADO | Ref: {ref} | Monto: {monto} Bs")
return {"status": "success", "msg": "Pago registrado", "ref": ref}

except Exception as e:
error_msg = str(e).lower()
if "duplicate key" in error_msg or "unique constraint" in error_msg or "23505" in error_msg:
print(f"♻️ DUPLICADO BLOQUEADO: La ref {ref} ya existe.")
return {"status": "ignored", "msg": "Referencia duplicada", "ref": ref}
else:
raise HTTPException(status_code=500, detail=f"Error BD: {str(e)}")
else:
print("⚠️ Ignorado: No hay dinero en el texto.")
return {"status": "ignored", "reason": "sin_dinero"}

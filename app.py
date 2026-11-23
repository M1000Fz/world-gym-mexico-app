from flask import Flask, render_template, request, redirect, flash, session, Response
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import psycopg2
import requests
import csv
import io
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave_secreta_world_gym")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_cpbBGC6hKV8x@ep-twilight-unit-aejcmcmn-pooler.c-2.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "m1000")

# --- CONFIGURACIÓN DE CORREO (API BREVO HTTPS - SIN BLOQUEO SMTP EN RENDER) ---
CORREO_REMITENTE = os.environ.get("CORREO_REMITENTE", "worldgymmexicofz@gmail.com")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

# --- CATÁLOGO DE PRECIOS (MXN) ---
PRECIOS_PLANES = {
    'MENSUAL': 350.00,
    'TRIMESTRAL': 950.00,
    'ANUAL': 3400.00,
    'VIP': 7500.00
}

def obtener_precio_plan(membresia):
    if not membresia:
        return 350.00
    return PRECIOS_PLANES.get(membresia.strip().upper(), 350.00)

def obtener_conexion():
    return psycopg2.connect(DATABASE_URL)

# --- ASEGURAR ESTRUCTURA DE BD EN NEON POSTGRESQL ---
def asegurar_estructura_bd():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS password VARCHAR(255);")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_pagos (
                id_pago SERIAL PRIMARY KEY,
                cliente_id INTEGER REFERENCES clientes(id),
                monto DECIMAL(10, 2) NOT NULL,
                fecha_pago TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metodo_pago VARCHAR(50) DEFAULT 'Efectivo'
            );
        """)
        conexion.commit()
        cursor.close()
        conexion.close()
    except Exception as e:
        print("Aviso al verificar estructura de BD:", e)

asegurar_estructura_bd()

# --- ENVÍO DE CORREO VÍA BREVO API ---
def enviar_correo_brevo(destinatario, asunto, html_content, texto_plano):
    if not BREVO_API_KEY.strip():
        return False, "Falta configurar BREVO_API_KEY en Render"

    payload = {
        "sender": {
            "name": "World Gym México",
            "email": CORREO_REMITENTE
        },
        "to": [
            {"email": destinatario}
        ],
        "subject": asunto,
        "htmlContent": html_content,
        "textContent": texto_plano
    }

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY.strip(),
        "content-type": "application/json"
    }

    try:
        resp = requests.post(BREVO_ENDPOINT, json=payload, headers=headers, timeout=12)
        if resp.status_code in (200, 201, 202):
            return True, "Enviado"
        return False, f"Brevo HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        print("Error enviando correo con Brevo:", e)
        return False, str(e)

# --- FUNCIÓN PARA ENVIAR CORREO DE BIENVENIDA ---
def enviar_correo_bienvenida(destinatario, nombre, apellido, membresia, codigo_acceso):
    precio = obtener_precio_plan(membresia)
    asunto = f"Bienvenido a World Gym México - Tu Código de Acceso ({codigo_acceso})"

    texto_plano = (
        f"¡Hola {nombre} {apellido}!\n\n"
        f"Bienvenido a World Gym México. Tu registro se ha completado con éxito.\n\n"
        f"Datos de tu membresía:\n"
        f"- Plan: {membresia} (${precio:,.2f} MXN)\n"
        f"- Correo registrado: {destinatario}\n"
        f"- Código de acceso único: {codigo_acceso}\n\n"
        f"Para entrar a tu Portal de Socios y ver los días restantes de tu plan:\n"
        f"1. Ingresa al portal y selecciona la pestaña 'Registrarse'.\n"
        f"2. Captura tu correo y tu código de acceso ({codigo_acceso}).\n"
        f"3. Crea tu contraseña personal y listo.\n\n"
        f"¡Nos vemos entrenando!\nWorld Gym México"
    )

    html = f"""
    <html>
      <body style="margin:0; padding:24px; background-color:#09090b; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color:#f4f4f5;">
        <div style="max-width:520px; margin:0 auto; background-color:#131318; border:1px solid #272732; border-top:4px solid #ff003c; border-radius:14px; padding:28px;">
          <h2 style="margin:0 0 6px 0; text-align:center; letter-spacing:2px; text-transform:uppercase; color:#ffffff;">
            🏋️ WORLD <span style="color:#ff003c;">GYM</span> MÉXICO
          </h2>
          <p style="margin:0 0 22px 0; text-align:center; font-size:12px; letter-spacing:1.5px; text-transform:uppercase; color:#a1a1aa;">
            Confirmación de Registro de Socio
          </p>

          <p style="font-size:15px; line-height:1.6; color:#e4e4e7;">
            ¡Hola <strong>{nombre} {apellido}</strong>! Tu inscripción en <strong>World Gym México</strong> ha quedado registrada correctamente.
          </p>

          <div style="background-color:#1c1c24; border:1px solid #272732; border-radius:10px; padding:18px; margin:20px 0;">
            <p style="margin:0 0 8px 0; font-size:13px; color:#a1a1aa;">PLAN CONTRATADO</p>
            <p style="margin:0 0 14px 0; font-size:16px; font-weight:700; color:#ffffff;">{membresia} (${precio:,.2f} MXN)</p>

            <p style="margin:0 0 8px 0; font-size:13px; color:#a1a1aa;">CORREO DE REGISTRO</p>
            <p style="margin:0 0 14px 0; font-size:15px; color:#f4f4f5;">{destinatario}</p>

            <p style="margin:0 0 8px 0; font-size:13px; color:#a1a1aa;">TU CÓDIGO DE ACCESO ÚNICO</p>
            <div style="background-color:#09090b; border:1px dashed #ff003c; border-radius:8px; padding:12px; text-align:center; font-size:22px; font-weight:800; letter-spacing:2px; color:#ff003c;">
              {codigo_acceso}
            </div>
          </div>

          <p style="font-size:14px; line-height:1.6; color:#d4d4d8;">
            <strong>¿Cómo activar tu Portal de Socios?</strong><br>
            1. Entra a la plataforma y abre la pestaña <strong>Registrarse</strong>.<br>
            2. Ingresa tu correo y el código de acceso de arriba.<br>
            3. Crea tu contraseña personal para consultar tu vigencia en cualquier momento.
          </p>

          <hr style="border:none; border-top:1px solid #272732; margin:22px 0;">
          <p style="margin:0; text-align:center; font-size:12px; color:#71717a;">
            World Gym México · Mensaje automático de registro
          </p>
        </div>
      </body>
    </html>
    """

    return enviar_correo_brevo(destinatario, asunto, html, texto_plano)

# --- CONSTRUIR CONTENIDO DE ALERTA DE VENCIMIENTO ---
def crear_contenido_vencimiento(nombre, apellido, membresia, dias_restantes):
    precio = obtener_precio_plan(membresia)

    if dias_restantes <= 0:
        asunto = "Aviso: Tu membresía en World Gym México ha vencido"
        titulo_estado = "⛔ MEMBRESÍA VENCIDA"
        color_estado = "#ff003c"
        detalle_estado = "Tu membresía actual ha expirado. Pasa a recepción para renovarla y retomar tus entrenamientos sin interrupciones."
    else:
        dia_txt = "día" if dias_restantes == 1 else "días"
        asunto = f"Recordatorio: Tu membresía en World Gym México vence en {dias_restantes} {dia_txt}"
        titulo_estado = f"⏳ VENCE EN {dias_restantes} {dia_txt.upper()}"
        color_estado = "#f59e0b"
        detalle_estado = f"Te quedan {dias_restantes} {dia_txt} de vigencia en tu plan. Renueva antes de la fecha límite para evitar interrupciones en tu acceso."

    texto_plano = (
        f"¡Hola {nombre} {apellido}!\n\n"
        f"{titulo_estado}\n"
        f"{detalle_estado}\n\n"
        f"Detalles de renovación:\n"
        f"- Plan actual: {membresia}\n"
        f"- Costo de renovación: ${precio:,.2f} MXN\n\n"
        f"¡Te esperamos en World Gym México!"
    )

    html = f"""
    <html>
      <body style="margin:0; padding:24px; background-color:#09090b; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color:#f4f4f5;">
        <div style="max-width:520px; margin:0 auto; background-color:#131318; border:1px solid #272732; border-top:4px solid {color_estado}; border-radius:14px; padding:28px;">
          <h2 style="margin:0 0 6px 0; text-align:center; letter-spacing:2px; text-transform:uppercase; color:#ffffff;">
            🏋️ WORLD <span style="color:#ff003c;">GYM</span> MÉXICO
          </h2>
          <p style="margin:0 0 22px 0; text-align:center; font-size:12px; letter-spacing:1.5px; text-transform:uppercase; color:#a1a1aa;">
            Recordatorio de Vigencia de Membresía
          </p>

          <p style="font-size:15px; line-height:1.6; color:#e4e4e7;">
            ¡Hola <strong>{nombre} {apellido}</strong>!
          </p>

          <div style="background-color:#1c1c24; border:1px solid #272732; border-radius:10px; padding:18px; margin:18px 0; text-align:center;">
            <div style="font-size:20px; font-weight:800; letter-spacing:1px; color:{color_estado}; margin-bottom:10px;">
              {titulo_estado}
            </div>
            <p style="margin:0; font-size:14px; line-height:1.5; color:#d4d4d8;">
              {detalle_estado}
            </p>
          </div>

          <div style="background-color:#09090b; border:1px solid #272732; border-radius:8px; padding:14px 18px; margin-bottom:18px;">
            <p style="margin:0 0 6px 0; font-size:13px; color:#a1a1aa;">PLAN ACTUAL: <strong style="color:#ffffff;">{membresia}</strong></p>
            <p style="margin:0; font-size:13px; color:#a1a1aa;">RENOVACIÓN: <strong style="color:#34d399;">${precio:,.2f} MXN</strong></p>
          </div>

          <hr style="border:none; border-top:1px solid #272732; margin:20px 0;">
          <p style="margin:0; text-align:center; font-size:12px; color:#71717a;">
            World Gym México · Sistema automático de notificaciones
          </p>
        </div>
      </body>
    </html>
    """

    return asunto, html, texto_plano

# --- PROTECCIÓN DE RUTAS ADMIN ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Acceso denegado. Se requiere credencial.', 'error')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# --- ACCESO UNIFICADO: LOGIN (ADMIN Y CLIENTE) ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        credencial_1 = request.form['usuario_correo'].strip()
        credencial_2 = request.form['password'].strip()
        
        if credencial_1 == ADMIN_USER and credencial_2 == ADMIN_PASS:
            session['admin_logged_in'] = True
            return redirect('/panel_admin')
            
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        consulta = """
            SELECT nombre, apellido, tipo_membresia, password,
            COALESCE(
                (CASE 
                    WHEN UPPER(TRIM(tipo_membresia)) = 'MENSUAL' THEN fecha_registro + interval '1 month'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'TRIMESTRAL' THEN fecha_registro + interval '3 months'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'ANUAL' THEN fecha_registro + interval '1 year'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'VIP' THEN fecha_registro + interval '100 years'
                    ELSE fecha_registro + interval '1 month'
                END)::date - CURRENT_DATE,
                0
            ) AS dias_restantes
            FROM clientes WHERE LOWER(email) = LOWER(%s) AND estatus = 'Activo';
        """
        cursor.execute(consulta, (credencial_1,))
        cliente = cursor.fetchone()
        cursor.close()
        conexion.close()
        
        if cliente:
            password_guardada = cliente[3]
            if not password_guardada:
                flash('Tu cuenta aún no tiene contraseña. Ve a la pestaña "Registrarse" con tu código de acceso para crearla.', 'error')
            elif check_password_hash(password_guardada, credencial_2):
                session['cliente_logged_in'] = True
                session['cliente_datos'] = {
                    'nombre': f"{cliente[0]} {cliente[1]}",
                    'membresia': cliente[2],
                    'dias': cliente[4]
                }
                return redirect('/mi_portal')
            else:
                flash('Contraseña incorrecta. Verifica tus datos.', 'error')
        else:
            flash('Correo no encontrado o cuenta inactiva.', 'error')
            
    return render_template('login.html')

# --- ACTIVACIÓN / REGISTRO DE CONTRASEÑA DEL SOCIO ---
@app.route('/registro', methods=['POST'])
def registro_cliente():
    email = request.form['email'].strip()
    codigo_acceso = request.form['codigo_acceso'].strip().upper()
    nueva_password = request.form['nueva_password'].strip()
    confirmar_password = request.form['confirmar_password'].strip()

    if len(nueva_password) < 4:
        flash('La contraseña debe tener al menos 4 caracteres.', 'error')
        return redirect('/')

    if nueva_password != confirmar_password:
        flash('Las contraseñas no coinciden. Inténtalo de nuevo.', 'error')
        return redirect('/')

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id, password FROM clientes WHERE LOWER(email) = LOWER(%s) AND UPPER(TRIM(codigo_acceso)) = %s AND estatus = 'Activo';",
        (email, codigo_acceso)
    )
    cliente = cursor.fetchone()

    if not cliente:
        cursor.close()
        conexion.close()
        flash('Correo o código de acceso incorrecto. Verifica los datos proporcionados en recepción.', 'error')
        return redirect('/')

    if cliente[1]:
        cursor.close()
        conexion.close()
        flash('Esta cuenta ya fue registrada anteriormente. Inicia sesión con tu correo y contraseña.', 'error')
        return redirect('/')

    password_hash = generate_password_hash(nueva_password, method='pbkdf2:sha256')
    cursor.execute("UPDATE clientes SET password = %s WHERE id = %s;", (password_hash, cliente[0]))
    conexion.commit()
    cursor.close()
    conexion.close()

    flash('¡Cuenta activada con éxito! Ahora puedes iniciar sesión con tu correo y tu nueva contraseña.', 'success')
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión finalizada de manera segura.', 'success')
    return redirect('/')

# --- RUTAS DEL ADMINISTRADOR ---
@app.route('/panel_admin')
@login_required
def index():
    busqueda = request.args.get('q', '')
    filtro_estatus = request.args.get('estatus', 'Activo')

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    
    consulta_clientes = """
    SELECT id, nombre, apellido, email, telefono, COALESCE(TRIM(tipo_membresia), 'Mensual'),
        COALESCE(
            (CASE 
                WHEN UPPER(TRIM(tipo_membresia)) = 'MENSUAL' THEN fecha_registro + interval '1 month'
                WHEN UPPER(TRIM(tipo_membresia)) = 'TRIMESTRAL' THEN fecha_registro + interval '3 months'
                WHEN UPPER(TRIM(tipo_membresia)) = 'ANUAL' THEN fecha_registro + interval '1 year'
                WHEN UPPER(TRIM(tipo_membresia)) = 'VIP' THEN fecha_registro + interval '100 years'
                ELSE fecha_registro + interval '1 month'
            END)::date - CURRENT_DATE,
            0
        ) AS dias_restantes,
        COALESCE(codigo_acceso, 'SIN-CODIGO') AS codigo_acceso
    FROM clientes 
    WHERE estatus = %s AND (nombre ILIKE %s OR apellido ILIKE %s OR email ILIKE %s)
    ORDER BY id ASC;
    """
    cursor.execute(consulta_clientes, (filtro_estatus, f'%{busqueda}%', f'%{busqueda}%', f'%{busqueda}%'))
    clientes = cursor.fetchall()
    
    consulta_stats = """
    WITH vigencias AS (
        SELECT 
            COALESCE(UPPER(TRIM(tipo_membresia)), 'MENSUAL') AS plan_norm,
            COALESCE(
                (CASE 
                    WHEN UPPER(TRIM(tipo_membresia)) = 'MENSUAL' THEN fecha_registro + interval '1 month'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'TRIMESTRAL' THEN fecha_registro + interval '3 months'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'ANUAL' THEN fecha_registro + interval '1 year'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'VIP' THEN fecha_registro + interval '100 years'
                    ELSE fecha_registro + interval '1 month'
                END)::date - CURRENT_DATE,
                0
            ) AS dias
        FROM clientes
        WHERE estatus = 'Activo'
    )
    SELECT plan_norm, COUNT(*)
    FROM vigencias
    WHERE plan_norm = 'VIP' OR dias > 0
    GROUP BY plan_norm;
    """
    cursor.execute(consulta_stats)
    resultados_stats = cursor.fetchall()
    mapa_planes = {'MENSUAL': 'Mensual', 'TRIMESTRAL': 'Trimestral', 'ANUAL': 'Anual', 'VIP': 'VIP'}
    stats = {'Mensual': 0, 'Trimestral': 0, 'Anual': 0, 'VIP': 0}
    for fila in resultados_stats:
        clave = mapa_planes.get(fila[0])
        if clave:
            stats[clave] = fila[1]

    consulta_kpis = """
    WITH vigencias AS (
        SELECT 
            COALESCE(UPPER(TRIM(tipo_membresia)), 'MENSUAL') AS plan_norm,
            COALESCE(
                (CASE 
                    WHEN UPPER(TRIM(tipo_membresia)) = 'MENSUAL' THEN fecha_registro + interval '1 month'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'TRIMESTRAL' THEN fecha_registro + interval '3 months'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'ANUAL' THEN fecha_registro + interval '1 year'
                    WHEN UPPER(TRIM(tipo_membresia)) = 'VIP' THEN fecha_registro + interval '100 years'
                    ELSE fecha_registro + interval '1 month'
                END)::date - CURRENT_DATE,
                0
            ) AS dias
        FROM clientes
        WHERE estatus = 'Activo'
    )
    SELECT 
        COUNT(*) AS socios_totales,
        COUNT(*) FILTER (WHERE plan_norm = 'VIP' OR dias > 0) AS socios_vigentes,
        COUNT(*) FILTER (WHERE plan_norm = 'VIP') AS total_vip,
        COUNT(*) FILTER (WHERE plan_norm != 'VIP' AND dias > 0 AND dias <= 5) AS por_vencer,
        COUNT(*) FILTER (WHERE plan_norm != 'VIP' AND dias <= 0) AS vencidos
    FROM vigencias;
    """
    cursor.execute(consulta_kpis)
    row_kpi = cursor.fetchone()

    cursor.execute("""
        SELECT
            COALESCE(SUM(monto) FILTER (WHERE DATE_TRUNC('month', fecha_pago) = DATE_TRUNC('month', CURRENT_DATE)), 0) AS ingresos_mes,
            COALESCE(SUM(monto), 0) AS ingresos_totales
        FROM historial_pagos;
    """)
    row_finanzas = cursor.fetchone()

    cursor.execute("""
        SELECT p.id_pago, c.nombre, c.apellido, c.tipo_membresia, p.monto, p.metodo_pago, TO_CHAR(p.fecha_pago, 'DD/MM/YYYY HH24:MI')
        FROM historial_pagos p
        LEFT JOIN clientes c ON p.cliente_id = c.id
        ORDER BY p.fecha_pago DESC
        LIMIT 6;
    """)
    ultimos_pagos = cursor.fetchall()

    kpis = {
        'totales': row_kpi[0] if row_kpi else 0,
        'vigentes': row_kpi[1] if row_kpi else 0,
        'vip': row_kpi[2] if row_kpi else 0,
        'por_vencer': row_kpi[3] if row_kpi else 0,
        'vencidos': row_kpi[4] if row_kpi else 0,
        'ingresos_mes': float(row_finanzas[0]) if row_finanzas else 0.0,
        'ingresos_totales': float(row_finanzas[1]) if row_finanzas else 0.0
    }
            
    cursor.close()
    conexion.close()
    return render_template('nuevo_dashboard.html', clientes=clientes, stats=stats, kpis=kpis, ultimos_pagos=ultimos_pagos)

@app.route('/agregar', methods=['POST'])
@login_required
def agregar():
    nombre = request.form['nombre'].strip()
    apellido = request.form['apellido'].strip()
    email = request.form['email'].strip()
    telefono = request.form['telefono'].strip()
    membresia = request.form['membresia'].strip()
    metodo_pago = request.form.get('metodo_pago', 'Efectivo').strip()
    monto = obtener_precio_plan(membresia)

    codigo_promo = f"GYM-{membresia[:3].upper()}"
    try:
        respuesta = requests.get("https://random-word-api.herokuapp.com/word?length=5", timeout=3)
        if respuesta.status_code == 200:
            palabra = respuesta.json()[0].upper()
            codigo_promo = f"{palabra}-{membresia[:3].upper()}"
    except:
        pass

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id, estatus FROM clientes WHERE LOWER(email) = LOWER(%s);", (email,))
        existente = cursor.fetchone()

        if existente:
            cliente_id, estatus_actual = existente
            if estatus_actual == 'Activo':
                flash('Ese correo electrónico ya pertenece a un socio activo.', 'error')
                return redirect('/panel_admin')
            else:
                cursor.execute("""
                    UPDATE clientes
                    SET nombre = %s, apellido = %s, email = %s, telefono = %s,
                        tipo_membresia = %s, codigo_acceso = %s, estatus = 'Activo',
                        fecha_registro = CURRENT_TIMESTAMP, password = NULL
                    WHERE id = %s;
                """, (nombre, apellido, email, telefono, membresia, codigo_promo, cliente_id))
                nuevo_cliente_id = cliente_id
                accion_msg = "Cliente reactivado"
        else:
            consulta = """
                INSERT INTO clientes (nombre, apellido, email, telefono, tipo_membresia, codigo_acceso, estatus)
                VALUES (%s, %s, %s, %s, %s, %s, 'Activo')
                RETURNING id;
            """
            cursor.execute(consulta, (nombre, apellido, email, telefono, membresia, codigo_promo))
            nuevo_cliente_id = cursor.fetchone()[0]
            accion_msg = "Cliente registrado"

        cursor.execute(
            "INSERT INTO historial_pagos (cliente_id, monto, metodo_pago) VALUES (%s, %s, %s);",
            (nuevo_cliente_id, monto, metodo_pago)
        )
        conexion.commit()

        enviado, detalle = enviar_correo_bienvenida(email, nombre, apellido, membresia, codigo_promo)
        if enviado:
            flash(f'{accion_msg} (+${monto:,.0f} MXN en {metodo_pago}) y correo enviado a {email}. Código: {codigo_promo}', 'success')
        else:
            flash(f'{accion_msg} (+${monto:,.0f} MXN, Código: {codigo_promo}), pero el correo no se envió: {detalle}', 'error')
    except Exception as e:
        conexion.rollback()
        flash(f'Error al registrar cliente: {e}', 'error')
    finally:
        cursor.close()
        conexion.close()
    return redirect('/panel_admin')

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        email = request.form['email']
        telefono = request.form['telefono']
        membresia = request.form['membresia']
        try:
            consulta = "UPDATE clientes SET nombre = %s, apellido = %s, email = %s, telefono = %s, tipo_membresia = %s WHERE id = %s;"
            cursor.execute(consulta, (nombre, apellido, email, telefono, membresia, id))
            conexion.commit()
            flash('Datos actualizados correctamente.', 'success')
        except psycopg2.IntegrityError:
            conexion.rollback()
            flash('El nuevo correo ya pertenece a otra persona.', 'error')
        cursor.close()
        conexion.close()
        return redirect('/panel_admin')
    else:
        cursor.execute("SELECT id, nombre, apellido, email, telefono, tipo_membresia FROM clientes WHERE id = %s;", (id,))
        cliente = cursor.fetchone()
        cursor.close()
        conexion.close()
        return render_template('editar.html', cliente=cliente)

@app.route('/renovar/<int:id>')
@login_required
def renovar_membresia(id):
    metodo_pago = request.args.get('metodo', 'Efectivo')
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT tipo_membresia FROM clientes WHERE id = %s;", (id,))
    fila = cursor.fetchone()
    plan = fila[0] if fila else 'Mensual'
    monto = obtener_precio_plan(plan)

    cursor.execute(
        "UPDATE clientes SET fecha_registro = CURRENT_TIMESTAMP, estatus = 'Activo' WHERE id = %s;",
        (id,)
    )
    cursor.execute(
        "INSERT INTO historial_pagos (cliente_id, monto, metodo_pago) VALUES (%s, %s, %s);",
        (id, monto, metodo_pago)
    )
    conexion.commit()
    cursor.close()
    conexion.close()
    flash(f'Membresía {plan} renovada (+${monto:,.0f} MXN en {metodo_pago}).', 'success')
    return redirect('/panel_admin')

@app.route('/borrar/<int:id>')
@login_required
def borrar(id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("UPDATE clientes SET estatus = 'Inactivo' WHERE id = %s;", (id,))
    conexion.commit()
    cursor.close()
    conexion.close()
    flash('El cliente ha sido dado de baja (Inactivo), pero su historial financiero se conserva intacto.', 'success')
    return redirect('/panel_admin')

@app.route('/exportar')
@login_required
def exportar_csv():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre, apellido, email, telefono, tipo_membresia, estatus FROM clientes ORDER BY id ASC;")
    clientes = cursor.fetchall()
    cursor.close()
    conexion.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Nombre', 'Apellido', 'Email', 'Telefono', 'Plan', 'Estatus'])
    for c in clientes:
        writer.writerow(c)
    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=Reporte_Gym.csv"})

@app.route('/notificar_vencimientos')
@login_required
def notificar_vencimientos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    consulta = """
    SELECT nombre, apellido, email, COALESCE(TRIM(tipo_membresia), 'Mensual'),
        COALESCE(
            (CASE 
                WHEN UPPER(TRIM(tipo_membresia)) = 'MENSUAL' THEN fecha_registro + interval '1 month'
                WHEN UPPER(TRIM(tipo_membresia)) = 'TRIMESTRAL' THEN fecha_registro + interval '3 months'
                WHEN UPPER(TRIM(tipo_membresia)) = 'ANUAL' THEN fecha_registro + interval '1 year'
                WHEN UPPER(TRIM(tipo_membresia)) = 'VIP' THEN fecha_registro + interval '100 years'
                ELSE fecha_registro + interval '1 month'
            END)::date - CURRENT_DATE,
            0
        ) AS dias_restantes
    FROM clientes 
    WHERE COALESCE(
        (CASE 
            WHEN UPPER(TRIM(tipo_membresia)) = 'MENSUAL' THEN fecha_registro + interval '1 month'
            WHEN UPPER(TRIM(tipo_membresia)) = 'TRIMESTRAL' THEN fecha_registro + interval '3 months'
            WHEN UPPER(TRIM(tipo_membresia)) = 'ANUAL' THEN fecha_registro + interval '1 year'
            WHEN UPPER(TRIM(tipo_membresia)) = 'VIP' THEN fecha_registro + interval '100 years'
            ELSE fecha_registro + interval '1 month'
        END)::date - CURRENT_DATE,
        0
    ) <= 5
    AND email IS NOT NULL
    AND TRIM(email) != ''
    AND UPPER(TRIM(tipo_membresia)) != 'VIP'
    AND estatus = 'Activo';
    """
    cursor.execute(consulta)
    socios_en_riesgo = cursor.fetchall()
    cursor.close()
    conexion.close()

    if not socios_en_riesgo:
        flash('Ningún cliente requiere recordatorio por ahora.', 'success')
        return redirect('/panel_admin')

    enviados = 0
    fallidos = 0
    ultimo_error = ""

    for nombre, apellido, email, membresia, dias in socios_en_riesgo:
        asunto, html, texto_plano = crear_contenido_vencimiento(nombre, apellido, membresia, dias)
        ok, detalle = enviar_correo_brevo(email.strip(), asunto, html, texto_plano)
        if ok:
            enviados += 1
        else:
            fallidos += 1
            ultimo_error = detalle

    if fallidos == 0:
        flash(f'Se enviaron {enviados} correos de alerta de vencimiento correctamente.', 'success')
    elif enviados == 0:
        flash(f'No se pudieron enviar las alertas ({fallidos} pendientes): {ultimo_error}', 'error')
    else:
        flash(f'Se enviaron {enviados} correos y fallaron {fallidos}. Último detalle: {ultimo_error}', 'error')

    return redirect('/panel_admin')

# --- RUTAS DEL PORTAL CLIENTE ---
@app.route('/mi_portal')
def mi_portal():
    if 'cliente_logged_in' not in session:
        return redirect('/')
    datos = session.get('cliente_datos')
    return render_template('portal_cliente.html', vista='dashboard', datos=datos)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host="0.0.0.0", port=port)
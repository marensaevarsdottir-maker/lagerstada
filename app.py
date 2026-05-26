import os
import resend
from flask import Flask, render_template, jsonify, request, make_response
from datetime import datetime

app = Flask(__name__)

# ── Email setup ───────────────────────────────────────────────────────────────
resend.api_key = os.environ.get('RESEND_API_KEY', '')
EMAIL_TO = os.environ.get('EMAIL_TO', '')

def send_low_stock_email(item_name):
    if not resend.api_key or not EMAIL_TO:
        return
    try:
        resend.Emails.send({
            "from": "Lagerstöðukerfi <onboarding@resend.dev>",
            "to": EMAIL_TO,
            "subject": f"⚠️ {item_name} er búið í geymslu",
            "html": f"""
            <div style="font-family:sans-serif;max-width:500px;margin:40px auto;padding:24px;border:1px solid #B2D8D8;border-radius:12px;">
              <h2 style="color:#006666;margin-top:0;">📦 Lagerstöðukerfi</h2>
              <p style="font-size:16px;">Lagerstöðukerfið lætur þig vita:</p>
              <div style="background:#FFF5F5;border-left:4px solid #C53030;padding:16px;border-radius:8px;margin:16px 0;">
                <strong style="color:#C53030;font-size:18px;">{item_name}</strong>
                <p style="margin:4px 0 0;color:#555;">er komið í <strong>0</strong> í geymslu</p>
              </div>
              <p style="color:#718096;font-size:14px;">Vinsamlegast athugaðu hvort þörf sé á áfyllingu.</p>
            </div>
            """
        })
    except Exception as e:
        print(f'Email villa: {e}')

# ── Database setup ────────────────────────────────────────────────────────────
# Uses PostgreSQL on Render (DATABASE_URL), SQLite locally

DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    # Render gives 'postgres://' but psycopg2 needs 'postgresql://'
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    def get_db():
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn

    PH = '%s'  # PostgreSQL placeholder

    def init_db():
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id         SERIAL PRIMARY KEY,
                name       TEXT NOT NULL UNIQUE,
                geymsla    INTEGER NOT NULL DEFAULT 0,
                ibuad      INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cur.close()
        conn.close()

else:
    import sqlite3
    DATABASE = os.path.join(os.path.dirname(__file__), 'lagerstada.db')

    def get_db():
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn

    PH = '?'  # SQLite placeholder

    def init_db():
        conn = get_db()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                geymsla     INTEGER NOT NULL DEFAULT 0,
                ibuad       INTEGER NOT NULL DEFAULT 0,
                updated_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()


def row_to_dict(row):
    return dict(row)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    resp = make_response(render_template('index.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/api/items', methods=['GET'])
def get_items():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM items ORDER BY name')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = []
    for row in rows:
        d = row_to_dict(row)
        d['samtals'] = d['geymsla'] + d['ibuad']
        result.append(d)
    return jsonify(result)


@app.route('/api/items', methods=['POST'])
def add_item():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Nafn vantar'}), 400

    geymsla = max(0, int(data.get('geymsla', 0)))
    ibuad   = max(0, int(data.get('ibuad',   0)))
    now     = datetime.now().isoformat(timespec='seconds')

    conn = get_db()
    cur = conn.cursor()
    try:
        if DATABASE_URL:
            cur.execute(
                f'INSERT INTO items (name, geymsla, ibuad, updated_at) VALUES ({PH},{PH},{PH},{PH}) RETURNING *',
                (name, geymsla, ibuad, now)
            )
            row = cur.fetchone()
        else:
            cur.execute(
                f'INSERT INTO items (name, geymsla, ibuad, updated_at) VALUES ({PH},{PH},{PH},{PH})',
                (name, geymsla, ibuad, now)
            )
            cur.execute('SELECT * FROM items WHERE name=?', (name,))
            row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        d = row_to_dict(row)
        d['samtals'] = d['geymsla'] + d['ibuad']
        return jsonify(d), 201
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        if 'unique' in str(e).lower() or 'UNIQUE' in str(e):
            return jsonify({'error': 'Þessi hlutur er þegar til'}), 409
        return jsonify({'error': str(e)}), 500


@app.route('/api/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    data = request.json or {}
    conn = get_db()
    cur = conn.cursor()

    fields, values = [], []

    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            cur.close(); conn.close()
            return jsonify({'error': 'Nafn má ekki vera tómt'}), 400
        fields.append(f'name={PH}'); values.append(name)

    geymsla_goes_zero = False
    if 'geymsla' in data:
        new_geymsla = max(0, int(data['geymsla']))
        # Check if geymsla is going to 0 — fetch old value first
        cur.execute(f'SELECT geymsla, name FROM items WHERE id={PH}', (item_id,))
        old = cur.fetchone()
        if old and old['geymsla'] != 0 and new_geymsla == 0:
            geymsla_goes_zero = old['name']
        fields.append(f'geymsla={PH}'); values.append(new_geymsla)

    if 'ibuad' in data:
        fields.append(f'ibuad={PH}'); values.append(max(0, int(data['ibuad'])))

    if not fields:
        cur.close(); conn.close()
        return jsonify({'error': 'Engar breytingar'}), 400

    fields.append(f'updated_at={PH}')
    values.append(datetime.now().isoformat(timespec='seconds'))
    values.append(item_id)

    cur.execute(f'UPDATE items SET {", ".join(fields)} WHERE id={PH}', values)
    conn.commit()
    cur.execute(f'SELECT * FROM items WHERE id={PH}', (item_id,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if row is None:
        return jsonify({'error': 'Hlutur fannst ekki'}), 404

    d = row_to_dict(row)
    d['samtals'] = d['geymsla'] + d['ibuad']

    # Send email if geymsla just hit 0
    if geymsla_goes_zero:
        send_low_stock_email(geymsla_goes_zero)

    return jsonify(d)


@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'DELETE FROM items WHERE id={PH}', (item_id,))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({'success': True})


# ── Entry point ───────────────────────────────────────────────────────────────

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    print(f'\n  ✅  Lagerstöðukerfi keyrir á porti {port}\n')
    app.run(debug=False, host='0.0.0.0', port=port)

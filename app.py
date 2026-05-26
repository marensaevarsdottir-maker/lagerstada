from flask import Flask, render_template, jsonify, request, make_response
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
DATABASE = os.path.join(os.path.dirname(__file__), 'lagerstada.db')


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


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
    rows = conn.execute(
        'SELECT * FROM items ORDER BY name COLLATE NOCASE'
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
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
    try:
        conn.execute(
            'INSERT INTO items (name, geymsla, ibuad, updated_at) VALUES (?,?,?,?)',
            (name, geymsla, ibuad, now)
        )
        conn.commit()
        row = conn.execute(
            'SELECT * FROM items WHERE name=?', (name,)
        ).fetchone()
        conn.close()
        d = dict(row)
        d['samtals'] = d['geymsla'] + d['ibuad']
        return jsonify(d), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Þessi hlutur er þegar til'}), 409


@app.route('/api/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    data = request.json or {}
    conn = get_db()

    # Build dynamic SET clause
    fields, values = [], []

    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            conn.close()
            return jsonify({'error': 'Nafn má ekki vera tómt'}), 400
        fields.append('name=?');    values.append(name)

    if 'geymsla' in data:
        fields.append('geymsla=?'); values.append(max(0, int(data['geymsla'])))

    if 'ibuad' in data:
        fields.append('ibuad=?');   values.append(max(0, int(data['ibuad'])))

    if not fields:
        conn.close()
        return jsonify({'error': 'Engar breytingar'}), 400

    fields.append('updated_at=?')
    values.append(datetime.now().isoformat(timespec='seconds'))
    values.append(item_id)

    conn.execute(f'UPDATE items SET {", ".join(fields)} WHERE id=?', values)
    conn.commit()
    row = conn.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
    conn.close()

    if row is None:
        return jsonify({'error': 'Hlutur fannst ekki'}), 404

    d = dict(row)
    d['samtals'] = d['geymsla'] + d['ibuad']
    return jsonify(d)


@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    conn = get_db()
    conn.execute('DELETE FROM items WHERE id=?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ── Entry point ───────────────────────────────────────────────────────────────

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    print(f'\n  ✅  Lagerstöðukerfi keyrir á porti {port}\n')
    app.run(debug=False, host='0.0.0.0', port=port)

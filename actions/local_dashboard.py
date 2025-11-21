# local_dashboard.py - COMPLETE VERSION FOR RENDER
import os
from urllib.parse import urlparse
from datetime import datetime, date, time, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import check_password_hash
from functools import wraps
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import traceback

load_dotenv()

# Initialize Flask
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-this-12345')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

# Cloud API URL (your Render deployment)
CLOUD_API_URL = os.getenv('CLOUD_API_URL', 'https://ileco1-report-form.onrender.com')

# Database Connection
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    url = urlparse(DATABASE_URL)
    db_pool = psycopg2.pool.SimpleConnectionPool(
        1, 10,
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port or 5432,
        database=url.path[1:]
    )
else:
    db_pool = psycopg2.pool.SimpleConnectionPool(
        1, 10,
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT", "5432"),
        database=os.getenv("PGDATABASE")
    )

def get_db():
    return db_pool.getconn()

def release_db(conn):
    db_pool.putconn(conn)

# ============================================
# AUTHENTICATION
# ============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        # Simple hardcoded auth for local use
        if username == 'admin' and password == 'admin123':
            session['user_id'] = 1
            session['username'] = username
            session['role'] = 'admin'
            session['full_name'] = 'Administrator'
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'redirect': url_for('dashboard')
                })
            else:
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
        else:
            if request.is_json:
                return jsonify({
                    'success': False,
                    'error': 'Invalid credentials'
                }), 401
            else:
                flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

# ============================================
# DASHBOARD
# ============================================

@app.route('/')
@login_required
def dashboard():
    """Main dashboard"""
    
    # Get filters
    status_filter = request.args.get('status', 'All Status')
    priority_filter = request.args.get('priority', 'All Priorities')
    search_term = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Build query
        query = """
            SELECT report_id, full_name, contact_number, address, 
                   details, priority, status, timestamp, 
                   incident_type_detail, source, latitude, longitude,
                   job_order_id
            FROM power_outage_reports
            WHERE (hidden = FALSE OR hidden IS NULL)
        """
        params = []
        
        # Apply filters
        if status_filter != 'All Status':
            query += " AND status = %s"
            params.append(status_filter)
        
        if priority_filter != 'All Priorities':
            query += " AND priority = %s"
            params.append(priority_filter)
        
        if search_term:
            query += " AND (full_name ILIKE %s OR address ILIKE %s OR contact_number ILIKE %s)"
            search_pattern = f'%{search_term}%'
            params.extend([search_pattern, search_pattern, search_pattern])
        
        if date_from:
            query += " AND DATE(timestamp) >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND DATE(timestamp) <= %s"
            params.append(date_to)
        
        query += " ORDER BY timestamp DESC LIMIT 100"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        # Format complaints
        complaints = []
        for row in rows:
            complaints.append({
                'record_id': row[0],
                'table': 'power_outage_reports',
                'customer_name': row[1],
                'customer_id': row[2],
                'customer_phone': row[2],
                'address': row[3],
                'description': row[4],
                'priority': row[5],
                'status': row[6],
                'time': row[7].strftime('%I:%M %p') if row[7] else 'N/A',
                'issue_type': row[8] or 'Power Outage',
                'source': row[9] or 'Web Form',
                'job_order_id': row[12] or None,
                'full_data': {
                    'timestamp': row[7],
                    'latitude': row[10],
                    'longitude': row[11]
                }
            })
        
        # Calculate statistics
        total_active = len(complaints)
        critical_count = sum(1 for c in complaints if c['priority'] == 'CRITICAL')
        
        today_start = datetime.combine(date.today(), time(0, 0))
        resolved_today = sum(1 for c in complaints 
                            if c['status'] == 'RESOLVED' and 
                            c['full_data']['timestamp'] and 
                            c['full_data']['timestamp'] >= today_start)
        
        cur.close()
        release_db(conn)
        
        print(f"✅ Dashboard loaded: {total_active} complaints")
        
    except Exception as e:
        print(f"❌ Error fetching complaints: {e}")
        traceback.print_exc()
        complaints = []
        total_active = 0
        critical_count = 0
        resolved_today = 0
    
    return render_template(
        'dashboard.html',
        complaints=complaints,
        queue=[],  # Empty queue for now
        current_status=status_filter,
        current_priority=priority_filter,
        current_search=search_term,
        current_date_from=date_from,
        current_date_to=date_to,
        critical_count=critical_count,
        resolved_today=resolved_today,
        current_user=session.get('username'),
        user_full_name=session.get('full_name'),
        user_role=session.get('role'),
        # Analytics
        technical_count=0,
        service_count=0,
        billing_count=0,
        power_outage_count=total_active
    )

# ============================================
# API ENDPOINTS
# ============================================

@app.route('/api/complaints_with_location', methods=['GET'])
@login_required
def get_complaints_with_location():
    """Get complaints with location for map"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Get filters
        status = request.args.get('status', 'All Status')
        priority = request.args.get('priority', 'All Priorities')
        
        query = """
            SELECT report_id, full_name, address, 
                   latitude, longitude, details, 
                   priority, status, timestamp,
                   incident_type_detail, contact_number
            FROM power_outage_reports
            WHERE (hidden = FALSE OR hidden IS NULL)
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
        """
        params = []
        
        if status != 'All Status':
            query += " AND status = %s"
            params.append(status)
        
        if priority != 'All Priorities':
            query += " AND priority = %s"
            params.append(priority)
        
        query += " ORDER BY timestamp DESC LIMIT 100"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        complaints = []
        for row in rows:
            complaints.append({
                'id': f'PO-{row[0]:06d}',
                'customer': row[1] or 'Unknown',
                'customerId': row[10] or 'N/A',
                'address': row[2] or 'N/A',
                'lat': float(row[3]) if row[3] else None,
                'lng': float(row[4]) if row[4] else None,
                'description': row[5] or 'No description',
                'priority': (row[6] or 'HIGH').upper(),
                'status': (row[7] or 'NEW').upper(),
                'time': row[8].strftime('%I:%M %p') if row[8] else 'N/A',
                'issueType': row[9] or 'Power Outage',
                'contact': row[10] or 'N/A',
                'source': 'Web Form'
            })
        
        cur.close()
        release_db(conn)
        
        return jsonify({
            'success': True,
            'complaints': complaints,
            'count': len(complaints)
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/update_status/<table>/<int:record_id>', methods=['POST'])
@login_required
def update_status(table, record_id):
    """Update complaint status"""
    try:
        data = request.get_json()
        new_status = data.get('status', '').upper()
        
        if new_status not in ['NEW', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED']:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE power_outage_reports 
            SET status = %s 
            WHERE report_id = %s
        """, (new_status, record_id))
        
        conn.commit()
        cur.close()
        release_db(conn)
        
        print(f"✅ Status updated: {record_id} -> {new_status}")
        
        return jsonify({
            'success': True,
            'message': f'Status updated to {new_status}',
            'new_status': new_status
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/view/<table>/<int:record_id>', methods=['GET'])
@login_required
def view_complaint(table, record_id):
    """View complaint details"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT report_id, full_name, contact_number, email,
                   address, details, priority, status, timestamp,
                   incident_type_detail, affected_area, landmark,
                   latitude, longitude, source
            FROM power_outage_reports
            WHERE report_id = %s
        """, (record_id,))
        
        row = cur.fetchone()
        
        if row:
            details = {
                'Complaint ID': f'PO-{row[0]:06d}',
                'Customer Name': row[1] or 'N/A',
                'Contact Number': row[2] or 'N/A',
                'Email': row[3] or 'N/A',
                '--- LOCATION ---': '',
                'Address': row[4] or 'N/A',
                'Landmark': row[11] or 'N/A',
                'Latitude': row[12] or 'N/A',
                'Longitude': row[13] or 'N/A',
                '--- INCIDENT ---': '',
                'Incident Type': row[9] or 'Power Outage',
                'Affected Area': row[10] or 'Unknown',
                'Details': row[5] or 'No details',
                '--- STATUS ---': '',
                'Priority': row[6] or 'HIGH',
                'Status': row[7] or 'NEW',
                'Source': row[14] or 'Web Form',
                'Timestamp': row[8].strftime('%B %d, %Y %I:%M %p') if row[8] else 'N/A'
            }
            
            cur.close()
            release_db(conn)
            
            return jsonify({
                'title': 'Power Outage Report Details',
                'table_type': 'Power Outage',
                'details': details,
                'status_level': row[7] or 'NEW',
                'priority_level': row[6] or 'HIGH'
            })
        else:
            return jsonify({'error': 'Complaint not found'}), 404
            
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/delete_complaint/<table>/<int:record_id>', methods=['POST'])
@login_required
def delete_complaint(table, record_id):
    """Soft delete complaint"""
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE power_outage_reports 
            SET hidden = TRUE 
            WHERE report_id = %s
        """, (record_id,))
        
        conn.commit()
        cur.close()
        release_db(conn)
        
        return jsonify({
            'success': True,
            'message': 'Complaint hidden successfully'
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Optional: Preview report form
@app.route('/report')
@login_required
def report_preview():
    """Preview public report form"""
    return render_template('report_outage.html')

# Health check
@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'cloud_api': CLOUD_API_URL,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    print("=" * 70)
    print("🏢 ILECO-1 Local Dashboard")
    print("=" * 70)
    print(f"📍 Running on: http://localhost:5000")
    print(f"👤 Default Login: admin / admin123")
    print(f"☁️  Cloud Form: {CLOUD_API_URL}/report")
    print("=" * 70)
    print("✅ Templates should be in: templates/")
    print("   - dashboard.html")
    print("   - login.html")
    print("   - report_outage.html (optional)")
    print("=" * 70)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
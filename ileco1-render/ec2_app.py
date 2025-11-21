# ec2_app.py - PUBLIC FORM ON AWS EC2
# This runs on AWS EC2 and only handles public complaint submissions

import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# DATABASE SETUP (EC2 PostgreSQL)
# ============================================
db_pool = psycopg2.pool.SimpleConnectionPool(
    1, 10,
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "your_password"),
    host="localhost",  # PostgreSQL on same EC2
    port=5432,
    database=os.getenv("DB_NAME", "ileco_db")
)

def get_db():
    return db_pool.getconn()

def release_db(conn):
    db_pool.putconn(conn)

# ============================================
# WEBHOOK TO YOUR LOCAL DASHBOARD
# ============================================
# Set this to your ngrok URL (e.g., https://abc123.ngrok.io)
LOCAL_DASHBOARD_WEBHOOK = os.getenv('LOCAL_WEBHOOK_URL', 'http://localhost:5000')

def notify_local_dashboard(complaint_data):
    """Send complaint data to your local dashboard via webhook"""
    try:
        webhook_url = f"{LOCAL_DASHBOARD_WEBHOOK}/api/webhook/new_complaint"
        
        response = requests.post(
            webhook_url,
            json=complaint_data,
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Notified local dashboard: {complaint_data['report_id']}")
        else:
            logger.warning(f"⚠️ Local dashboard notification failed: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Failed to notify local dashboard: {e}")
        # Don't fail the submission if webhook fails

# ============================================
# PUBLIC ROUTES (Only Report Form)
# ============================================

@app.route('/')
def index():
    """Homepage - redirect to report form"""
    return render_template('report_outage.html')

@app.route('/report')
def report_form():
    """Public complaint form"""
    return render_template('report_outage.html')

@app.route('/api/submit_power_outage', methods=['POST'])
def submit_power_outage():
    """Handle complaint submission"""
    try:
        data = request.get_json()
        
        # Extract data
        full_name = data.get('full_name', '').strip()
        contact_number = data.get('contact_number', '').strip()
        email = data.get('email', '').strip()
        address = data.get('address', '').strip()
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        details = data.get('details', '').strip()
        incident_type = data.get('incident_type', 'power_outage')
        
        # Validate
        if not all([full_name, contact_number, address, details, latitude, longitude]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Determine priority
        critical_types = ['fallen_wire', 'fire_hazard', 'transformer_issue']
        priority = 'CRITICAL' if incident_type in critical_types else 'HIGH'
        
        # Save to EC2 database
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO power_outage_reports 
            (full_name, contact_number, email, address, latitude, longitude, 
             details, incident_type_detail, priority, status, source, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING report_id
        """, (full_name, contact_number, email, address, latitude, longitude,
              details, incident_type, priority, 'NEW', 'Web Form'))
        
        report_id = cur.fetchone()[0]
        conn.commit()
        
        cur.close()
        release_db(conn)
        
        logger.info(f"✅ Report {report_id} saved to EC2 database")
        
        # ============================================
        # 🔴 CRITICAL: Notify your local dashboard
        # ============================================
        complaint_data = {
            'report_id': report_id,
            'full_name': full_name,
            'contact_number': contact_number,
            'email': email,
            'address': address,
            'latitude': latitude,
            'longitude': longitude,
            'details': details,
            'incident_type': incident_type,
            'priority': priority,
            'timestamp': datetime.now().isoformat(),
            'source': 'AWS EC2'
        }
        
        # Send to your local dashboard (non-blocking)
        notify_local_dashboard(complaint_data)
        
        return jsonify({
            'success': True,
            'report_id': report_id,
            'priority': priority,
            'message': 'Report submitted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error submitting report: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/complaints_nearby', methods=['POST'])
def complaints_nearby():
    """Find nearby complaints"""
    try:
        data = request.get_json()
        lat = float(data.get('lat'))
        lng = float(data.get('lng'))
        radius = int(data.get('radius', 1000))
        
        conn = get_db()
        cur = conn.cursor()
        
        # Simple distance query (without PostGIS)
        cur.execute("""
            SELECT 
                report_id,
                incident_type_detail,
                priority,
                status,
                latitude,
                longitude,
                (
                    6371000 * acos(
                        cos(radians(%s)) * 
                        cos(radians(latitude)) * 
                        cos(radians(longitude) - radians(%s)) + 
                        sin(radians(%s)) * 
                        sin(radians(latitude))
                    )
                ) as distance_meters
            FROM power_outage_reports
            WHERE latitude IS NOT NULL 
              AND longitude IS NOT NULL
              AND status != 'RESOLVED'
            HAVING distance_meters < %s
            ORDER BY distance_meters
            LIMIT 10
        """, (lat, lng, lat, radius))
        
        rows = cur.fetchall()
        
        complaints = []
        for row in rows:
            complaints.append({
                'report_id': row[0],
                'type': row[1] or 'Power Outage',
                'priority': row[2],
                'status': row[3],
                'lat': row[4],
                'lng': row[5],
                'distance_meters': round(row[6], 2),
                'distance_km': round(row[6] / 1000, 2)
            })
        
        cur.close()
        release_db(conn)
        
        return jsonify({
            'success': True,
            'complaints': complaints,
            'count': len(complaints)
        })
        
    except Exception as e:
        logger.error(f"Error finding nearby complaints: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'ILECO-1 Public Form (AWS EC2)',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
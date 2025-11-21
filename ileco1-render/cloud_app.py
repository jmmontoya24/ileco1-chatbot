# ADD THIS TO YOUR EXISTING cloud_app.py
# This receives complaints from AWS EC2 and displays in dashboard

@app.route('/api/webhook/new_complaint', methods=['POST'])
def webhook_new_complaint():
    """
    Receive new complaints from AWS EC2 public form
    This endpoint is called by EC2 when someone submits a complaint
    """
    try:
        data = request.get_json()
        
        logger.info(f"📥 Received complaint from AWS EC2: {data.get('report_id')}")
        
        # Save to YOUR local database
        conn = get_rasa_connection()
        if not conn:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        
        cur = conn.cursor()
        
        # Insert complaint into your local database
        cur.execute("""
            INSERT INTO power_outage_reports 
            (full_name, contact_number, email, address, latitude, longitude, 
             details, incident_type_detail, priority, status, source, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING report_id
        """, (
            data.get('full_name'),
            data.get('contact_number'),
            data.get('email'),
            data.get('address'),
            data.get('latitude'),
            data.get('longitude'),
            data.get('details'),
            data.get('incident_type'),
            data.get('priority'),
            'NEW',
            'AWS EC2 Public Form'
        ))
        
        local_report_id = cur.fetchone()[0]
        conn.commit()
        
        cur.close()
        release_db_connection(conn, db_pool)
        
        logger.info(f"✅ Complaint saved locally with ID: {local_report_id}")
        
        # ============================================
        # 🔴 BROADCAST TO DASHBOARD VIA WEBSOCKET
        # ============================================
        complaint_display = {
            'record_id': local_report_id,
            'customer_name': data.get('full_name'),
            'issue_type': 'Power Outage',
            'priority': data.get('priority'),
            'address': data.get('address'),
            'source': 'AWS EC2 Public',
            'timestamp': datetime.now().isoformat()
        }
        
        # Send real-time notification to dashboard
        broadcast_new_complaint(complaint_display)
        
        if data.get('priority') == 'CRITICAL':
            broadcast_critical_alert(complaint_display)
        
        return jsonify({
            'success': True,
            'local_report_id': local_report_id,
            'message': 'Complaint received and displayed on dashboard'
        })
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# ADD THIS: Sync from EC2 to Local (Optional)
# ============================================
@app.route('/api/sync_from_ec2', methods=['POST'])
@login_required
def sync_from_ec2():
    """
    Manually sync complaints from EC2 to local database
    Useful for catching up if your PC was offline
    """
    try:
        ec2_url = os.getenv('EC2_API_URL', 'http://YOUR-EC2-IP:5000')
        
        # Fetch complaints from EC2
        response = requests.get(f"{ec2_url}/api/export_complaints")
        
        if response.status_code == 200:
            ec2_complaints = response.json().get('complaints', [])
            
            conn = get_rasa_connection()
            cur = conn.cursor()
            
            synced = 0
            for complaint in ec2_complaints:
                # Check if already exists
                cur.execute("""
                    SELECT report_id FROM power_outage_reports 
                    WHERE contact_number = %s 
                      AND timestamp::date = %s::date
                """, (complaint['contact_number'], complaint['timestamp']))
                
                if not cur.fetchone():
                    # Insert new complaint
                    cur.execute("""
                        INSERT INTO power_outage_reports 
                        (full_name, contact_number, email, address, latitude, longitude, 
                         details, priority, status, source, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        complaint['full_name'],
                        complaint['contact_number'],
                        complaint['email'],
                        complaint['address'],
                        complaint['latitude'],
                        complaint['longitude'],
                        complaint['details'],
                        complaint['priority'],
                        complaint['status'],
                        'Synced from EC2',
                        complaint['timestamp']
                    ))
                    synced += 1
            
            conn.commit()
            cur.close()
            release_db_connection(conn, db_pool)
            
            return jsonify({
                'success': True,
                'synced': synced,
                'message': f'Synced {synced} new complaints from EC2'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch from EC2'
            }), 500
            
    except Exception as e:
        logger.error(f"Sync error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# ADD THIS: Export API for EC2 to call
# ============================================
@app.route('/api/export_complaints', methods=['GET'])
def export_complaints_api():
    """
    Export complaints for EC2 to sync
    No authentication required for this read-only endpoint
    """
    try:
        conn = get_rasa_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                report_id, full_name, contact_number, email, address,
                latitude, longitude, details, priority, status,
                timestamp, source
            FROM power_outage_reports
            WHERE timestamp > NOW() - INTERVAL '7 days'
            ORDER BY timestamp DESC
        """)
        
        rows = cur.fetchall()
        
        complaints = []
        for row in rows:
            complaints.append({
                'report_id': row[0],
                'full_name': row[1],
                'contact_number': row[2],
                'email': row[3],
                'address': row[4],
                'latitude': row[5],
                'longitude': row[6],
                'details': row[7],
                'priority': row[8],
                'status': row[9],
                'timestamp': row[10].isoformat() if row[10] else None,
                'source': row[11]
            })
        
        cur.close()
        release_db_connection(conn, db_pool)
        
        return jsonify({
            'success': True,
            'complaints': complaints,
            'count': len(complaints)
        })
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
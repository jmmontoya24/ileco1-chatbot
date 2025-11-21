import re
import os
from datetime import datetime
from flask import request, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import logging

logger = logging.getLogger(__name__)

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')  # e.g., +639171234567

# Initialize Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    logger.info("✅ Twilio SMS client initialized")
else:
    logger.warning("⚠️ Twilio credentials not found. SMS features disabled.")


class SMSParser:
    """Parse incoming SMS messages into structured complaint data"""
    
    # SMS Format patterns
    PATTERNS = {
        'standard': r'ILECO\s+(OUTAGE|BILLING|SERVICE)\s+(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)',
        'simple': r'ILECO\s+(.+)',
    }
    
    TYPE_MAPPING = {
        'OUTAGE': 'POWER OUTAGE',
        'BILLING': 'BILLING',
        'SERVICE': 'SERVICE',
        'POWER': 'POWER OUTAGE',
        'METER': 'BILLING',
        'EMERGENCY': 'POWER OUTAGE'
    }
    
    @classmethod
    def parse_sms(cls, message_body, from_number):
        """
        Parse SMS message into complaint data
        
        Args:
            message_body: SMS text content
            from_number: Sender's phone number
            
        Returns:
            dict: Parsed complaint data or None if parsing fails
        """
        message_body = message_body.strip().upper()
        
        # Try standard format first
        match = re.match(cls.PATTERNS['standard'], message_body, re.IGNORECASE)
        if match:
            issue_type, name, address, contact, details = match.groups()
            return {
                'issue_type': cls.TYPE_MAPPING.get(issue_type.upper(), 'SERVICE'),
                'full_name': name.strip().title(),
                'address': address.strip().title(),
                'contact_number': contact.strip(),
                'details': details.strip(),
                'source': 'SMS',
                'priority': cls._determine_priority(details),
                'from_number': from_number
            }
        
        # Try simple format (just message)
        match = re.match(cls.PATTERNS['simple'], message_body, re.IGNORECASE)
        if match:
            content = match.group(1).strip()
            return {
                'issue_type': cls._detect_issue_type(content),
                'full_name': 'SMS User',
                'address': 'To be verified',
                'contact_number': from_number,
                'details': content,
                'source': 'SMS',
                'priority': cls._determine_priority(content),
                'from_number': from_number
            }
        
        return None
    
    @classmethod
    def _detect_issue_type(cls, content):
        """Detect issue type from message content"""
        content_lower = content.lower()
        
        if any(word in content_lower for word in ['outage', 'blackout', 'no power', 'brownout', 'walang kuryente']):
            return 'POWER OUTAGE'
        elif any(word in content_lower for word in ['bill', 'billing', 'bayad', 'presyo']):
            return 'BILLING'
        else:
            return 'SERVICE'
    
    @classmethod
    def _determine_priority(cls, details):
        """Determine priority based on keywords"""
        details_lower = details.lower()
        
        critical_keywords = [
            'fire', 'emergency', 'danger', 'explosion', 'accident',
            'fallen wire', 'live wire', 'sunog', 'emergency', 'delikado'
        ]
        
        if any(word in details_lower for word in critical_keywords):
            return 'CRITICAL'
        
        return 'HIGH'


def send_sms_notification(to_number, message):
    """
    Send SMS notification to a number
    
    Args:
        to_number: Recipient phone number
        message: Message content
    
    Returns:
        bool: Success status
    """
    if not twilio_client:
        logger.error("Twilio client not initialized")
        return False
    
    try:
        message = twilio_client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )
        logger.info(f"✅ SMS sent to {to_number}: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send SMS: {e}")
        return False


def handle_incoming_sms(app, get_rasa_connection, release_db_connection, 
                        db_pool, broadcast_new_complaint, broadcast_critical_alert):
    """
    Setup SMS webhook endpoint for Twilio
    
    Args:
        app: Flask app instance
        get_rasa_connection: Database connection function
        release_db_connection: Database release function
        db_pool: Database pool
        broadcast_new_complaint: WebSocket broadcast function
        broadcast_critical_alert: Critical alert broadcast function
    """
    
    @app.route('/api/sms/webhook', methods=['POST'])
    def sms_webhook():
        """Handle incoming SMS from Twilio"""
        try:
            # Get SMS data from Twilio
            from_number = request.form.get('From', '')
            message_body = request.form.get('Body', '')
            message_sid = request.form.get('MessageSid', '')
            
            logger.info(f"📱 Incoming SMS from {from_number}: {message_body}")
            
            # Parse SMS
            parsed_data = SMSParser.parse_sms(message_body, from_number)
            
            if not parsed_data:
                # Invalid format - send help message
                response = MessagingResponse()
                response.message(
                    "Invalid format. Please use:\n"
                    "ILECO [TYPE] [NAME] | [ADDRESS] | [CONTACT] | [DETAILS]\n\n"
                    "Example:\n"
                    "ILECO OUTAGE Juan Cruz | Brgy. Oton | 09171234567 | No power"
                )
                return str(response), 200
            
            # Save to database
            conn = get_rasa_connection()
            if not conn:
                logger.error("Database connection failed")
                response = MessagingResponse()
                response.message("System error. Please try again later.")
                return str(response), 500
            
            try:
                cur = conn.cursor()
                
                issue_type = parsed_data['issue_type']
                
                # Insert based on issue type
                if issue_type == 'POWER OUTAGE':
                    cur.execute("""
                        INSERT INTO power_outage_reports 
                        (full_name, contact_number, address, details, 
                         priority, status, source, issue_type, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        RETURNING report_id
                    """, (
                        parsed_data['full_name'],
                        parsed_data['contact_number'],
                        parsed_data['address'],
                        parsed_data['details'],
                        parsed_data['priority'],
                        'NEW',
                        'SMS',
                        'Power Outage'
                    ))
                    
                    result = cur.fetchone()
                    record_id = result[0]
                    complaint_id = f"PO-{record_id:06d}"
                    
                elif issue_type == 'BILLING':
                    cur.execute("""
                        INSERT INTO meter_concern 
                        (account_no, name, address, contact_number, concern,
                         priority, status, source, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        RETURNING id
                    """, (
                        'N/A',  # Account number not provided in SMS
                        parsed_data['full_name'],
                        parsed_data['address'],
                        parsed_data['contact_number'],
                        parsed_data['details'],
                        'MEDIUM',
                        'NEW',
                        'SMS'
                    ))
                    
                    result = cur.fetchone()
                    record_id = result[0]
                    complaint_id = f"BC-{record_id:06d}"
                    
                else:  # SERVICE
                    cur.execute("""
                        INSERT INTO agent_queue 
                        (user_id, full_name, concern, contact_number,
                         priority, status, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        RETURNING id
                    """, (
                        parsed_data['from_number'],
                        parsed_data['full_name'],
                        parsed_data['details'],
                        parsed_data['contact_number'],
                        parsed_data.get('priority', 'LOW'),
                        'NEW'
                    ))
                    
                    result = cur.fetchone()
                    record_id = result[0]
                    complaint_id = f"SR-{record_id:06d}"
                
                conn.commit()
                
                logger.info(f"✅ SMS complaint saved: {complaint_id}")
                
                # Broadcast to dashboard
                complaint_data = {
                    'record_id': record_id,
                    'customer_name': parsed_data['full_name'],
                    'issue_type': issue_type,
                    'priority': parsed_data['priority'],
                    'address': parsed_data['address'],
                    'timestamp': datetime.now().isoformat(),
                    'source': 'SMS'
                }
                
                broadcast_new_complaint(complaint_data)
                
                # If critical, send alert
                if parsed_data['priority'] == 'CRITICAL':
                    broadcast_critical_alert(complaint_data)
                
                # Send confirmation SMS
                confirmation_message = (
                    f"✅ ILECO-1: Your complaint has been received.\n"
                    f"Ref: {complaint_id}\n"
                    f"Type: {issue_type}\n"
                    f"Priority: {parsed_data['priority']}\n"
                    f"We will respond shortly."
                )
                
                send_sms_notification(from_number, confirmation_message)
                
                # Respond to Twilio
                response = MessagingResponse()
                response.message(confirmation_message)
                
                return str(response), 200
                
            except Exception as e:
                logger.error(f"❌ Error saving SMS complaint: {e}")
                import traceback
                traceback.print_exc()
                conn.rollback()
                
                response = MessagingResponse()
                response.message("Error processing your complaint. Please try again.")
                return str(response), 500
                
            finally:
                if 'cur' in locals():
                    cur.close()
                release_db_connection(conn, db_pool)
        
        except Exception as e:
            logger.error(f"❌ SMS webhook error: {e}")
            import traceback
            traceback.print_exc()
            
            response = MessagingResponse()
            response.message("System error. Please contact ILECO-1 directly.")
            return str(response), 500
    
    
    @app.route('/api/sms/send', methods=['POST'])
    def send_sms_api():
        """API endpoint to send SMS notifications"""
        try:
            data = request.get_json()
            to_number = data.get('to_number')
            message = data.get('message')
            
            if not to_number or not message:
                return jsonify({
                    'success': False,
                    'error': 'to_number and message required'
                }), 400
            
            success = send_sms_notification(to_number, message)
            
            return jsonify({
                'success': success,
                'message': 'SMS sent successfully' if success else 'Failed to send SMS'
            })
            
        except Exception as e:
            logger.error(f"Send SMS API error: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    
    @app.route('/api/sms/test', methods=['GET'])
    def test_sms():
        """Test SMS integration"""
        if not twilio_client:
            return jsonify({
                'success': False,
                'error': 'Twilio not configured',
                'configured': False
            })
        
        return jsonify({
            'success': True,
            'configured': True,
            'phone_number': TWILIO_PHONE_NUMBER,
            'message': 'SMS integration is active'
        })
    
    logger.info("✅ SMS webhook endpoints registered")
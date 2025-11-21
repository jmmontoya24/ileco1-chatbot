from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction
import psycopg2
import re
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.types import DomainDict
from datetime import datetime
import random
from rasa_sdk.events import SlotSet, FollowupAction, ConversationPaused, ConversationResumed
from rasa_sdk.events import AllSlotsReset, Form
import os


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "rasa_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "5227728"),
    "port": os.getenv("DB_PORT", "5432")
}


class ActionShowCarouselMain(Action):
    def name(self) -> str:
        return "action_show_carousel"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[str, Any]) -> List[Dict[str, Any]]:

        # Reset power outage form slots in case user comes back
        return_slots = [
            SlotSet("po_full_name", None),
            SlotSet("po_address", None),
            SlotSet("po_contact_number", None),
            SlotSet("mc_full_name", None),
            SlotSet("mc_address", None),
            SlotSet("mc_contact_number", None),
            SlotSet("mc_account_no", None),
            SlotSet("mc_meter_concern", None),
            SlotSet("fr_job_order_id", None)
        ]

        elements = [
            {
                "title": "Report of Power Outage",
                "subtitle": "Report an issue",
                "image_url": "https://i.postimg.cc/hP14f5Gz/Power-Outage.jpg",
                "buttons": [
                    {"type": "postback", "title": "Report Power Interruption", "payload": "/report_power_outage"},
                    {"type": "postback", "title": "Schedule Power Outage", "payload": "/schedule_outage"},
                    {"type": "postback", "title": "Follow-Up Report", "payload": "/follow_up_report"}
                ]
            },
            {
                "title": "Billing & Payment Concerns",
                "subtitle": "Ask about your bill",     
                "image_url": "https://i.postimg.cc/sXt0kNnD/kari-kamo-upod-kita.jpg",
                "buttons": [
                    {"type": "postback", "title": "Online Billing", "payload": "/online_billing"},
                    {"type": "postback", "title": "Payment Option", "payload": "/payment_option"}
                ]
            },
            {
                "title": "Application for New Connection",
                "subtitle": "Apply here",
                "image_url": "https://i.postimg.cc/sXt0kNnD/kari-kamo-upod-kita.jpg",
                "buttons": [
                    {"type": "postback", "title": "Requirements ", "payload": "/requirements_checklist"},
                    {"type": "postback", "title": "Schedule of PMOS", "payload": "/schedule_pmos"},
                    {"type": "postback", "title": "Download Application Forms", "payload": "/download_forms"}
                ]
            },
            {
                "title": "Services/Technical Support",
                "subtitle": "Request maintenance or other services",
                "image_url": "https://i.postimg.cc/sXt0kNnD/kari-kamo-upod-kita.jpg",
                "buttons": [
                    {"type": "postback", "title": "Meter Concern", "payload": "/meter_concern"},
                    {"type": "postback", "title": "Transfer of Meter", "payload": "/transfer_of_meter"},
                ]
            },
            {
                "title": "General Information",
                "subtitle": "Get information about our services",
                "image_url": "https://i.postimg.cc/sXt0kNnD/kari-kamo-upod-kita.jpg",
                "buttons": [
                    {"type": "postback", "title": "Contact Information", "payload": "/contact_information"},
                    {"type": "postback", "title": "Rates", "payload": "/rates"},
                    {"type": "postback", "title": "Office Location", "payload": "/office_location"}
                ]
            },
            {
                "title": "Chat with Agent",
                "subtitle": "Talk to a customer service representative",
                "image_url": "https://i.postimg.cc/02qJQ0F6/agentwew.jpg",
                "buttons": [
                    {"type": "postback", "title": "Connect to Available Agent", "payload": "/talk_to_agent"}
                ]
            }
        ]

        facebook_payload = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "generic",
                    "elements": elements
                }
            }
        }
        dispatcher.utter_message(json_message=facebook_payload)

        return return_slots



class ActionSubmitPowerOutageFormEnhanced(Action):
    def name(self) -> Text:
        return "action_submit_power_outage_form"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        # Get data from slots
        full_name = tracker.get_slot("po_full_name")
        address = tracker.get_slot("po_address")
        contact_number = tracker.get_slot("po_contact_number")
        user_id = tracker.sender_id

        try:
            # ✅ FIXED: Only use **DB_CONFIG
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()

            # Check for existing report today
            cursor.execute("""
                SELECT job_order_id, timestamp, status
                FROM power_outage_reports
                WHERE address = %s AND timestamp::date = CURRENT_DATE
                ORDER BY timestamp DESC
                LIMIT 1
            """, (address,))
            existing = cursor.fetchone()

            if existing and existing[2] not in ['RESOLVED', 'FINISHED']:
                job_order_id = existing[0]
                message = (
                    f"⚠️ Hello {full_name}, your outage was already reported today.\n"
                    f"🧾 *Job Order ID:* `{job_order_id}`\n"
                    f"✅ Our team is already working on it."
                )
                
            else:
                job_order_id = f"JO-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

                # Insert new report with correct field names
                cursor.execute("""
                    INSERT INTO power_outage_reports (
                        user_id, 
                        full_name, 
                        address, 
                        contact_number, 
                        job_order_id, 
                        issue_type, 
                        priority, 
                        status, 
                        source, 
                        timestamp,
                        description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id, 
                    full_name, 
                    address, 
                    contact_number, 
                    job_order_id,
                    "POWER OUTAGE",
                    "HIGH", 
                    "NEW",
                    "Chatbot", 
                    datetime.now(),
                    f"Power outage reported at {address}"
                ))

                message = (
                    f"✅ Thank you {full_name}! Your outage report has been logged.\n"
                    f"📄 *Job Order ID:* `{job_order_id}`\n"
                    f"📍 *Location:* {address}\n"
                    f"📱 *Contact:* {contact_number}\n"
                    f"Our crew is on the way to check and determine the cause of the power outage. Thank you for your patience."
                )

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            dispatcher.utter_message(text=f"❌ Error saving report: {str(e)}")
            print(f"Database error: {str(e)}")
            return []

        dispatcher.utter_message(text=message)

        return [
            SlotSet("po_full_name", None),
            SlotSet("po_address", None),
            SlotSet("po_contact_number", None),
        ]

class ValidatePowerOutageForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_power_outage_form"

    def validate_po_full_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        name = slot_value.strip()
        if len(name.split()) >= 2 and all(part.isalpha() or part == '.' for part in name.replace(" ", "")):
            return {"po_full_name": name}
        else:
            dispatcher.utter_message(text="❌ Please enter a valid full name (e.g., Juan Dela Cruz).")
            return {"po_full_name": None}

    def validate_po_address(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        address = slot_value.strip().lower()

        allowed_towns = [
            "tubungan", "alimodian", "cabatuan", "guimbal", "igbaras",
            "leganes", "leon", "miag-ao", "miagao",
            "oton", "pavia", "san joaquin", "san miguel", "sta. barbara", "sta barbara",
            "tigbauan"
        ]

        has_keywords = any(kw in address for kw in ["brgy", "purok", "street", "city", "blk"])
        contains_allowed_town = any(town in address for town in allowed_towns)

        if len(address) >= 10 and has_keywords and contains_allowed_town:
            return {"po_address": slot_value.strip()}
        else:
            dispatcher.utter_message(
                text="❌ Please provide a more detailed address with your barangay and town "
                     "(e.g., Brgy. Bacan, Cabatuan, Iloilo)."
            )
            return {"po_address": None}

    def validate_po_contact_number(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        if re.fullmatch(r"09\d{9}", slot_value):
            return {"po_contact_number": slot_value}
        else:
            dispatcher.utter_message(
                text=(
                    "❌ The contact number is invalid.\n"
                    "📌 It must be an 11-digit number starting with *09*.\n"
                    "🔄 Example: *09123456789*"
                )
            )
            return {"po_contact_number": None}
    

class ActionSubmitFollowUpReportForm(Action):
    def name(self) -> Text:
        return "action_submit_follow_up_report_form"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        fr_job_order_id = tracker.get_slot("fr_job_order_id")

        try:
            # ✅ FIXED: Only use **DB_CONFIG
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT full_name, address, contact_number, status, timestamp
                FROM power_outage_reports
                WHERE job_order_id = %s
            """, (fr_job_order_id,))

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result:
                full_name, address, contact_number, status, timestamp = result
                status_lower = status.lower()

                if status_lower in ["completed", "finished"]:
                    message = (
                        f"✅ Thank you for your patience.\n\n"
                        f"🧾 *Job Order ID:* `{fr_job_order_id}`\n"
                        f"📌 Your report has been resolved as *{status}*.\n"
                        f"If you still face issues, feel free to report again."
                    )
                elif status_lower in ["in progress", "pending"]:
                    message = (
                        f"📄 Thank you for your patience.\n\n"
                        f"🔄 *Current Status:* `{status}`\n\n"
                        f"🙏 We're working to resolve the issue."
                    )
                else:
                    message = (
                        f"📌 Status update for `{fr_job_order_id}` is: `{status}`.\n\n"
                        f"Thank you for your understanding."
                    )
            else:
                message = (
                    f"❗ No report found with Job Order `{fr_job_order_id}`.\n"
                    f"Please double-check the number."
                )

        except Exception as e:
            message = f"❌ Error checking report: {str(e)}"

        dispatcher.utter_message(text=message)
        return [
            SlotSet("fr_job_order_id", None),
        ]

class ActionSubmitMeterConcern(Action):
    def name(self) -> str:
        return "action_submit_meter_concern"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any]
    ) -> List[Dict[str, Any]]:

        account_no = tracker.get_slot("mc_account_no")
        full_name = tracker.get_slot("mc_full_name")
        address = tracker.get_slot("mc_address")
        contact_number = tracker.get_slot("mc_contact_number")
        concern = tracker.get_slot("mc_meter_concern")
        user_id = tracker.sender_id

        if all([account_no, full_name, address, contact_number, concern]):
            job_order_id = f"JO-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        else:
            dispatcher.utter_message(
                text="⚠️ Some details are missing. Please complete the form."
            )
            return []

        try:
            # ✅ FIXED: Only use **DB_CONFIG
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            insert_query = """
                INSERT INTO meter_concern (
                    user_id, job_order_id, account_no, name, address, contact_number, concern, priority, status, source, timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                insert_query,
                (
                    user_id,
                    job_order_id,
                    account_no,
                    full_name,
                    address,
                    contact_number,
                    concern,
                    "MEDIUM",
                    "PENDING",
                    "Chatbot",
                    datetime.now(),
                ),
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            dispatcher.utter_message(
                text=f"⚠️ An error occurred while saving your report: {e}"
            )
            return []

        dispatcher.utter_message(
            text=f"✅ Thank you, *{full_name}*! Your meter concern has been successfully submitted.\n📝 Job Order ID: *{job_order_id}*\n📞 Please expect a call from our crew for the inspection schedule."
        )

        return [
            SlotSet("mc_account_no", None),
            SlotSet("mc_full_name", None),
            SlotSet("mc_address", None),
            SlotSet("mc_contact_number", None),
            SlotSet("mc_meter_concern", None),
        ]

class ValidateMeterConcernForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_meter_concern_form"

    def validate_mc_account_no(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        account_no = slot_value.strip()

        if not re.fullmatch(r"\d{6,12}", account_no):
            dispatcher.utter_message(
                text="❌ Invalid account number.\n🔄 Please enter a valid number (6–12 digits)."
            )
            return {"mc_account_no": None}

        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("SELECT acctno FROM consumer_accounts WHERE acctno = %s", (account_no,))
            result = cur.fetchone()
            cur.close()
            conn.close()

            if result:
                return {"mc_account_no": account_no}
            else:
                dispatcher.utter_message(
                    text="❌ This account number does not exist in our records. Please double-check."
                )
                return {"mc_account_no": None}

        except Exception as e:
            dispatcher.utter_message(text=f"⚠️ Database error: {e}")
            return {"mc_account_no": None}

    def validate_mc_full_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        full_name = slot_value.strip()

        if len(full_name.split()) < 2 or not all(part.isalpha() or part == '.' for part in full_name.replace(" ", "")):
            dispatcher.utter_message(text="❌ Please enter a valid full name (e.g., Juan Dela Cruz).")
            return {"mc_full_name": None}
        return {"mc_full_name": full_name}

    def validate_mc_address(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        address = slot_value.strip().lower()

        allowed_towns = [
            "tubungan", "alimodian", "cabatuan", "guimbal", "igbaras",
            "leganes", "leon", "miag-ao", "miagao",
            "oton", "pavia", "san joaquin", "san miguel",
            "sta. barbara", "sta barbara", "tigbauan"
        ]

        has_keywords = any(kw in address for kw in ["brgy", "purok", "street", "blk", "city"])
        contains_allowed_town = any(town in address for town in allowed_towns)

        if len(address) >= 10 and has_keywords and contains_allowed_town:
            return {"mc_address": slot_value.strip()}
        else:
            dispatcher.utter_message(
                text="❌ Please provide a more detailed address with barangay and town "
                     "(e.g., Brgy. Bacan, Cabatuan, Iloilo)."
            )
            return {"mc_address": None}

    def validate_mc_contact_number(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        if re.fullmatch(r"09\d{9}", slot_value):
            return {"mc_contact_number": slot_value}
        else:
            dispatcher.utter_message(
                text="❌ Invalid contact number.\n📌 It must start with *09* and be 11 digits.\n🔄 Example: *09123456789*"
            )
            return {"mc_contact_number": None}

    def validate_mc_meter_concern(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        keywords = [
            "no display",
            "faded reading",
            "burned",
            "not rotating",
            "stuck up",
            "broken",
            "tilting",
            "defective",
            "damaged",
            "malfunction",
        ]
        
        user_input = slot_value.strip().lower()
        for keyword in keywords:
             if keyword in user_input:
              return {"mc_meter_concern": keyword}
        
        dispatcher.utter_message(text="❌ Sorry, that's not a valid meter concern. Please try again.")
        return {"mc_meter_concern": None}


        
        
class ActionCheckAgreement(Action):
    def name(self) -> Text:
        return "action_check_terms"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        if tracker.get_slot("terms_agreed") is not True:
            dispatcher.utter_message(response="utter_greet")
            return []
        
        return []

class ActionShowCarousel(Action):
    def name(self) -> str:
        return "action_show_carousel_extra"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[str, Any]) -> List[Dict[str, Any]]:

        elements = [
            {
                "title": "Report of Power Outage",
                "subtitle": "Report an issue",
                "image_url": "https://i.postimg.cc/hP14f5Gz/Power-Outage.jpg",
                "buttons": [
                    {"type": "postback", "title": "Report a Power Outage", "payload": "/report_power_outage"},
                    {"type": "postback", "title": "Schedule Power Outage", "payload": "/schedule_outage"},
                    {"type": "postback", "title": "Follow-Up Report", "payload": "/follow_up_report"}
                ]
            },
            {
                "title": "Billing & Payment Concerns",
                "subtitle": "Ask about your bill",     
                "image_url": "https://i.postimg.cc/sXt0kNnD/kari-kamo-upod-kita.jpg",
                "buttons": [
                    {"type": "postback", "title": "Online Billing", "payload": "/online_billing"},
                    {"type": "postback", "title": "Payment Option", "payload": "/payment_option"}
                ]
            },
            {
                "title": "Application for New Connection",
                "subtitle": "Apply here",
                "image_url": "https://i.postimg.cc/sXt0kNnD/kari-kamo-upod-kita.jpg",
                "buttons": [
                    {"type": "postback", "title": "Requirements ", "payload": "/requirements_checklist"},
                    {"type": "postback", "title": "Schedule of PMOS", "payload": "/schedule_pmos"},
                    {"type": "postback", "title": "Download Application Forms", "payload": "/download_forms"}
                ]
            },
            {
                "title": "Services/Technical Support",
                "subtitle": "Request maintenance or other services",
                "image_url": "https://i.postimg.cc/sXt0kNnD/kari-kamo-upod-kita.jpg",
                "buttons": [
                    {"type": "postback", "title": "Meter Concern", "payload": "/meter_concern"},
                    {"type": "postback", "title": "Transfer of Meter", "payload": "/transfer_of_meter"},
                ]
            },
            {
                "title": "General Information",
                "subtitle": "Get information about our services",
                "image_url": "https://i.postimg.cc/sXt0kNnD/kari-kamo-upod-kita.jpg",
                "buttons": [
                    {"type": "postback", "title": "Contact Information", "payload": "/contact_information"},
                    {"type": "postback", "title": "Rates", "payload": "/rates"},
                    {"type": "postback", "title": "Office Location", "payload": "/energy_saving_tips"}
                ]
            },
            {
                "title": "Chat with Agent",
                "subtitle": "Talk to a customer service representative",
                "image_url": "https://i.postimg.cc/02qJQ0F6/agentwew.jpg",
                "buttons": [
                    {"type": "postback", "title": "Connect to Available Agent", "payload": "/talk_to_agent"}
                ]
            }
        ]

        facebook_payload = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "generic",
                    "elements": elements
                }
            }
        }

        dispatcher.utter_message(text="📋 Please choose an option below if you want to have another transaction:")
        dispatcher.utter_message(json_message=facebook_payload)
        return []

class ValidateFollowUpReportForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_follow_up_report_form"

    def validate_fr_job_order_id(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> Dict[Text, Any]:

        match = re.fullmatch(r"JO-\d{8}-\d{4}", slot_value.upper().strip())
        if match:
            return {"fr_job_order_id": match.group(0)}
        else:
            dispatcher.utter_message(text=(
                "❗ The Job Order Number you entered seems invalid.\n"
                "Please make sure it looks like this format: `JO-YYYYMMDD-XXXX`"
            ))
            return {"fr_job_order_id": None}


class ActionResumeConversation(Action):
    def name(self) -> Text:
        return "action_resume_conversation"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        return [ConversationResumed()]

class ActionSubmitTalkToAgentForm(Action):
    def name(self) -> Text:
        return "action_submit_talk_to_agent_form"

    def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        full_name = tracker.get_slot("tta_full_name")
        concern = tracker.get_slot("tta_concern")
        contact_number = tracker.get_slot("tta_contact_number")
        priority = self.get_priority_from_concern(concern)
        user_id = tracker.sender_id
        timestamp = datetime.now()

        if not full_name or not contact_number or not concern:
            dispatcher.utter_message(text=(
                "⚠️ *Incomplete Information Detected!*\n"
                "Please make sure you've provided your full name, concern, and contact number so we can assist you properly. 😊"
            ))
            return []

        try:
            # ✅ FIXED: Only use **DB_CONFIG
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO agent_queue (user_id, full_name, concern, contact_number, priority, timestamp, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'Pending')
            """, (user_id, full_name, concern, contact_number, priority, timestamp))

            cursor.execute("SELECT user_id FROM agent_queue WHERE status = 'Pending' ORDER BY timestamp ASC")
            queue = cursor.fetchall()

            user_ids = [row[0] for row in queue]
            queue_positions = {uid: idx + 1 for idx, uid in enumerate(user_ids)}
            queue_position = queue_positions[user_id]

            conn.commit()
            cursor.close()
            conn.close()

            dispatcher.utter_message(text=(
                f"✅ *Thank you, {full_name}!* Your concern has been successfully recorded. \n\n"
                f"📌 *Concern:* _{concern}_\n"
                f"📞 *Contact Number:* `{contact_number}`\n"
            ))

            dispatcher.utter_message(text=(
                f"🙏 We appreciate your patience.\n"
                f"You are currently *#{queue_position}* in the queue.\n"
                f"Please stay connected — one of our friendly agents will reach out shortly!"
            ))

            return [
                SlotSet("tta_full_name", None),
                SlotSet("tta_concern", None),
                SlotSet("tta_contact_number", None),
                ConversationPaused()
            ]

        except Exception as e:
            dispatcher.utter_message(text=(
                "❌ *Oops! Something went wrong while processing your request.*\n"
                "Please try again in a few moments.\n\n"
                "_Our team is working to resolve this as soon as possible!_ 🙏"
            ))
            print(f"Error submitting to agent queue: {e}")
            return []

    def get_priority_from_concern(self, concern: Text) -> Text:
        concern = (concern or "").lower()
        if any(word in concern for word in ["emergency", "fire", "fallen", "accident", "hazard"]):
            return "critical"
        elif any(word in concern for word in ["no electricity", "power outage", "blackout"]):
            return "high"
        elif any(word in concern for word in ["billing", "bill", "payment", "follow-up", "follow up"]):
            return "medium"
        elif any(word in concern for word in ["transfer", "new connection", "installation", "application"]):
            return "low"
        else:
            return "low"
        
    class ActionServeNextUser(Action):
        def name(self) -> Text:
            return "action_serve_next_user"

    def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        try:
            # ✅ FIXED: Only use **DB_CONFIG
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, user_id, full_name 
                FROM agent_queue 
                WHERE status = 'Pending' 
                ORDER BY timestamp ASC 
                LIMIT 1
            """)
            first_user = cursor.fetchone()

            if not first_user:
                dispatcher.utter_message(text="🎉 No more users in the queue.")
                return []

            record_id, user_id, full_name = first_user

            cursor.execute("UPDATE agent_queue SET status = 'Resolved' WHERE id = %s", (record_id,))
            conn.commit()

            dispatcher.utter_message(text=f"👤 *{full_name}* has now been served and removed from the queue.")

            cursor.close()
            conn.close()
            return []

        except Exception as e:
            dispatcher.utter_message(text="❌ Failed to serve next user.")
            print(f"Error in ActionServeNextUser: {e}")
            return []

class ValidateTalkToAgentForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_talk_to_agent_form"

    def validate_tta_full_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        full_name = slot_value.strip()
        if len(full_name.split()) >= 2 and all(part.isalpha() or part == '.' for part in full_name.replace(" ", "")):
            return {"tta_full_name": full_name}
        else:
            dispatcher.utter_message(text="❌ Please enter a valid full name (e.g., Juan Dela Cruz).")
            return {"tta_full_name": None}

    def validate_tta_contact_number(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        if re.fullmatch(r"09\d{9}", slot_value):
            return {"tta_contact_number": slot_value}
        else:
            dispatcher.utter_message(
                text="❌ Invalid contact number.\n📌 It must start with *09* and be 11 digits.\n🔄 Example: *09123456789*"
            )
            return {"tta_contact_number": None}

def validate_tta_concern(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:

        concern_map = {
            "1": "no electricity",
            "2": "emergency",
            "3": "billing issue",
            "4": "new connection",
            "5": "follow-up",
            "6": "transfer or disconnection",
            "7": "others"
        }

        value = slot_value.strip().lower()
        mapped = concern_map.get(value)

        if mapped:
            return {"tta_concern": mapped}
        elif len(value) >= 5:
            return {"tta_concern": value}
        else:
            dispatcher.utter_message(
                text="❌ Please describe your concern in more detail (e.g., 'No electricity', 'Billing issue')."
            )
            return {"tta_concern": None}

class ActionDefaultFallback(Action):

    def name(self) -> Text:
        return "action_default_fallback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text=(
            "😕 I'm sorry, I didn't quite understand that.\n"
            "Type 'menu' to continue?"
        ))
        return []
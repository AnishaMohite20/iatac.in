import os
import sys
# Add local site-packages to path for shared hosting
sys.path.append(os.path.join(os.path.dirname(__file__), "site-packages"))

import secrets
import datetime
import threading
from flask import Flask, request, jsonify, send_from_directory
import razorpay
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import gspread
from google.oauth2.service_account import Credentials
import pytz
from fpdf import FPDF
from dotenv import load_dotenv

from flask_cors import CORS

load_dotenv()

app = Flask(__name__, static_folder='.')
CORS(app)  # Enable CORS for all routes

# Configuration
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET')
PDF_CO_KEY = os.getenv('PDF_CO_KEY')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
MANAGER_EMAIL = "office.ravindra@gmail.com"
GOOGLE_SHEET_CREDS_FILE = os.getenv('GOOGLE_SHEET_CREDS_FILE')
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME')

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

SERVICE_PRICES = {
    "Annual Fee (All)": 5000 * 100,
    "HR Services Company Membership": 5000 * 100,
    "HR Consultants Membership": 3000 * 100,
    "Corporates Membership": 15000 * 100,
    "Demo Service": 1 * 100
}

SERVICE_CATEGORIES = {
    "HR Services Company Membership": "HR Services",
    "HR Consultants Membership": "HR Consultant",
    "Corporates Membership": "Corporate",
    "Annual Fee (All)": "Membership",
    "Demo Service": "Membership"
}

@app.route('/')
def home():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

@app.route('/create_order', methods=['POST'])
def create_order():
    try:
        data = request.json
        service_name = data.get('service')
        user_name = data.get('name')
        user_email = data.get('email')
        user_phone = data.get('phone')

        if service_name not in SERVICE_PRICES:
            return jsonify({"error": "Invalid service selected"}), 400

        amount = SERVICE_PRICES[service_name]
        order_data = {
            "amount": amount,
            "currency": "INR",
            "receipt": f"IATAC_{secrets.token_hex(4).upper()}",
            "notes": {
                "User Name": user_name,
                "Mobile": user_phone,
                "Email": user_email,
                "Service": service_name
            }
        }
        order = client.order.create(data=order_data)
        return jsonify(order)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def send_email_async(to_email, subject, body):
    """Background task to send email"""
    if not SENDER_PASSWORD or "YOUR" in SENDER_PASSWORD:
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"SMTP Error: {e}")

def log_to_google_sheet(user_details, order_id):
    """Background task to log payment to Google Sheets"""
    if not GOOGLE_SHEET_CREDS_FILE or not os.path.exists(GOOGLE_SHEET_CREDS_FILE):
        print("Google Sheet Credentials file missing.")
        return

    try:
        # 1. Setup Auth
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(GOOGLE_SHEET_CREDS_FILE, scopes=scope)
        gc = gspread.authorize(creds)

        # 2. Open Sheet
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.get_worksheet(0)

        # 3. Prepare Timezone (IST)
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        
        # 4. Map Category
        category = SERVICE_CATEGORIES.get(user_details['service'], "Membership")

        # 5. Prepare Row Data
        row = [
            now.strftime("%d-%m-%Y"),           # Transaction Date
            now.strftime("%H:%M:%S"),           # Transaction Time
            user_details['name'],               # User Full Name
            user_details['phone'],              # User Mobile Number
            user_details['email'],              # User Email Address
            user_details['service'],            # Selected Service Name
            category,                           # Service Category
            user_details['amount'],             # Amount Paid (INR)
            user_details['method'],              # Payment Method
            user_details['payment_id'],         # Razorpay Payment ID
            order_id,                           # Order ID
            "SUCCESS",                          # Payment Status
            "iatac.in",                         # Website Source
            "Yes",                              # Receipt Generated
            "Yes",                              # Manager Email Sent
            "N/A",                              # PDF Receipt URL
            now.strftime("%Y-%m-%d %H:%M:%S")  # Created At (Timestamp)
        ]

        # 6. Check for duplicates (using Payment ID)
        # To keep it efficient, we just append. Dedup should ideally happen via payment_id check if sheet is small.
        worksheet.append_row(row)
        print("Payment logged to Google Sheet successfully.")

    except Exception as e:
        print(f"Google Sheet Error: {e}")

class IATACReceipt(FPDF):
    def header(self):
        # Logo
        if os.path.exists("images/logo-iatac.png"):
            self.image("images/logo-iatac.png", 10, 8, 33)
        self.set_font("helvetica", "B", 20)
        self.set_text_color(0, 123, 255) # Primary Blue
        self.cell(80)
        self.cell(100, 10, "OFFICIAL RECEIPT", border=0, align="R", ln=1)
        self.ln(20)

    def footer(self):
        self.set_y(-35)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(169, 169, 169)
        self.cell(0, 10, "This is a computer-generated document. No signature is required.", align="C", ln=1)
        self.set_font("helvetica", "B", 10)
        self.set_text_color(45, 52, 70)
        self.cell(0, 10, "IATAC - Indian Association of Talent Acquisition Consultants", align="C", ln=1)
        self.set_font("helvetica", "", 8)
        self.cell(0, 5, "Office-609, Parth Solitaire, Sector-9E, Kalamboli, Navi Mumbai - 410218", align="C")

def generate_receipt_pdf(details):
    """Generate a pixel-perfect PDF using fpdf2"""
    try:
        if not os.path.exists("receipts"):
            os.makedirs("receipts")

        pdf = IATACReceipt()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Billing Info
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 10, "BILLED TO:", ln=1)
        pdf.set_font("helvetica", "", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 6, f"{details['name']}", ln=1)
        pdf.cell(0, 6, f"Mobile: {details['phone']}", ln=1)
        pdf.cell(0, 6, f"Email: {details['email']}", ln=1)
        
        # Receipt Info (Top Right positioning using set_xy)
        pdf.set_xy(140, 45)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(50, 6, "RECEIPT NO:", align="R", ln=1)
        pdf.set_x(140)
        pdf.set_font("helvetica", "", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(50, 6, f"#{details['receipt_no']}", align="R", ln=1)
        pdf.set_x(140)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(50, 6, "DATE:", align="R", ln=1)
        pdf.set_x(140)
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(50, 6, f"{details['date']}", align="R", ln=1)

        pdf.ln(20)

        # Table Header
        pdf.set_fill_color(0, 123, 255)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", "B", 11)
        pdf.cell(100, 10, " Description", border=1, fill=True)
        pdf.cell(50, 10, " Transaction ID", border=1, fill=True, align="C")
        pdf.cell(40, 10, " Amount", border=1, fill=True, align="R")
        pdf.ln()

        # Table Row
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("helvetica", "", 10)
        pdf.cell(100, 15, f" {details['service']}", border=1)
        pdf.set_font("courier", "", 9)
        pdf.cell(50, 15, f" {details['payment_id']}", border=1, align="C")
        pdf.set_font("helvetica", "B", 11)
        pdf.cell(40, 15, f" INR {details['amount']:.2f} ", border=1, align="R")
        pdf.ln()

        # Total Section
        pdf.ln(10)
        pdf.set_x(140)
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(50, 10, "TOTAL RECEIVED:", align="R")
        pdf.set_font("helvetica", "B", 16)
        pdf.set_text_color(0, 123, 255)
        pdf.cell(0, 10, f" INR {details['amount']:.2f}", ln=1, align="R")

        # Payment Method
        pdf.ln(5)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 10, f"Payment Method: {details['method'].upper()}", ln=1)
        pdf.set_text_color(40, 167, 69) # Green
        pdf.cell(0, 10, "Status: PAID", ln=1)

        filename = f"Receipt_{details['payment_id']}.pdf"
        filepath = os.path.join("receipts", filename)
        pdf.output(filepath)
        return filename
    except Exception as e:
        print(f"PDF Generation Error: {e}")
        return None

@app.route('/download_receipt/<filename>')
def download_receipt(filename):
    return send_from_directory("receipts", filename, as_attachment=True)

@app.route('/contact_submit', methods=['POST'])
def contact_submit():
    try:
        data = request.json
        name = data.get('name')
        mobile = data.get('mobile')
        email = data.get('email')
        message = data.get('message')
        honeypot = data.get('honeypot')

        # 1. Simple Honeypot Spam Prevention
        if honeypot:
            return jsonify({"status": "Error", "message": "Spam detected."}), 400

        # 2. Validation
        if not all([name, mobile, email, message]):
            return jsonify({"status": "Error", "message": "All fields are required."}), 400

        # 3. Format Email
        subject = f"New Contact Enquiry from {name}"
        contact_email_to = "iatac.mumbai@gmail.com"
        
        email_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 25px; border: 1px solid #e1e1e1; border-radius: 12px; max-width: 600px; color: #333;">
            <h2 style="color: #007bff; margin-top: 0; border-bottom: 2px solid #007bff; padding-bottom: 10px;">New Website Enquiry</h2>
            <p style="margin-top: 20px;">You have received a new message from the <strong>iatac.in</strong> website.</p>
            
            <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                <tr>
                    <td style="padding: 10px; border: 1px solid #eee; background: #f9f9f9; font-weight: bold; width: 30%;">Name</td>
                    <td style="padding: 10px; border: 1px solid #eee;">{name}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #eee; background: #f9f9f9; font-weight: bold;">Mobile</td>
                    <td style="padding: 10px; border: 1px solid #eee;">{mobile}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border: 1px solid #eee; background: #f9f9f9; font-weight: bold;">Email</td>
                    <td style="padding: 10px; border: 1px solid #eee;">{email}</td>
                </tr>
            </table>
            
            <div style="margin-top: 20px; padding: 15px; background: #f4f7f6; border-radius: 8px; border-left: 4px solid #007bff;">
                <h4 style="margin: 0 0 10px 0; color: #007bff;">Message:</h4>
                <p style="margin: 0; line-height: 1.6;">{message}</p>
            </div>
            
            <div style="margin-top: 25px; font-size: 0.85rem; color: #888; text-align: center; border-top: 1px solid #eee; padding-top: 15px;">
                Sent from IATAC Contact Form | {datetime.datetime.now().strftime("%d-%b-%Y %I:%M %p")}
            </div>
        </div>
        """

        # 4. Dispatch Email in Background
        threading.Thread(target=send_email_async, args=(contact_email_to, subject, email_body)).start()

        return jsonify({"status": "Success", "message": "Your message has been sent successfully!"})

    except Exception as e:
        print(f"Contact Submit Error: {e}")
        return jsonify({"status": "Error", "message": str(e)}), 500

@app.route('/verify_payment', methods=['POST'])
def verify_payment():
    try:
        data = request.json
        params_dict = {
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        }
        
        # 1. Verify Signature
        client.utility.verify_payment_signature(params_dict)

        # 2. Get Payment Details
        payment_info = client.payment.fetch(data['razorpay_payment_id'])
        order_info = client.order.fetch(data['razorpay_order_id'])
        
        user_details = {
            "name": order_info['notes'].get('User Name'),
            "phone": order_info['notes'].get('Mobile'),
            "email": order_info['notes'].get('Email'),
            "service": order_info['notes'].get('Service'),
            "amount": payment_info['amount'] / 100,
            "payment_id": data['razorpay_payment_id'],
            "receipt_no": order_info['receipt'],
            "date": datetime.datetime.now().strftime("%d-%b-%Y %I:%M:%S %p IST"),
            "method": payment_info.get('method', 'N/A')
        }

        # 3. Handle Emails in Background
        manager_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 8px;">
            <h2 style="color: #007bff;">New Membership Payment Received</h2>
            <p><strong>Customer Name:</strong> {user_details['name']}</p>
            <p><strong>Service:</strong> {user_details['service']}</p>
            <p><strong>Amount Paid:</strong> ₹{user_details['amount']}</p>
            <p><strong>Mobile:</strong> {user_details['phone']}</p>
            <p><strong>Email:</strong> {user_details['email']}</p>
            <p><strong>Transaction ID:</strong> {user_details['payment_id']}</p>
            <p><strong>Date/Time:</strong> {user_details['date']}</p>
            <hr>
            <p style="font-size: 0.9em; color: #666;">Sent from IATAC Payment System</p>
        </div>
        """
        
        user_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 8px;">
            <h2 style="color: #28a745;">Payment Successful!</h2>
            <p>Dear {user_details['name']},</p>
            <p>Your payment for <strong>{user_details['service']}</strong> has been successfully received.</p>
            <p><strong>Amount:</strong> ₹{user_details['amount']}</p>
            <p><strong>Transaction ID:</strong> {user_details['payment_id']}</p>
            <p>You can download your official receipt from the website or save this email for your records.</p>
            <br>
            <p>Best Regards,<br><strong>Team IATAC</strong></p>
        </div>
        """

        threading.Thread(target=send_email_async, args=(MANAGER_EMAIL, "Custom Payment Alert", manager_body)).start()
        threading.Thread(target=send_email_async, args=(user_details['email'], "IATAC Payment Confirmation", user_body)).start()
        
        # 4. Log to Google Sheet in Background
        threading.Thread(target=log_to_google_sheet, args=(user_details, data['razorpay_order_id'])).start()

        # 5. Generate Server-Side PDF
        pdf_filename = generate_receipt_pdf(user_details)
        if pdf_filename:
            user_details['pdf_url'] = f"/download_receipt/{pdf_filename}"
        else:
            user_details['pdf_url'] = None

        # 6. Return user_details to the frontend for instant receipt generation
        return jsonify({ "status": "Success", "details": user_details })
        
    except Exception as e:
        print(f"Verify Error: {e}")
        return jsonify({ "status": "Error", "error": str(e) }), 500

        
    except Exception as e:
        print(f"Verify Error: {e}")
        return jsonify({ "status": "Error", "error": str(e) }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

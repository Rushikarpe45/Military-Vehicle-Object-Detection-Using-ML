import cv2
import numpy as np
import easyocr
import mysql.connector
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, Response, request, jsonify

app = Flask(__name__)

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Rishikarpev@77711',
    'database': 'license_plate_db'
}

# Email configuration
email_config = {
    'smtp_server': 'smtp.gmail.com',
    'port': 587,
    'email': 'karperushikesh42@gmail.com',
    'password': 'htet xgoj hati qplw'
}

# Predefined list of recipients
email_recipients = [
    "karperushikesh42@gmail.com",
]

reader = easyocr.Reader(['en'])
detected_text = ""

# Helper function to send an email to multiple recipients
def send_email(subject, body):
    """
    Sends an email with the given subject and body to a predefined list of recipients.
    
    Args:
        subject (str): Subject of the email.
        body (str): Body content of the email.
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = email_config['email']
        msg['To'] = ", ".join(email_recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(email_config['smtp_server'], email_config['port']) as server:
            server.starttls()
            server.login(email_config['email'], email_config['password'])
            server.sendmail(email_config['email'], email_recipients, msg.as_string())
        print(f"Email sent successfully to {email_recipients}")
    except Exception as e:
        print(f"Failed to send email: {e}")

@app.route('/plate_counts', methods=['GET'])
def plate_counts():
    """Return the count of plates scanned today."""
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        
        # Query to count the occurrences of each plate scanned today
        query = """
            SELECT number_plate, COUNT(*) as count 
            FROM captured_plates 
            WHERE DATE(capturedOn) = CURDATE()
            GROUP BY number_plate 
            ORDER BY count DESC
        """
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        connection.close()
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})

# Check if a plate is authorized and send an email if unauthorized
def check_authorized_plate(plate):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)

        # Check if plate exists in authorized plates
        query_check = "SELECT * FROM authorized_plates WHERE plate_number = %s"
        cursor.execute(query_check, (plate,))
        result = cursor.fetchone()
        is_authorized = result is not None

        # Log captured plate
        query_insert = "INSERT INTO captured_plates (number_plate) VALUES (%s)"
        cursor.execute(query_insert, (plate,))
        connection.commit()

        cursor.close()
        connection.close()

        # If unauthorized, send an email to the list of recipients
        if not is_authorized:
            subject = "Unauthorized Vehicle Detected"
            body = f"An unauthorized vehicle with plate number {plate} has been detected."
            send_email(subject, body)

        return is_authorized
    except Exception as e:
        print(f"Error in processing plate: {e}")
        return False

def add_authorized_plate(plate):
    """Add a new authorized plate to the database."""
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    query = "INSERT INTO authorized_plates (plate_number) VALUES (%s)"
    try:
        cursor.execute(query, (plate,))
        connection.commit()
        return True
    except mysql.connector.IntegrityError:
        return False
    finally:
        cursor.close()
        connection.close()

def preprocess_license_plate(roi):
    """Preprocess the license plate for OCR."""
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    threshold = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
    kernel = np.ones((3, 3), np.uint8)
    clean = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel)
    sharpen_kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    sharp = cv2.filter2D(clean, -1, sharpen_kernel)
    return sharp

def process_frame(frame):
    """Process the video frame for license plate detection and OCR."""
    global detected_text
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)

        keypoints = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = keypoints[0] if len(keypoints) == 2 else keypoints[1]
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

        location = None
        for contour in contours:
            approx = cv2.approxPolyDP(contour, 10, True)
            if len(approx) == 4:
                location = approx
                break

        if location is not None:
            mask = np.zeros(gray.shape, np.uint8)
            cv2.drawContours(mask, [location], 0, 255, -1)
            (x, y) = np.where(mask == 255)
            (x1, y1) = (np.min(x), np.min(y))
            (x2, y2) = (np.max(x), np.max(y))
            roi = frame[x1:x2 + 1, y1:y2 + 1]

            # Draw rectangle around the detected plate
            cv2.rectangle(frame, (y1, x1), (y2, x2), (0, 255, 0), 2)

            processed_roi = preprocess_license_plate(roi)
            result = reader.readtext(processed_roi, detail=0, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")
            if result:
                filtered_result = [text for text in result if text.upper() != "IND"]
                detected_text = " ".join(filtered_result).strip()

        return frame
    except Exception as e:
        print(f"Error processing frame: {e}")
        return frame

@app.route('/')
def index():
    return render_template('index.html')

def gen_frames():
    """Generate frames from the camera."""
    cap = cv2.VideoCapture(0)
    while True:
        success, frame = cap.read()
        if not success:
            break
        else:
            processed_frame = process_frame(frame)
            _, buffer = cv2.imencode('.jpg', processed_frame)
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    cap.release()

@app.route('/video_feed')
def video_feed():
    """Video streaming route."""
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/detected_plate')
def detected_plate():
    """Return the detected plate number."""
    return jsonify({"plate": detected_text})

@app.route('/check_plate', methods=['POST'])
def check_plate():
    """Check if the detected plate is authorized."""
    data = request.get_json()
    plate = data.get('plate')
    if plate:
        cleaned_plate = plate.replace(" ", "")
        is_authorized = check_authorized_plate(cleaned_plate)
        message = "Authorized" if is_authorized else "Not Authorized"
        return jsonify({"plate": plate, "message": message})
    return jsonify({"plate": "", "message": "No plate detected"})

@app.route('/add_plate', methods=['POST'])
def add_plate():
    """Add a new plate to the authorized list."""
    data = request.get_json()
    plate = data.get('plate')
    if plate:
        cleaned_plate = plate.replace(" ", "")
        success = add_authorized_plate(cleaned_plate)
        if success:
            return jsonify({"message": "Plate added successfully"})
        return jsonify({"message": "Plate already exists"})
    return jsonify({"message": "Invalid plate number"})

@app.route('/last_captured_plates', methods=['GET'])
def last_captured_plates():
    """Fetch the last 5 captured plates."""
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)
    query = "SELECT number_plate FROM captured_plates ORDER BY id DESC LIMIT 5"
    cursor.execute(query)
    plates = [row['number_plate'] for row in cursor.fetchall()]
    cursor.close()
    connection.close()
    return jsonify({"plates": plates})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

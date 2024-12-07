
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

CORS(app)

# Simulate a database (in-memory for simplicity)
patients = {
    "123": {"name": "John Doe", "history": ["Diabetes Diagnosis", "Allergy to Penicillin"]},
}

# Storage for prescriptions
UPLOAD_FOLDER = "./uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# API Endpoints
@app.route("/api/chat", methods=["POST"])
def chat():
    """Hardcoded chat response"""
    user_message = request.json.get("message", "")
    response = {
        "response": f"I see you said: '{user_message}'. This is a placeholder response."
    }
    return jsonify(response)

@app.route("/api/upload-prescription", methods=["POST"])
def upload_prescription():
    """Upload and process a prescription image"""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    # Save file
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    # Simulate recognition result
    prescription_text = "Paracetamol 500mg, Take one tablet twice a day."
    return jsonify({"message": "Prescription uploaded successfully.", "recognized_text": prescription_text})

@app.route("/api/patient/<patient_id>", methods=["GET"])
def get_patient_data(patient_id):
    """Fetch patient data"""
    patient = patients.get(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404
    return jsonify(patient)

@app.route("/api/doctors", methods=["GET"])
def get_doctors():
    """Return hardcoded list of doctors"""
    doctors = [
        {"name": "Dr. Smith", "specialty": "Cardiologist", "rating": 4.8},
        {"name": "Dr. Patel", "specialty": "Dermatologist", "rating": 4.5},
    ]
    return jsonify(doctors)

if __name__ == "__main__":
    app.run(debug=True)

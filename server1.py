from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import datetime
import csv
import json
import requests

app = Flask(__name__)
CORS(app)  

def generate_hash(data):
    hash_object = hashlib.sha256(data.encode())
    return hash_object.hexdigest()

def check_expiry(expiry_date_str):
    expiry_date = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    current_date = datetime.date.today()
    return expiry_date > current_date

def check_salt_composition(expected_composition, actual_composition):
    for salt, expected_value in expected_composition.items():
        if salt not in actual_composition or actual_composition[salt] != expected_value:
            return False
    return True

def load_batch_data_from_csv():
    batch_data = {}
    try:
        with open('your_batch_data.csv', mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                batch_data[row['batch_number']] = {
                    'hash': row['hash'],
                    'salt_composition': json.loads(row['salt_composition']),
                    'expiry_date': row['expiry_date'],
                    'max_transit_temperature': float(row['max_transit_temperature'])
                }
    except Exception as e:
        print(f"Error loading CSV: {str(e)}")
    return batch_data

def fetch_expected_hash(batch_number):
    try:
        response = requests.post('http://localhost:5001/verify-hash', json={'batch_no': batch_number})
        if response.status_code == 200:
            return response.json().get('hash')
        else:
            return None
    except Exception as e:
        print(f"Error fetching hash: {str(e)}")
        return None

@app.route('/')
def home():
    return "Welcome to the Medicine Quality Web App!"

@app.route('/connect', methods=['GET'])
def connect():
    return jsonify({"message": "Connected to Web Application"})

@app.route('/upload-barcode', methods=['POST'])
def upload_barcode():
    batch_data = load_batch_data_from_csv()
    try:
        data = request.get_json()
        print(f"Received data: {data}")

        barcode_data = data.get('barcode_data', '')
        actual_salt_composition = data.get('salt_composition', {})
        transit_temperature = data.get('transit_temperature', 0)

        if not barcode_data:
            return jsonify({"error": "No barcode data provided"}), 400

        batch_number = barcode_data

        if batch_number in batch_data:
            expected_hash = fetch_expected_hash(batch_number)
            if not expected_hash:
                return jsonify({"error": "Batch number not found or hash retrieval failed"}), 404

            generated_hash = generate_hash(batch_number)

            if expected_hash != generated_hash:
                return jsonify({"error": "Invalid hash, unauthorized batch"}), 403

            expected_composition = batch_data[batch_number]["salt_composition"]
            if not check_salt_composition(expected_composition, actual_salt_composition):
                return jsonify({"error": "Salt composition mismatch"}), 400

            expiry_date = batch_data[batch_number]["expiry_date"]
            if not check_expiry(expiry_date):
                return jsonify({"error": "Medicine is expired"}), 400

            max_allowed_temp = batch_data[batch_number]["max_transit_temperature"]
            if transit_temperature > max_allowed_temp:
                return jsonify({"error": f"Exceeded max transit temperature ({max_allowed_temp}°C)"}), 400

            quality_score = 100
            days_left = (datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days
            if days_left < 180:
                quality_score -= 20

            if transit_temperature > (max_allowed_temp - 5):
                quality_score -= 15

            return jsonify({
                "message": "Uploaded successfully",
                "quality_score": quality_score
            }), 200

        else:
            return jsonify({"error": "Batch number not found"}), 404

    except Exception as e:
        print(f"Error in /upload-barcode: {str(e)}")  # Debug print
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
